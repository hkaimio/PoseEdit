# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np
from anytree.iterators import PreOrderIter

from ..blender import dal
from ..blender.dal import SERIES_NAME, BlenderObjRef, CustomProperty
from .marker_data import MarkerData
from .person_data_series import RawPersonData
from .person_data_view import PersonDataView
from .skeleton import SkeletonBase

BLENDER_TARGET_WIDTH = 10.0  # Blender units

# Custom Properties
VIEW_START = CustomProperty[int]("view_start")
CAMERA_X_SCALE = CustomProperty[float]("camera_x_scale")
CAMERA_Y_SCALE = CustomProperty[float]("camera_y_scale")
CAMERA_Z_SCALE = CustomProperty[float]("camera_z_scale")
CAMERA_X_OFFSET = CustomProperty[float]("camera_x_offset")
CAMERA_Y_OFFSET = CustomProperty[float]("camera_y_offset")


PASTEL_COLORS = [
    (0.68, 0.78, 0.81, 1.0),  # Light Blue
    (0.47, 0.87, 0.47, 1.0),  # Light Green
    (0.96, 0.60, 0.76, 1.0),  # Light Pink
    (0.99, 0.99, 0.59, 1.0),  # Light Yellow
    (0.76, 0.69, 0.88, 1.0),  # Light Purple
    (1.0, 0.70, 0.28, 1.0),  # Light Orange
    (0.74, 0.93, 0.71, 1.0),  # Mint
    (1.0, 0.82, 0.86, 1.0),  # Light Coral
]

BRIGHT_COLORS = [
    (1.0, 0.0, 0.0, 1.0),  # Red
    (0.0, 1.0, 0.0, 1.0),  # Green
    (0.0, 0.0, 1.0, 1.0),  # Blue
    (1.0, 1.0, 0.0, 1.0),  # Yellow
    (1.0, 0.0, 1.0, 1.0),  # Magenta
    (0.0, 1.0, 1.0, 1.0),  # Cyan
    (1.0, 0.5, 0.0, 1.0),  # Orange
    (0.5, 0.0, 1.0, 1.0),  # Purple
]


def _get_all_children_recursive(obj_ref: BlenderObjRef) -> list[BlenderObjRef]:
    """Recursively gets all children of a Blender object."""
    all_children = []
    direct_children = dal.get_children_of_object(obj_ref)
    for child in direct_children:
        all_children.append(child)
        all_children.extend(_get_all_children_recursive(child))
    return all_children


def update_scene_frame_range():
    """Adjusts the scene start and end frames to encompass all camera views."""
    min_start = 1
    max_end = 1

    for view in CameraView.get_all():
        start_frame = view.get_start_frame()
        duration = 0
        # Find the duration of the animation data in the view
        # This includes raw tracks and stitched tracks
        for obj_ref in _get_all_children_recursive(view._obj):
            obj_duration = dal.get_animation_duration(obj_ref)
            if obj_duration > duration:
                duration = obj_duration

        min_start = min(min_start, start_frame)
        max_end = max(max_end, start_frame + duration)

    dal.set_scene_frame_range(min_start, int(max_end))


class CameraView:
    def __init__(self):
        self._obj: BlenderObjRef | None = None
        self._video_surf: BlenderObjRef | None = None
        self._raw_person_data: list[RawPersonData] = []

    @classmethod
    def from_blender_obj(cls, obj_ref: BlenderObjRef) -> CameraView:
        """Creates a CameraView instance from a Blender object reference."""
        if not obj_ref or not dal.get_custom_property(obj_ref, dal.IS_CAMERA_VIEW):
            raise ValueError("Object is not a valid CameraView.")

        view = cls()
        view._obj = obj_ref
        return view

    @classmethod
    def get_all(cls) -> list[CameraView]:
        """Returns all CameraView instances in the current scene."""
        camera_view_refs = dal.find_all_objects_by_property(dal.IS_CAMERA_VIEW, True)
        return [cls.from_blender_obj(ref) for ref in camera_view_refs]

    def get_transform_scale(self) -> tuple[float, float, float]:
        """Returns the scale transformation for this camera view."""
        if not self._obj:
            return (1.0, 1.0, 1.0)
        x_scale = dal.get_custom_property(self._obj, CAMERA_X_SCALE) or 1.0
        y_scale = dal.get_custom_property(self._obj, CAMERA_Y_SCALE) or 1.0
        z_scale = dal.get_custom_property(self._obj, CAMERA_Z_SCALE) or 1.0
        return (x_scale, y_scale, z_scale)

    def get_transform_location(self) -> tuple[float, float, float]:
        """Returns the location transformation for this camera view."""
        if not self._obj:
            return (0.0, 0.0, 0.0)
        x_offset = dal.get_custom_property(self._obj, CAMERA_X_OFFSET) or 0.0
        y_offset = dal.get_custom_property(self._obj, CAMERA_Y_OFFSET) or 0.0
        return (x_offset, y_offset, 0.0)

    def get_start_frame(self) -> int:
        """Returns the start frame of the camera view."""
        if not self._obj:
            return 1
        return dal.get_custom_property(self._obj, VIEW_START) or 1

    def set_start_frame(self, new_start: int):
        """Sets the start frame of the camera view, shifting all related data."""
        if not self._obj:
            return

        old_start = self.get_start_frame()
        delta = new_start - old_start

        if delta == 0:
            return

        # Shift all animation data (f-curves) for all objects in this view
        views = PersonDataView.get_all_for_camera_view(self)

        for person_view in views:
            person_view.shift(delta)

        # Update the property
        dal.set_custom_property(self._obj, VIEW_START, new_start)

        # Update the scene frame range
        # update_scene_frame_range()


