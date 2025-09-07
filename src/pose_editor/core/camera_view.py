from typing import List, Dict
from ..blender.dal import BlenderObjRef, create_empty, create_marker, set_fcurve_from_data, add_keyframe
from .person_data_series import RawPersonData
from pathlib import Path
import json
import os
import re
import math
from anytree import Node
from anytree.iterators import PreOrderIter
from .skeleton import SkeletonBase

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

    # Use the provided skeleton object
    marker_ids = {node.id: node.name for node in PreOrderIter(skeleton_obj._skeleton) if node.id is not None}

    # Process JSON files
    json_files = sorted([f for f in os.listdir(pose_data_dir) if f.endswith('.json')])
    
    pose_data_by_person_and_frame: Dict[int, Dict[int, List[float]]] = {}
    min_frame = float('inf')
    max_frame = float('-inf')

    for filename in json_files:
        try:
            frame_num = _extract_frame_number(filename)
        except ValueError:
            continue # Skip files that don't have a valid frame number
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

    # Create RawPersonData objects and Blender markers
    for person_idx, frames_data in pose_data_by_person_and_frame.items():
        raw_person_data = RawPersonData(create_empty(f"{name}_Person{person_idx}", parent_obj=camera_view._obj))
        raw_person_data._skeleton = skeleton_obj._skeleton
        camera_view._raw_person_data.append(raw_person_data)

        # Prepare data for F-curves
        marker_fcurve_data: Dict[str, Dict[str, List[tuple[int, float]]]] = {}
        for marker_name in marker_ids.values():
            from typing import List, Dict
from ..blender.dal import BlenderObjRef, create_empty, create_marker, set_fcurve_from_data
from .person_data_series import RawPersonData
from pathlib import Path
import json
import os
import re
from anytree import Node
from anytree.iterators import PreOrderIter
from .skeleton import SkeletonBase

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

    # Use the provided skeleton object
    marker_ids = {node.id: node.name for node in PreOrderIter(skeleton_obj._skeleton) if node.id is not None}

    # Process JSON files
    json_files = sorted([f for f in os.listdir(pose_data_dir) if f.endswith('.json')])
    
    pose_data_by_person_and_frame: Dict[int, Dict[int, List[float]]] = {}
    min_frame = float('inf')
    max_frame = float('-inf')

    for filename in json_files:
        try:
            frame_num = _extract_frame_number(filename)
        except ValueError:
            continue # Skip files that don't have a valid frame number
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

    # Create RawPersonData objects and Blender markers
    for person_idx, frames_data in pose_data_by_person_and_frame.items():
        print(f"Creating RawPersonData for person {person_idx}  of {len(pose_data_by_person_and_frame)}  with {len(frames_data)} frames")
        raw_person_data = RawPersonData(create_empty(f"{name}_Person{person_idx}", parent_obj=camera_view._obj))
        raw_person_data._skeleton = skeleton_obj._skeleton
        camera_view._raw_person_data.append(raw_person_data)

        # Prepare data for F-curves
        marker_fcurve_data: Dict[str, Dict[str, List[tuple[int, List[float]]]]] = {}
        for marker_name in marker_ids.values():
            marker_fcurve_data[marker_name] = {
                'location': [],
                '["quality"]': []
            }

        for frame_num in range(min_frame, max_frame + 1):
            if frame_num not in frames_data:
                # Handle missing frames if necessary, e.g., interpolate or skip
                continue
            
            keypoints = frames_data[frame_num]
            for node_id, marker_name in marker_ids.items():
                # Assuming keypoints are [x1, y1, l1, x2, y2, l2, ...]
                # and node_id corresponds to the 0-indexed marker in the flattened array
                # So, actual index in keypoints array is node_id * 3
                idx = node_id * 3
                if idx + 2 < len(keypoints):
                    x = keypoints[idx]
                    y = keypoints[idx + 1]
                    likelihood = keypoints[idx + 2]

                    # Convert pixel coordinates to Blender units (example: simple scaling)
                    # Assuming video resolution is 1920x1080, and Blender unit is 1m
                    # This needs to be refined based on actual video and scene scale
                    blender_x = x / 100.0  # Example scaling
                    blender_y = y / 100.0  # Example scaling
                    blender_z = 0.0 # 2D data

                    if math.isnan(x) or math.isnan(y):
                        marker_fcurve_data[marker_name]['["quality"]'].append((frame_num, [0.0]))
                    else:
                        marker_fcurve_data[marker_name]['location'].append((frame_num, [blender_x, blender_y, blender_z]))
                        marker_fcurve_data[marker_name]['["quality"]'].append((frame_num, [likelihood]))

        # Create marker objects and set F-curves
        for marker_name, fcurve_data in marker_fcurve_data.items():
            # Find the corresponding skeleton node to get its parent for Blender object hierarchy
            # This part needs refinement based on how you want to parent markers in Blender
            # For now, parent all markers directly to the RawPersonData empty
            marker_obj_ref = create_marker(raw_person_data._blenderObj, marker_name, (1.0, 1.0, 0.0, 1.0)) # Default color yellow
            raw_person_data._markers[marker_name] = marker_obj_ref

            for data_path, keyframes in fcurve_data.items():
                for i in range(len(keyframes)):
                    frame, values = keyframes[i]
                    add_keyframe(marker_obj_ref, frame, {data_path: values})
                    

    # TODO: Create video plane (optional for now)

    return camera_view
