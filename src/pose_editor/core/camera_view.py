# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from typing import List, Dict
from ..blender import dal
from ..blender.dal import BlenderObjRef, SERIES_NAME
from .person_data_series import RawPersonData
from .marker_data import MarkerData
from .person_data_view import PersonDataView
from pathlib import Path
import json
import os
import re
import math
import numpy as np
from anytree import Node
from anytree.iterators import PreOrderIter
from .skeleton import SkeletonBase

BLENDER_TARGET_WIDTH = 10.0  # Blender units

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

class CameraView(object):
    def __init__(self):
        self._obj: BlenderObjRef | None = None
        self._video_surf: BlenderObjRef | None = None

        self._raw_person_data: List[RawPersonData] = []


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

    dal.set_camera_background(camera_obj_ref, movie_clip)
    dal.set_camera_ortho(camera_obj_ref, scaled_blender_width)

    json_files = sorted([f for f in os.listdir(pose_data_dir) if f.endswith(".json")])

    pose_data_by_person: Dict[int, Dict[int, List[float]]] = {}
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
        with open(filepath, "r") as f:
            data = json.load(f)

        if "people" in data:
            for person_idx, person_data in enumerate(data["people"]):
                if person_idx not in pose_data_by_person:
                    pose_data_by_person[person_idx] = {}
                pose_data_by_person[person_idx][frame_num] = person_data["pose_keypoints_2d"]

    if not pose_data_by_person:
        return camera_view

    num_frames = int(max_frame - min_frame + 1)
    num_joints = len(skeleton_obj._skeleton.leaves)

    for person_idx, frames_data in pose_data_by_person.items():
        series_name = f"{name}_person{person_idx}"
        marker_data = MarkerData(series_name, "COCO_133")

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
                            likelihood if (x is not None and y is not None and likelihood > 0) else -1.0
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
        person_view = PersonDataView(f"PV.{series_name}", skeleton_obj, color=color)
        print(f"Linking PersonDataView {person_view.view_name} to MarkerData series {series_name}...")
        person_view.connect_to_series(marker_data)

        print(f"Linking PersonDataView {person_view.view_root_object.name} to CameraView {camera_view._obj.name}...")
        person_view.view_root_object._get_obj().parent = camera_view._obj._get_obj()
        print(
            f"Setting scale and location for PersonDataView {person_view.view_root_object.name} sx={xfactor}, sy={yfactor}, ox={xoffset}, oy={yoffset}..."
        )
        person_view.view_root_object._get_obj().scale = (xfactor, yfactor, zfactor)
        person_view.view_root_object._get_obj().location = (xoffset, yoffset, 0)
        print(
            f"PersonDataView {person_view.view_root_object.name} created and linked to CameraView {camera_view._obj.name}."
        )
    return camera_view