def _extract_frame_number(filename: str) -> int:
    """
    Extracts the frame number from a filename.
    Assumes the frame number is the last sequence of digits before the file extension.
    e.g., "cam1_000000.json" -> 0
          "video_frame_00123.png" -> 123

    Args:
        filename: The name of the file.

    Returns:
        The extracted frame number.

    Raises:
        ValueError: If no frame number can be extracted.
    """
    match = re.search(r"(\d+)\.\w+", filename)
    if match:
        return int(match.group(1))

    numbers = re.findall(r"\d+", filename)
    if numbers:
        return int(numbers[-1])

    raise ValueError(f"No frame number found in filename: {filename}")


def create_camera_view(name: str, video_file: Path, pose_data_dir: Path, skeleton_obj: SkeletonBase) -> CameraView:
    """
    Loads raw pose data from JSON files for a single camera view.

    This function orchestrates the creation of all necessary Blender objects
    to represent the camera view, its associated raw person data tracks, and the
    visual representation of that data.

    Blender Representation of a Camera View:
    -   A main Empty object named `View_<name>` is created to act as the root for
        all objects related to this camera view.
    -   A Blender Camera object (`Cam_<name>`) is created and parented to the
        view root. It is configured to display the specified video file as its
        background.
    -   For each person track found in the pose data, this function creates:
        1.  A `MarkerData` instance, which creates a slotted `Action` to hold
            the animation keyframes.
        2.  A `PersonDataView` instance, which creates the visible armature and
            marker objects.
        3.  The `PersonDataView`'s root object is parented to the main
            `View_<name>` Empty.

    Args:
        name: The name of the camera view.
        video_file: The path to the background video file.
        pose_data_dir: The path to the directory containing JSON pose data files.
        skeleton_obj: A SkeletonBase object representing the skeleton definition.

    Returns:
        A CameraView object containing references to the created Blender objects.
    """
    camera_view = CameraView()

    camera_view_empty_name = f"View_{name}"
    camera_view._obj = dal.create_empty(camera_view_empty_name)
    dal.set_custom_property(camera_view._obj, SERIES_NAME, name)
    dal.set_custom_property(camera_view._obj, dal.IS_CAMERA_VIEW, True)
    dal.set_custom_property(camera_view._obj, VIEW_START, 1)

    # Create camera and set background video
    camera_name = f"Cam_{name}"
    camera_obj_ref = dal.create_camera(camera_name, parent_obj=camera_view._obj)

    # Position the camera to look along the Z-axis
    camera_obj = camera_obj_ref._get_obj()
    camera_obj.location = (0, 0, 10)  # Positioned away from the scene
    camera_obj.rotation_euler = (0, 0, 0)

    movie_clip = dal.load_movie_clip(str(video_file))
    video_width, video_height = movie_clip.size

    if video_width > video_height:
        scale_factor = BLENDER_TARGET_WIDTH / video_width
    else:
        scale_factor = BLENDER_TARGET_WIDTH / video_height

    xfactor = scale_factor
    yfactor = -scale_factor
    zfactor = scale_factor

    scaled_blender_width = video_width * scale_factor
    scaled_blender_height = video_height * scale_factor

    xoffset = -scaled_blender_width / 2
    yoffset = scaled_blender_height / 2

    dal.set_custom_property(camera_view._obj, CAMERA_X_SCALE, xfactor)
    dal.set_custom_property(camera_view._obj, CAMERA_Y_SCALE, yfactor)
    dal.set_custom_property(camera_view._obj, CAMERA_Z_SCALE, zfactor)
    dal.set_custom_property(camera_view._obj, CAMERA_X_OFFSET, xoffset)
    dal.set_custom_property(camera_view._obj, CAMERA_Y_OFFSET, yoffset)

    dal.set_camera_background(camera_obj_ref, movie_clip)
    dal.set_camera_ortho(camera_obj_ref, scaled_blender_width)

    json_files = sorted([f for f in os.listdir(pose_data_dir) if f.endswith(".json")])

    pose_data_by_person: dict[int, dict[int, list[float]]] = {}
    min_frame = float("inf")
    max_frame = float("-inf")

    for filename in json_files:
        try:
            frame_num = _extract_frame_number(filename)
        except ValueError:
            continue
        min_frame = min(min_frame, frame_num)
        max_frame = max(max_frame, frame_num)

        filepath = os.path.join(pose_data_dir, filename)
        with open(filepath) as f:
            data = json.load(f)

        if "people" in data:
            for person_idx, person_data in enumerate(data["people"]):
                if person_idx not in pose_data_by_person:
                    pose_data_by_person[person_idx] = {}
                if person_data and "pose_keypoints_2d" in person_data:
                    pose_data_by_person[person_idx][frame_num] = person_data["pose_keypoints_2d"]
                else:
                    pose_data_by_person[person_idx][frame_num] = []

    if not pose_data_by_person:
        return camera_view

    num_frames = int(max_frame - min_frame + 1)
    num_joints = len(skeleton_obj._skeleton.leaves)

    for person_idx, frames_data in pose_data_by_person.items():
        series_name = f"{name}_person{person_idx}"
        marker_data = MarkerData.create_new(series_name, "COCO_133")

        columns_to_extract = []
        for joint_node in PreOrderIter(skeleton_obj._skeleton):
            if not hasattr(joint_node, "id") or joint_node.id is None:
                continue
            joint_name = joint_node.name
            columns_to_extract.append((joint_name, "location", 0))  # X
            columns_to_extract.append((joint_name, "location", 1))  # Y
            columns_to_extract.append((joint_name, '["quality"]', None))  # Quality

        np_data = np.full((num_frames, len(columns_to_extract)), np.nan)

        for frame_idx, frame_num in enumerate(range(int(min_frame), int(max_frame) + 1)):
            if frame_num in frames_data:
                keypoints = frames_data[frame_num]
                col_idx = 0
                for joint_node in PreOrderIter(skeleton_obj._skeleton):
                    if not hasattr(joint_node, "id") or joint_node.id is None:
                        continue
                    kp_idx = joint_node.id * 3
                    if kp_idx + 2 < len(keypoints):
                        x, y, likelihood = keypoints[kp_idx], keypoints[kp_idx + 1], keypoints[kp_idx + 2]

                        np_data[frame_idx, col_idx] = x
                        np_data[frame_idx, col_idx + 1] = y
                        np_data[frame_idx, col_idx + 2] = (
                            likelihood if (x is not np.nan and y is not np.nan and likelihood > 0) else -1.0
                        )
                    col_idx += 3
            else:
                # Person not detected in this frame, set quality to -1
                col_idx = 0
                for joint_node in PreOrderIter(skeleton_obj._skeleton):
                    if not hasattr(joint_node, "id") or joint_node.id is None:
                        continue
                    # The quality is the 3rd value for each joint (x, y, quality)
                    np_data[frame_idx, col_idx + 2] = -1.0
                    col_idx += 3

        marker_data.set_animation_data_from_numpy(columns_to_extract, start_frame=int(min_frame), data=np_data)

        # Assign a consistent color based on the person index
        color = PASTEL_COLORS[person_idx % len(PASTEL_COLORS)]

        print(f"Creating PersonDataView for {series_name}...")
        person_view = PersonDataView.create_new(
            view_name=f"PV.{series_name}",
            skeleton=skeleton_obj,
            color=color,
            camera_view=camera_view,
            collection=None,  # Or a specific collection if needed
        )
        print(f"Linking PersonDataView {person_view.view_name} to MarkerData series {series_name}...")
        person_view.connect_to_series(marker_data)

        print(
            f"PersonDataView {person_view.view_root_object.name} created and linked to CameraView {camera_view._obj.name}."
        )
    return camera_view