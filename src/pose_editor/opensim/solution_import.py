"""
OpenSim solution import functionality.

This module provides functions to import OpenSim simulation results (.mot/.sto files)
back into Blender armatures as animation keyframes.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import bpy
import numpy as np

from ..blender import dal
from .config import ArmatureExportConfig, JointType


@dataclass
class OpenSimSolutionData:
    """
    Parsed OpenSim solution data.

    Attributes:
        time_values: List of time values in seconds
        coordinate_values: Dictionary mapping coordinate names to value lists
        in_degrees: Whether rotation values are in degrees (True) or radians (False)
    """
    time_values: list[float]
    coordinate_values: dict[str, list[float]]
    in_degrees: bool = True  # OpenSim defaults to degrees


def parse_opensim_solution(solution_file: str) -> OpenSimSolutionData:
    """
    Parse OpenSim .mot or .sto file.

    Both .mot and .sto files have the same format:
    - Header section ending with "endheader"
    - Column names on next line
    - Tab/space-separated data rows

    Args:
        solution_file: Path to solution file (.mot or .sto)

    Returns:
        Parsed solution data with time values and coordinate values

    Raises:
        FileNotFoundError: If solution file doesn't exist
        ValueError: If file format is invalid
    """
    solution_path = Path(solution_file)
    if not solution_path.exists():
        raise FileNotFoundError(f"Solution file not found: {solution_file}")

    with open(solution_file) as f:
        lines = f.readlines()

    # Find header end and check for inDegrees flag
    header_end = -1
    in_degrees = True  # Default to degrees (OpenSim convention)

    for i, line in enumerate(lines):
        # Check for inDegrees flag in header
        if line.strip().lower().startswith('indegrees'):
            # Parse inDegrees=yes or inDegrees=no
            if '=' in line:
                value = line.split('=')[1].strip().lower()
                in_degrees = value.startswith('y')  # 'yes' or 'y'

        if line.strip().lower().startswith('endheader'):
            header_end = i + 1
            break

    if header_end == -1:
        raise ValueError(f"No 'endheader' line found in {solution_file}")

    if header_end >= len(lines):
        raise ValueError(f"No data after header in {solution_file}")

    # Next line is column names
    column_names = lines[header_end].split()

    if not column_names:
        raise ValueError(f"No column names found in {solution_file}")

    # Parse data rows
    data = {name: [] for name in column_names}

    for line_num, line in enumerate(lines[header_end + 1:], start=header_end + 2):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        values = line.split()
        if len(values) != len(column_names):
            print(f"Warning: Line {line_num} has {len(values)} values but expected {len(column_names)}, skipping")
            continue

        for name, value_str in zip(column_names, values, strict=True):
            try:
                data[name].append(float(value_str))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid numeric value '{value_str}' for column '{name}' at line {line_num}"
                ) from exc

    # Extract time column (try different common names)
    time_values = None
    for time_name in ['time', 'Time', 'TIME', 't']:
        if time_name in data:
            time_values = data.pop(time_name)
            break

    if time_values is None:
        raise ValueError(f"No time column found in {solution_file}")

    if not time_values:
        raise ValueError(f"No data rows found in {solution_file}")

    print(f"Parsed {len(time_values)} frames from {solution_file}")
    print(f"Time range: {time_values[0]:.3f} to {time_values[-1]:.3f} seconds")
    print(f"Coordinates: {len(data)}")
    print(f"Rotation units: {'degrees' if in_degrees else 'radians'}")

    return OpenSimSolutionData(
        time_values=time_values,
        coordinate_values=data,
        in_degrees=in_degrees,
    )


def build_coordinate_to_bone_map(config: ArmatureExportConfig) -> dict[str, tuple]:
    """
    Build mapping from OpenSim coordinate names to (bone_name, axis_index, axis_type).

    Args:
        config: Armature export configuration used for export

    Returns:
        Dictionary mapping coordinate names to (blender_bone_name, axis_index, axis_type)
        where axis_type is 'tx', 'ty', 'tz', 'rx', 'ry', or 'rz'

    Example:
        {"shoulder.R_joint_coord_rot_x": ("shoulder.R", 0, "rx")}
    """
    coord_map = {}

    for bone_name, bone_config in config.bones.items():
        opensim_name = bone_config.opensim_name
        joint_name = f"{opensim_name}_joint"
        constraints = bone_config.constraints

        if constraints.joint_type == JointType.FREE:
            # Free joint has 6 coordinates
            # In OpenSim .mot files, Free joint coordinates are named simply coord_0 through coord_5
            # (without the joint name prefix)
            # OpenSim FreeJoint convention:
            # coord_0, coord_1, coord_2 = rotations (x, y, z) in degrees
            # coord_3, coord_4, coord_5 = translations (x, y, z) in meters
            for i, axis in enumerate(['x', 'y', 'z']):
                # Rotation coordinates (first 3)
                coord_name = f"coord_{i}"
                coord_map[coord_name] = (bone_name, i, f"r{axis}")

                # Translation coordinates (last 3)
                coord_name = f"coord_{i+3}"
                coord_map[coord_name] = (bone_name, i, f"t{axis}")
        else:
            # Custom joint - map based on unlocked axes
            axis_list = [
                (constraints.x_axis, 'x', 0),
                (constraints.y_axis, 'y', 1),
                (constraints.z_axis, 'z', 2)
            ]

            for axis_constraint, axis_name, axis_idx in axis_list:
                if axis_constraint and not axis_constraint.locked:
                    coord_name = f"{joint_name}_coord_rot_{axis_name}"
                    coord_map[coord_name] = (bone_name, axis_idx, f"r{axis_name}")

    return coord_map


def apply_solution_to_armature(
    armature_obj: bpy.types.Object,
    solution_data: OpenSimSolutionData,
    coord_to_bone_map: dict[str, tuple],
    frame_start: int = 1,
    fps: float = 30.0,
    clear_existing: bool = True,
) -> None:
    """
    Apply OpenSim solution to Blender armature animation using fast batch fcurve setting.

    Args:
        armature_obj: Target Blender armature object
        solution_data: Parsed OpenSim solution data
        coord_to_bone_map: Mapping from coordinate names to (bone_name, axis_index, axis_type)
        frame_start: First frame number to write animation
        fps: Frames per second for time-to-frame conversion
        clear_existing: If True, clear existing animation data before applying

    Raises:
        ValueError: If armature is not valid or bones are missing
    """
    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object '{armature_obj.name}' is not an armature")

    scene = bpy.context.scene
    scene.frame_start = frame_start

    # Calculate frame numbers from time values
    frame_numbers = [
        frame_start + int(t * fps)
        for t in solution_data.time_values
    ]
    scene.frame_end = frame_numbers[-1]
    num_frames = len(frame_numbers)

    print(f"Applying animation from frame {frame_start} to {frame_numbers[-1]} ({num_frames} frames)")

    # Clear existing animation if requested
    if clear_existing:
        if armature_obj.animation_data:
            armature_obj.animation_data.action = None

    # Create new action
    action_name = f"{armature_obj.name}_opensim_solution"
    action = bpy.data.actions.new(name=action_name)

    if not armature_obj.animation_data:
        armature_obj.animation_data_create()
    armature_obj.animation_data.action = action

    # Get the action slot name (for Blender 4.0+ layered actions)
    slot_name = armature_obj.name

    # Prepare data structures for batch fcurve setting
    # Group coordinates by bone and build column descriptors
    bone_channels = {}  # {bone_name: {data_path: {axis_idx: coord_name}}}
    unmapped_coords = []

    for coord_name, values in solution_data.coordinate_values.items():
        if coord_name not in coord_to_bone_map:
            unmapped_coords.append(coord_name)
            continue

        bone_name, axis_idx, axis_type = coord_to_bone_map[coord_name]

        if bone_name not in armature_obj.pose.bones:
            print(f"Warning: Bone '{bone_name}' not found in armature, skipping coordinate '{coord_name}'")
            continue

        # Determine data path
        if axis_type.startswith('t'):
            data_path = f'pose.bones["{bone_name}"].location'
        else:
            data_path = f'pose.bones["{bone_name}"].rotation_euler'
            # Ensure bone uses XYZ Euler rotation
            pose_bone = armature_obj.pose.bones[bone_name]
            if pose_bone.rotation_mode != 'ZYX':
                print(f"Setting bone '{bone_name}' rotation mode to ZYX")
                pose_bone.rotation_mode = 'ZYX'

        # Store coordinate info
        if bone_name not in bone_channels:
            bone_channels[bone_name] = {}
        if data_path not in bone_channels[bone_name]:
            bone_channels[bone_name][data_path] = {}
        bone_channels[bone_name][data_path][axis_idx] = coord_name

    # Build columns list and data array for dal.set_fcurves_from_numpy
    columns = []  # List of (slot_name, data_path, axis_index)
    coord_names_ordered = []  # Corresponding coordinate names

    for bone_name in sorted(bone_channels.keys()):
        for data_path in sorted(bone_channels[bone_name].keys()):
            for axis_idx in sorted(bone_channels[bone_name][data_path].keys()):
                coord_name = bone_channels[bone_name][data_path][axis_idx]
                columns.append((slot_name, data_path, axis_idx))
                coord_names_ordered.append(coord_name)

    # Build numpy array with all animation data
    num_columns = len(columns)
    data_array = np.zeros((num_frames, num_columns), dtype=np.float64)

    # Convert degrees to radians if needed
    deg_to_rad = math.radians(1.0) if solution_data.in_degrees else 1.0

    for col_idx, coord_name in enumerate(coord_names_ordered):
        values = solution_data.coordinate_values[coord_name]
        bone_name, axis_idx, axis_type = coord_to_bone_map[coord_name]

        # Apply unit conversion
        for frame_idx, value in enumerate(values):
            if axis_type.startswith('r'):
                # Rotation: convert degrees to radians if needed
                data_array[frame_idx, col_idx] = value * deg_to_rad
            else:
                # Translation: already in meters
                data_array[frame_idx, col_idx] = value

    # Use fast batch fcurve setting from DAL
        print(f"Setting {num_columns} fcurves with {num_frames} keyframes each using fast batch method...")
    dal.set_fcurves_from_numpy(
        action=action,
        columns=columns,
        start_frame=frame_start,
        data=data_array,
        interpolation='LINEAR',
    )

    # Report results
    modified_bones = set(bone_channels.keys())
    print(f"Applied animation to {len(modified_bones)} bones: {sorted(modified_bones)}")

    if unmapped_coords:
        print(f"Warning: {len(unmapped_coords)} coordinates not mapped to bones:")
        for coord in unmapped_coords[:10]:  # Show first 10
            print(f"  - {coord}")
        if len(unmapped_coords) > 10:
            print(f"  ... and {len(unmapped_coords) - 10} more")

    # Reset to first frame
    scene.frame_set(frame_start)
def import_opensim_solution(
    solution_file: str,
    armature_name: str,
    config: ArmatureExportConfig,
    frame_start: int = 1,
    fps: float = 30.0,
    clear_existing: bool = True,
) -> None:
    """
    Import OpenSim IK solution back to Blender armature.

    This is the main entry point for importing OpenSim solutions.

    Args:
        solution_file: Path to OpenSim solution file (.mot or .sto)
        armature_name: Name of target Blender armature object
        config: Same configuration that was used for export
        frame_start: First frame to write animation
        fps: Frames per second for time-to-frame conversion
        clear_existing: If True, clear existing animation before importing

    Raises:
        ValueError: If armature not found or invalid
        FileNotFoundError: If solution file doesn't exist

    Example:
        >>> from pose_editor.opensim import import_opensim_solution
        >>> from pose_editor.opensim.configs import create_cc5_human_config
        >>>
        >>> config = create_cc5_human_config()
        >>> import_opensim_solution(
        ...     solution_file="output/ik_solution.mot",
        ...     armature_name="cc5-timo",
        ...     config=config,
        ...     frame_start=1,
        ...     fps=30.0
        ... )
    """
    # Get armature object
    if armature_name not in bpy.data.objects:
        raise ValueError(f"Armature '{armature_name}' not found in scene")

    armature_obj = bpy.data.objects[armature_name]

    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object '{armature_name}' is not an armature")

    print("\n=== Importing OpenSim Solution ===")
    print(f"Solution file: {solution_file}")
    print(f"Target armature: {armature_name}")
    print(f"Frame start: {frame_start}")
    print(f"FPS: {fps}")

    # Parse solution file
    print("\nParsing solution file...")
    solution_data = parse_opensim_solution(solution_file)

    # Build coordinate mapping
    print("\nBuilding coordinate-to-bone mapping...")
    coord_to_bone_map = build_coordinate_to_bone_map(config)
    print(f"Mapped {len(coord_to_bone_map)} coordinates to bones")

    # Apply animation to armature
    print("\nApplying animation to armature...")
    apply_solution_to_armature(
        armature_obj,
        solution_data,
        coord_to_bone_map,
        frame_start,
        fps,
        clear_existing,
    )

    print("\n=== Import Complete ===")
