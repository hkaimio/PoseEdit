from typing import List, Dict
from ..blender.dal import (BlenderObjRef, create_empty, 
                            set_custom_property, 
                            CAMERA_X_FACTOR, CAMERA_Y_FACTOR, 
                            CAMERA_X_OFFSET, CAMERA_Y_OFFSET, SERIES_NAME)
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

# Placeholder video resolution and target Blender width
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
BLENDER_TARGET_WIDTH = 10.0 # Blender units

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
    match = re.search(r'(\d+)\.\w+', filename)
    if match:
        return int(match.group(1))
    
    numbers = re.findall(r'\d+', filename)
    if numbers:
        return int(numbers[-1])
    
    raise ValueError(f"No frame number found in filename: {filename}")

def create_camera_view(name: str, video_file: Path, pose_data_dir: Path, skeleton_obj: SkeletonBase) -> CameraView:
    """
    Loads raw pose data from JSON files for a single camera view, creates Blender objects
    to represent the camera view and raw person data, and links them.

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
    camera_view._obj = create_empty(camera_view_empty_name)
    set_custom_property(camera_view._obj, SERIES_NAME, name)

    if VIDEO_WIDTH > VIDEO_HEIGHT:
        scale_factor = BLENDER_TARGET_WIDTH / VIDEO_WIDTH
    else:
        scale_factor = BLENDER_TARGET_WIDTH / VIDEO_HEIGHT

    xfactor = scale_factor
    yfactor = -scale_factor
    zfactor = scale_factor

    scaled_blender_width = VIDEO_WIDTH * scale_factor
    scaled_blender_height = VIDEO_HEIGHT * scale_factor

    xoffset = -scaled_blender_width / 2
    yoffset = scaled_blender_height / 2

    set_custom_property(camera_view._obj, CAMERA_X_FACTOR, xfactor)
    set_custom_property(camera_view._obj, CAMERA_Y_FACTOR, yfactor)
    set_custom_property(camera_view._obj, CAMERA_X_OFFSET, xoffset)
    set_custom_property(camera_view._obj, CAMERA_Y_OFFSET, yoffset)

    json_files = sorted([f for f in os.listdir(pose_data_dir) if f.endswith('.json')])
    
    pose_data_by_person: Dict[int, Dict[int, List[float]]] = {}
    min_frame = float('inf')
    max_frame = float('-inf')

    for filename in json_files:
        try:
            frame_num = _extract_frame_number(filename)
        except ValueError:
            continue
        min_frame = min(min_frame, frame_num)
        max_frame = max(max_frame, frame_num)

        filepath = os.path.join(pose_data_dir, filename)
        with open(filepath, 'r') as f:
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
        if int(person_idx) < 5 or int(person_idx) > 10:
            continue  # For now, only process person index 5
        print(f"Processing person {person_idx} with {len(frames_data)} frames...")
        series_name = f"{name}_person{person_idx}"
        marker_data = MarkerData(series_name, "COCO_133")

        columns_to_extract = []
        for joint_node in PreOrderIter(skeleton_obj._skeleton):
            if joint_node.id is None:
                continue
            joint_name = joint_node.name
            columns_to_extract.append((joint_name, 'location', 0)) # X
            columns_to_extract.append((joint_name, 'location', 1)) # Y
            columns_to_extract.append((joint_name, '["quality"]' , None)) # Quality

        np_data = np.full((num_frames, len(columns_to_extract)), np.nan)

        for frame_idx, frame_num in enumerate(range(int(min_frame), int(max_frame) + 1)):
            if frame_num in frames_data:
                keypoints = frames_data[frame_num]
                col_idx = 0
                for joint_node in PreOrderIter(skeleton_obj._skeleton):
                    if joint_node.id is None:
                        continue
                    kp_idx = joint_node.id * 3
                    if kp_idx + 2 < len(keypoints):
                        x, y, likelihood = keypoints[kp_idx], keypoints[kp_idx+1], keypoints[kp_idx+2]
                        
                        np_data[frame_idx, col_idx] = x
                        np_data[frame_idx, col_idx + 1] = y
                        np_data[frame_idx, col_idx + 2] = likelihood
                    col_idx += 3

        marker_data.set_animation_data_from_numpy(columns_to_extract, start_frame=int(min_frame), data=np_data)

        print(f"Creating PersonDataView for {series_name}...")
        person_view = PersonDataView(f"PV.{series_name}", skeleton_obj)
        print(f"Linking PersonDataView {person_view.view_name} to MarkerData series {series_name}...")
        person_view.connect_to_series(marker_data)

        print(f"Linking PersonDataView {person_view.view_root_object.name} to CameraView {camera_view._obj.name}...")
        person_view.view_root_object._get_obj().parent = camera_view._obj._get_obj()
        print(f"Setting scale and location for PersonDataView {person_view.view_root_object.name} sx={xfactor}, sy={yfactor}, ox={xoffset}, oy={yoffset}...")
        person_view.view_root_object._get_obj().scale = (xfactor, yfactor, zfactor)
        person_view.view_root_object._get_obj().location = (xoffset, yoffset, 0)
        print(f"PersonDataView {person_view.view_root_object.name} created and linked to CameraView {camera_view._obj.name}.")
    return camera_view
