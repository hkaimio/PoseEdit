from typing import List, Dict
from ..blender.dal import (BlenderObjRef, create_empty, create_marker, 
                            add_keyframe, set_custom_property, 
                            CAMERA_X_FACTOR, CAMERA_Y_FACTOR, 
                            CAMERA_X_OFFSET, CAMERA_Y_OFFSET, SERIES_NAME)
from .person_data_series import RawPersonData
from pathlib import Path
import json
import os
import re
import math
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
    
    # Fallback for filenames without extension or different patterns
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

    # Create main camera view empty
    camera_view_empty_name = f"View_{name}"
    camera_view._obj = create_empty(camera_view_empty_name)
    set_custom_property(camera_view._obj, SERIES_NAME, name)

    # Calculate transformation factors and offsets
    if VIDEO_WIDTH > VIDEO_HEIGHT:
        scale_factor = BLENDER_TARGET_WIDTH / VIDEO_WIDTH
    else:
        scale_factor = BLENDER_TARGET_WIDTH / VIDEO_HEIGHT

    xfactor = scale_factor
    yfactor = -scale_factor # Negative for Y-axis inversion

    scaled_blender_width = VIDEO_WIDTH * scale_factor
    scaled_blender_height = VIDEO_HEIGHT * scale_factor

    xoffset = -scaled_blender_width / 2
    yoffset = scaled_blender_height / 2

    # Store transformation factors as custom properties
    set_custom_property(camera_view._obj, CAMERA_X_FACTOR, xfactor)
    set_custom_property(camera_view._obj, CAMERA_Y_FACTOR, yfactor)
    set_custom_property(camera_view._obj, CAMERA_X_OFFSET, xoffset)
    set_custom_property(camera_view._obj, CAMERA_Y_OFFSET, yoffset)

    marker_ids = {node.id: node.name for node in PreOrderIter(skeleton_obj._skeleton) if node.id is not None}

    json_files = sorted([f for f in os.listdir(pose_data_dir) if f.endswith('.json')])
    
    pose_data_by_person_and_frame: Dict[int, Dict[int, List[float]]] = {}
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
                if person_idx not in pose_data_by_person_and_frame:
                    pose_data_by_person_and_frame[person_idx] = {}
                pose_data_by_person_and_frame[person_idx][frame_num] = person_data["pose_keypoints_2d"]

    for person_idx, frames_data in pose_data_by_person_and_frame.items():
        raw_person_obj = create_empty(f"{name}_Person{person_idx}", parent_obj=camera_view._obj)
        set_custom_property(raw_person_obj, SERIES_NAME, f"{name}_Person{person_idx}")
        raw_person_data = RawPersonData(raw_person_obj)
        raw_person_data._skeleton = skeleton_obj._skeleton
        camera_view._raw_person_data.append(raw_person_data)

        # Apply transformation to the parent object
        raw_person_obj._get_obj().scale = (xfactor, yfactor, 1)
        raw_person_obj._get_obj().location = (xoffset, yoffset, 0)

        marker_fcurve_data: Dict[str, Dict[str, List[tuple[int, List[float]]]]] = {}
        for marker_name in marker_ids.values():
            marker_fcurve_data[marker_name] = {
                'location': [],
                '["quality"]' : []
            }

        if min_frame not in frames_data:
            for marker_name in marker_fcurve_data.keys():
                marker_fcurve_data[marker_name]['["quality"]'].append((min_frame, [-1.0]))

        for frame_num in range(min_frame, max_frame + 1):
            if frame_num not in frames_data:
                continue
            
            keypoints = frames_data[frame_num]
            for node_id, marker_name in marker_ids.items():
                idx = node_id * 3
                if idx + 2 < len(keypoints):
                    x = keypoints[idx]
                    y = keypoints[idx + 1]
                    likelihood = keypoints[idx + 2]

                    if math.isnan(x) or math.isnan(y):
                        marker_fcurve_data[marker_name]['["quality"]'].append((frame_num, [-1.0]))
                    else:
                        # Store raw pixel coordinates
                        marker_fcurve_data[marker_name]['location'].append((frame_num, [x, y, 0.0]))
                        marker_fcurve_data[marker_name]['["quality"]'].append((frame_num, [likelihood]))

        for marker_name, fcurve_data in marker_fcurve_data.items():
            marker_obj_ref = create_marker(raw_person_data._blenderObj, marker_name, (1.0, 1.0, 0.0, 1.0))
            raw_person_data._markers[marker_name] = marker_obj_ref

            for data_path, keyframes in fcurve_data.items():
                for i in range(len(keyframes)):
                    frame, values = keyframes[i]
                    add_keyframe(marker_obj_ref, frame, {data_path: values})

    return camera_view