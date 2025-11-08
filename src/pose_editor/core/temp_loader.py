# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause
import sys

sys.path.append("C:\\Users\\HarriKaimio\\projects\\pose-editor\\src")  # For testing in Blender's script editor
import pose_editor

pose_editor.register()

import json
import os
import re
from pathlib import Path

import numpy as np

from pose_editor.core.marker_data import MarkerData
from pose_editor.core.skeleton import COCO133Skeleton  # Assuming a default skeleton for now
from pose_editor.pose2sim.skeletons import COCO_133


def _extract_frame_number(filename: str) -> int:
    """Extracts the frame number from a filename (e.g., "cam1_000000.json" -> 0)."""
    numbers = re.findall(r"\d+", filename)
    if numbers:
        return int(numbers[-1])
    raise ValueError(f"No frame number found in filename: {filename}")


def load_mocap_data_series(pose_data_dir: Path, series_prefix: str) -> list[MarkerData]:
    """Loads a directory of pose JSONs and creates MarkerData objects.

    This function reads all JSON files in a directory, sorts them by frame,
    groups the data by person index, and creates and populates a MarkerData
    instance for each person detected in the files.

    Args:
        pose_data_dir: The path to the directory containing JSON pose data files.
        series_prefix: A prefix to use for naming the data series
                       (e.g., "cam1").
    """
    json_files = sorted([f for f in os.listdir(pose_data_dir) if f.endswith(".json")])

    # {person_idx: {frame_num: [keypoints_array]}}
    pose_data_by_person: dict[int, dict[int, list[float]]] = {}
    min_frame = 20000000
    max_frame = -1000000

    for filename in json_files:
        try:
            frame_num = _extract_frame_number(filename)
            min_frame = min(min_frame, frame_num)
            max_frame = max(max_frame, frame_num)
        except ValueError:
            continue

        filepath = os.path.join(pose_data_dir, filename)
        with open(filepath) as f:
            data = json.load(f)

        if "people" in data:
            for person_idx, person_data in enumerate(data["people"]):
                if person_idx not in pose_data_by_person:
                    pose_data_by_person[person_idx] = {}
                pose_data_by_person[person_idx][frame_num] = person_data["pose_keypoints_2d"]

    if not pose_data_by_person:
        print("No person data found in JSON files.")
        return []

    # For now, we'll use a fixed skeleton definition.
    skeleton = COCO133Skeleton(COCO_133)
    num_frames = max_frame - min_frame + 1

    personData = list()

    for person_idx, frames_data in pose_data_by_person.items():
        series_name = f"{series_prefix}_person{person_idx}"
        print(f"Processing series: {series_name}")

        marker_data = MarkerData.create_new(series_name, skeleton_name="COCO_133")

        # Prepare data for the numpy array
        # Let's define the columns we want to extract
        columns_to_extract = []
        for joint in range(133):
            bone_name = skeleton.get_joint_name(joint)
            if not bone_name:
                bone_name = f"joint_{joint}"

            columns_to_extract.append((bone_name, "location", 0))  # X
            columns_to_extract.append((bone_name, "location", 1))  # Y
            columns_to_extract.append((bone_name, '["quality"]', None))  # Quality

        # Create an empty numpy array to hold all data for this person
        # Initialize with np.nan to represent missing data
        np_data = np.full((num_frames, len(columns_to_extract)), np.nan)

        for frame_idx, frame_num in enumerate(range(min_frame, max_frame + 1)):
            if frame_num in frames_data:
                keypoints = frames_data[frame_num]
                col_idx = 0
                for joint in range(133):
                    kp_idx = joint * 3
                    if kp_idx + 2 < len(keypoints):
                        x, y, likelihood = keypoints[kp_idx], keypoints[kp_idx + 1], keypoints[kp_idx + 2]

                        # For now, store raw pixel coordinates. Transformation will be handled later.
                        np_data[frame_idx, col_idx] = x
                        np_data[frame_idx, col_idx + 1] = y
                        np_data[frame_idx, col_idx + 2] = likelihood
                    col_idx += 3

        print(f"Setting animation data for {series_name}...")
        marker_data.set_animation_data_from_numpy(columns_to_extract, start_frame=min_frame, data=np_data)
        personData.append(marker_data)
    print("Finished loading all data series.")
    return personData


from pose_editor.core.camera_view import create_camera_view

camera_view = create_camera_view(
    "CameraView1",
    Path("C:\\temp\\aikido-2024-08-25-harri-tommi\\kotegaeshi\\videos\\cam1.mp4"),
    Path("C:\\temp\\aikido-2024-08-25-harri-tommi\\kotegaeshi\\pose\\cam1_json"),
    COCO133Skeleton(COCO_133),
)
# person_data = load_mocap_data_series(Path("C:\\temp\\aikido-2024-08-25-harri-tommi\\kotegaeshi\\pose\\cam1_json"), "cam1")
# person_view = PersonDataView("PV.Harri.cam1", COCO133Skeleton(COCO_133))

# person_view.connect_to_series(person_data[5])
