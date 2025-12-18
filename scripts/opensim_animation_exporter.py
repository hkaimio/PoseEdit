#!/usr/bin/env python3
"""
OpenSim Animation Exporter

Standalone script to export OpenSim model animations to YAML or BVH format.
Uses similar logic as motion.py (lines 132 onward) to extract body transforms
and exports them in a format compatible with armature_export.py from Blender.

Requirements:
- OpenSim Python API (opensim)
- numpy
- PyYAML

Usage:
    # Export animation with skeleton (YAML format)
    python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml

    # Export animation as BVH
    python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.bvh

    # With optional parameters:
    python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml \\
        --start-frame 0 --end-frame 100 --framerate 30.0

    # Export skeleton rest pose only (YAML format)
    python opensim_animation_exporter.py --skeleton --model model.osim -o skeleton.yaml
"""

import argparse
import math
import sys
import traceback
from pathlib import Path

# Defer imports to allow help to work without dependencies
opensim_available = True
numpy_available = True
yaml_available = True

try:
    import opensim as osim
except ImportError:
    opensim_available = False

try:
    import numpy as np
except ImportError:
    numpy_available = False

try:
    import yaml
except ImportError:
    yaml_available = False


def check_dependencies():
    """Check that all required dependencies are available."""
    missing = []
    if not opensim_available:
        missing.append("opensim (OpenSim Python API)")
    if not numpy_available:
        missing.append("numpy")
    if not yaml_available:
        missing.append("PyYAML")

    if missing:
        print("Error: Missing required dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nPlease install the missing packages:")
        if not opensim_available:
            print("  - Install OpenSim with Python bindings")
        if not numpy_available:
            print("  - pip install numpy")
        if not yaml_available:
            print("  - pip install pyyaml")
        return False
    return True


def check_file_overwrite(file_path: str, force: bool = False) -> bool:
    """
    Check if file exists and get user permission to overwrite.

    Args:
        file_path: Path to the file to check
        force: If True, skip user confirmation

    Returns:
        bool: True if safe to write, False otherwise
    """
    if not Path(file_path).exists():
        return True

    if force:
        print(f"Warning: Overwriting existing file: {file_path}")
        return True

    try:
        response = input(f"File '{file_path}' already exists. Overwrite? (y/N): ").strip().lower()
        return response in ['y', 'yes']
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled by user.")
        return False


def rotation_matrix_to_euler_zxy(R):
    """
    Convert a 3x3 rotation matrix to ZXY Euler angles (in radians).
    Assumes R is a valid rotation matrix.
    """
    # Handle gimbal lock
    if abs(R[2][1]) < 1.0:
        x = math.asin(R[2][1])
        z = math.atan2(-R[0][1], R[1][1])
        y = math.atan2(-R[2][0], R[2][2])
    else:
        # Gimbal lock: R[2][1] == ±1
        x = math.pi / 2 if R[2][1] > 0 else -math.pi / 2
        z = math.atan2(R[1][0], R[0][0])
        y = 0

    return (z, x, y)  # ZXY order


def rotation_matrix_to_quaternion(R):
    """
    Convert a 3x3 rotation matrix to quaternion (w, x, y, z).
    Uses Shepperd's method for numerical stability.
    """
    trace = R[0, 0] + R[1, 1] + R[2, 2]

    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2  # s = 4 * qw
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2  # s = 4 * qx
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2  # s = 4 * qy
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2  # s = 4 * qz
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s

    # Convert numpy scalars to Python floats to avoid YAML serialization issues
    return (float(w), float(x), float(y), float(z))  # Quaternion as (w, x, y, z)


# Example bone mapping with None for bones to skip
bone_to_hik_map = {
    'spine' : 'Hips',
    # 'spine.001' : 'Spine',
    # 'spine.002' : 'Spine3',
    # 'spine.003' : 'Spine9',
    'spine.002' : 'Spine',
    'spine.003' : 'Spine3',
    'spine.004' : 'Neck',
    'spine.005' : 'Neck1',
    'spine.006' : 'Head',
    'shoulder.R' : 'RightShoulder',
    'upper_arm.R' : 'RightArm',
    'forearm.R' : 'RightForeArm',
    'hand.R' : 'RightHand',
    'palm.01.R': 'RightHandIndex1',
    'f_index.01.R': 'RightHandIndex2',
    'f_index.02.R': 'RightHandIndex3',
    'f_index.03.R': 'RightHandIndex4',
    'thumb.01.R': 'RightHandThumb2',
    'thumb.02.R': 'RightHandThumb3',
    "thumb.03.R": "RightHandThumb4",
    "palm.02.R": "RightHandMiddle1",
    "f_middle.01.R": "RightHandMiddle2",
    "f_middle.02.R": "RightHandMiddle3",
    "f_middle.03.R": "RightHandMiddle4",
    "palm.03.R": "RightHandRing1",
    "f_ring.01.R": "RightHandRing2",
    "f_ring.02.R": "RightHandRing3",
    "f_ring.03.R": "RightHandRing4",
    "palm.04.R": "RightHandPinky1",
    "f_pinky.01.R": "RightHandPinky2",
    "f_pinky.02.R": "RightHandPinky3",
    "f_pinky.03.R": "RightHandPinky4",
    'shoulder.L' : 'LeftShoulder',
    'upper_arm.L' : 'LeftArm',
    'forearm.L' : 'LeftForeArm',
    'hand.L' : 'LeftHand',
    'palm.01.L': 'LeftHandIndex1',
    'f_index.01.L': 'LeftHandIndex2',
    'f_index.02.L': 'LeftHandIndex3',
    'f_index.03.L': 'LeftHandIndex4',
    'thumb.01.L': 'LeftHandThumb2',
    'thumb.02.L': 'LeftHandThumb3',
    "thumb.03.L": "LeftHandThumb4",
    "palm.02.L": "LeftHandMiddle1",
    "f_middle.01.L": "LeftHandMiddle2",
    "f_middle.02.L": "LeftHandMiddle3",
    "f_middle.03.L": "LeftHandMiddle4",
    "palm.03.L": "LeftHandRing1",
    "f_ring.01.L": "LeftHandRing2",
    "f_ring.02.L": "LeftHandRing3",
    "f_ring.03.L": "LeftHandRing4",
    "palm.04.L": "LeftHandPinky1",
    "f_pinky.01.L": "LeftHandPinky2",
    "f_pinky.02.L": "LeftHandPinky3",
    "f_pinky.03.L": "LeftHandPinky4",
    'thigh.R' : 'RightUpLeg',
    'shin.R' : 'RightLeg',
    'foot.R' : 'RightFoot',
    'thigh.L' : 'LeftUpLeg',
    'shin.L' : 'LeftLeg',
    'foot.L' : 'LeftFoot',
    "toe.L": None,
    "toe.R": None,
    "heel.02.R": None,
    "heel.02.L": None
}


def yup_to_zup_rotation_matrix(rot_matrix_yup):
    # Rotation matrix for +90 degrees around X-axis
    angle_rad = np.pi / 2
    rot_x = np.array([
        [1, 0, 0],
        [0, np.cos(angle_rad), -np.sin(angle_rad)],
        [0, np.sin(angle_rad), np.cos(angle_rad)]
    ])

    # Convert rotation from Y-up to Z-up
    rot_matrix_zup = rot_x @ rot_matrix_yup
    return rot_matrix_zup


def global_to_local_transform(global_transform, parent_global_transform):
    """
    Convert a global transform to local coordinates relative to parent.

    Args:
        global_transform: 4x4 transformation matrix in global coordinates
        parent_global_transform: 4x4 transformation matrix of parent in global coordinates

    Returns:
        4x4 transformation matrix in parent's local coordinate system
    """
    # Local transform = parent_global^-1 * global_transform
    parent_global_inv = np.linalg.inv(parent_global_transform)
    local_transform = parent_global_inv @ global_transform
    return local_transform


def get_body_global_transforms(model, state, bodies):
    """
    Get global transforms for all bodies in the current state.

    Returns:
        dict mapping body_name -> 4x4 global transformation matrix
    """
    global_transforms = {}

    for body in bodies:
        body_name = body.getName()
        if body_name.lower() == 'ground':
            # Ground has identity transform
            global_transforms[body_name] = np.eye(4)
            continue

        # Get transform in ground frame
        H_swig = body.getTransformInGround(state)
        T = H_swig.T().to_numpy()
        R_swig = H_swig.R()

        R = np.array([[R_swig.get(0, 0), R_swig.get(0, 1), R_swig.get(0, 2)],
                      [R_swig.get(1, 0), R_swig.get(1, 1), R_swig.get(1, 2)],
                      [R_swig.get(2, 0), R_swig.get(2, 1), R_swig.get(2, 2)]])

        # Build 4x4 transformation matrix
        H = np.block([[R, T.reshape(3, 1)], [np.zeros(3), 1]])
        global_transforms[body_name] = H

    return global_transforms



def export_opensim_animation_to_yaml(osim_file_path: str, mot_file_path: str,
                                   output_file: str, frame_start: int = 0,
                                   frame_end: int | None = None,
                                   target_framerate: float = 60.0,
                                   coordinates: str = 'local',
                                   force_overwrite: bool = False) -> bool:
    """
    Export OpenSim animation to YAML format similar to armature_export.py
    Uses similar logic as motion.py from lines 132 onward to extract body transforms

    Args:
        osim_file_path: Path to OpenSim model file (.osim)
        mot_file_path: Path to motion file (.mot)
        output_file: Output YAML file path
        frame_start: Starting frame (default 0)
        frame_end: Ending frame (None for all frames)
        target_framerate: Target framerate for export (default 60.0)
        coordinates: Coordinate system - 'local' (parent-relative) or 'global' (ground-relative)
        force_overwrite: Whether to overwrite existing files without asking
        force_overwrite: If True, overwrite without asking (default False)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check for file overwrite permission
        if not check_file_overwrite(output_file, force_overwrite):
            print("Export cancelled.")
            return False
        print(f"Loading OpenSim model: {osim_file_path}")
        print(f"Loading motion data: {mot_file_path}")

        # Load OpenSim model and motion data (similar to motion.py)
        model = osim.Model(osim_file_path)
        motion_data = osim.TimeSeriesTable(mot_file_path)

        # Get model components
        model_bodySet = model.getBodySet()
        bodies = [model_bodySet.get(i) for i in range(model_bodySet.getSize())]

        # Get motion data
        times = motion_data.getIndependentColumn()
        coordinateNames = motion_data.getColumnLabels()
        motion_data_np = motion_data.getMatrix().to_numpy()

        # Convert rotational coordinates from degrees to radians if needed
        model_coordSet = model.getCoordinateSet()
        for i, c in enumerate(coordinateNames):
            try:
                if model_coordSet.get(c).getMotionType() == 1:  # 1: rotation
                    if motion_data.getTableMetaDataAsString('inDegrees') == 'yes':
                        motion_data_np[:, i] = motion_data_np[:, i] * np.pi / 180
            except Exception:
                pass

        # Calculate frame parameters
        fps = round((len(times) - 1) / (times[-1] - times[0])) if len(times) > 1 else target_framerate

        # Apply frame range limits
        if frame_end is None:
            frame_end = len(times) - 1
        frame_end = min(frame_end, len(times) - 1)
        frame_start = max(0, frame_start)

        conv_fac_frame_rate = max(1, fps // target_framerate)

        print(f"Motion data: {len(times)} frames at {fps:.1f} fps")
        print(f"Exporting frames {frame_start} to {frame_end} at {target_framerate} fps")
        print(f"Bodies: {len(bodies)}, Coordinates: {len(coordinateNames)}")

        # Initialize OpenSim model state
        state = model.initSystem()

        # Build body hierarchy for local coordinate calculations
        parent_to_children, child_to_parent = get_body_hierarchy(model)

        # Coordinate transformation matrix (Y-up to Y-up, identity since OpenSim is already Y-up)
        H_transform = np.eye(4)

        # Collect animation frames
        frames = []

        # Process frames with subsampling
        for n in range(frame_start, frame_end + 1, conv_fac_frame_rate):
            if n >= len(times):
                break

            # Calculate time in seconds relative to start
            time = times[n] - times[frame_start]

            # Set model state for this time frame (similar to motion.py lines 134-140)
            for c, coord in enumerate(coordinateNames):
                try:
                    model.getCoordinateSet().get(coord).setValue(
                        state, motion_data_np[n, c], enforceContraints=False)
                except Exception:
                    pass

            # Realize position to get body transforms
            model.realizePosition(state)

            # Extract body transforms for this frame
            changes = []

            if coordinates == 'local':
                # Get all global transforms first
                global_transforms = get_body_global_transforms(model, state, bodies)

                # Convert to local coordinates
                for body in bodies:
                    body_name = body.getName()
                    hik_name = bone_to_hik_map.get(body_name, body_name)

                    if not hik_name:
                        continue

                    # Skip ground body as it's typically not animated
                    if body_name.lower() == 'ground':
                        continue

                    # Get this body's global transform
                    global_H = global_transforms[body_name]

                    # Convert to local coordinates relative to parent
                    if body_name in child_to_parent:
                        parent_name = child_to_parent[body_name]
                        parent_global_H = global_transforms[parent_name]
                        local_H = global_to_local_transform(global_H, parent_global_H)
                    else:
                        # Root body uses global coordinates
                        local_H = global_H

                    # Extract position (convert to cm)
                    position = [float(local_H[0, 3])*100, float(local_H[1, 3])*100, float(local_H[2, 3])*100]

                    # Extract rotation matrix and convert to quaternion
                    R = local_H[0:3, 0:3]
                    quat = rotation_matrix_to_quaternion(R)

                    # Quaternion format
                    rotation = [round(q, 6) for q in quat]

                    # Create change entry
                    change = {
                        'name': hik_name,
                        'position': [round(p, 6) for p in position],
                        'rotation': [round(r, 3) for r in rotation]
                    }
                    changes.append(change)

            else:  # global coordinates (original behavior)
                for body in bodies:
                    body_name = body.getName()
                    hik_name = bone_to_hik_map.get(body_name, body_name)

                    if not hik_name:
                        continue

                    # Skip ground body as it's typically not animated
                    if body_name.lower() == 'ground':
                        continue

                    # Get transform in ground frame (similar to motion.py lines 143-153)
                    H_swig = body.getTransformInGround(state)
                    T = H_swig.T().to_numpy()
                    R_swig = H_swig.R()
                    R = np.array([[R_swig.get(0, 0), R_swig.get(0, 1), R_swig.get(0, 2)],
                                  [R_swig.get(1, 0), R_swig.get(1, 1), R_swig.get(1, 2)],
                                  [R_swig.get(2, 0), R_swig.get(2, 1), R_swig.get(2, 2)]])

                    H = np.block([[R, T.reshape(3, 1)], [np.zeros(3), 1]])

                    position = [float(H[0, 3])*100, float(H[1, 3])*100, float(H[2, 3])*100]

                    # Extract rotation as quaternion
                    quat = rotation_matrix_to_quaternion(R)

                    # Create change entry (similar to armature_export.py format)
                    change = {
                        'name': hik_name,
                        'position': [round(p, 6) for p in position],  # meters, 6 decimal precision
                        'rotation': [round(q, 6) for q in quat]   # quaternion (w, x, y, z), 6 decimal precision
                    }

                    changes.append(change)

            # Create frame data (similar to armature_export.py format)
            frame_data = {
                'time': round(time, 3),
                'changes': changes
            }

            frames.append(frame_data)

            if len(frames) % 100 == 0:
                print(f"Processed {len(frames)} frames...")

        # Build animation structure (similar to armature_export.py)
        animation = {
            'frames': frames
        }

        # Generate skeleton structure for rest pose
        print("Generating skeleton rest pose...")

        # Create rest pose state (default coordinate values)
        rest_state = model.initSystem()
        coord_set = model.getCoordinateSet()
        for i in range(coord_set.getSize()):
            coord = coord_set.get(i)
            coord.setValue(rest_state, coord.getDefaultValue(), enforceContraints=False)
        model.realizePosition(rest_state)

        # Build body hierarchy
        parent_to_children, child_to_parent = get_body_hierarchy(model)

        # Find root body
        root_body = find_root_body(model, child_to_parent)
        if not root_body:
            print("Warning: Could not find root body, skeleton export will be skipped")
            skeleton = None
        else:
            # Build skeleton hierarchy starting from root
            root_node = build_skeleton_node(root_body, model, rest_state, parent_to_children, coordinates)

            skeleton = {
                'name': 'opensim_skeleton',
                'up': 'y',           # Y-up coordinate system (OpenSim native)
                'forward': 'z',      # Z-forward (OpenSim convention)
                'handiness': 'right', # Right-handed coordinate system
                'transform': coordinates, # Coordinate system (local or global)
                'rotation': 'quaternion', # Rotation format (quaternion w,x,y,z)
                'units': 'cm',       # Centimeters
                'root': root_node
            }

        output_data = {}

        if skeleton:
            output_data['skeleton'] = skeleton

        output_data["frames"] = animation['frames']

        # Write to YAML (similar to armature_export.py)
        with open(output_file, 'w') as f:
            yaml.dump(output_data, f, default_flow_style=False,
                     sort_keys=False, allow_unicode=True)

        print(f"Successfully exported animation and skeleton to: {output_file}")
        print(f"Exported {len(frames)} frames with {len(changes)} bodies each")
        print(f"Duration: {frames[-1]['time']:.3f} seconds" if frames else "No frames exported")
        if skeleton:
            print(f"Skeleton exported with root: {root_body} -> {bone_to_hik_map.get(root_body, root_body)}")
        else:
            print("Warning: Skeleton export was skipped due to missing root body")

        return True

    except Exception as e:
        print(f"Error exporting OpenSim animation: {e}")
        traceback.print_exc()
        return False


def get_body_hierarchy(model):
    """
    Build a hierarchy map from the OpenSim model joints.
    Returns: (parent_to_children, child_to_parent) dictionaries
    """
    parent_to_children = {}
    child_to_parent = {}

    joint_set = model.getJointSet()
    for i in range(joint_set.getSize()):
        joint = joint_set.get(i)
        parent_body = joint.getParentFrame().findBaseFrame().getName()
        child_body = joint.getChildFrame().findBaseFrame().getName()

        # Skip ground connections for cleaner hierarchy
        if parent_body == 'ground':
            continue

        if parent_body not in parent_to_children:
            parent_to_children[parent_body] = []
        parent_to_children[parent_body].append(child_body)
        child_to_parent[child_body] = parent_body

    return parent_to_children, child_to_parent


def find_root_body(model, child_to_parent):
    """
    Find the root body (connected to ground) in the OpenSim model.
    """
    joint_set = model.getJointSet()
    for i in range(joint_set.getSize()):
        joint = joint_set.get(i)
        parent_body = joint.getParentFrame().findBaseFrame().getName()
        child_body = joint.getChildFrame().findBaseFrame().getName()

        if parent_body == 'ground':
            return child_body

    return None


def build_skeleton_node(body_name, model, state, parent_to_children, coordinates='local',
                       child_to_parent=None, global_transforms=None):
    """
    Recursively build a skeleton node with its children.

    Args:
        body_name: Name of the body to build node for
        model: OpenSim model
        state: Model state for rest pose
        parent_to_children: Dictionary mapping parent body names to child body lists
        coordinates: 'local' for parent-relative or 'global' for ground-relative coordinates
        child_to_parent: Dictionary mapping child body names to parent body names (for local coords)
        global_transforms: Pre-computed global transforms (for local coords)
    """
    # Get the HIK name from mapping
    hik_name = bone_to_hik_map.get(body_name, body_name)

    if not hik_name:
        return None

    if coordinates == 'local':
        # Use pre-computed global transforms and convert to local
        if global_transforms is None:
            # Compute global transforms if not provided
            bodies = [model.getBodySet().get(i) for i in range(model.getBodySet().getSize())]
            global_transforms = get_body_global_transforms(model, state, bodies)

        if child_to_parent is None:
            # Get body hierarchy if not provided
            _, child_to_parent = get_body_hierarchy(model)

        # Get this body's global transform
        global_H = global_transforms[body_name]

        # Convert to local coordinates relative to parent
        if body_name in child_to_parent:
            parent_name = child_to_parent[body_name]
            parent_global_H = global_transforms[parent_name]
            local_H = global_to_local_transform(global_H, parent_global_H)
        else:
            # Root body uses global coordinates
            local_H = global_H

        # Extract position (convert to cm)
        position = [
            round(float(local_H[0, 3]) * 100, 3),  # X in cm
            round(float(local_H[1, 3]) * 100, 3),  # Y in cm (up)
            round(float(local_H[2, 3]) * 100, 3)   # Z in cm
        ]

        # Extract rotation matrix and convert to quaternion
        R = local_H[0:3, 0:3]
        quat = rotation_matrix_to_quaternion(R)
        rotation = [round(q, 6) for q in quat]  # Quaternion (w, x, y, z)

    else:  # global coordinates (original behavior)
        # Get body transform in ground frame
        body_set = model.getBodySet()
        body = body_set.get(body_name)

        # Get transform in ground frame for rest pose
        H_swig = body.getTransformInGround(state)
        T = H_swig.T().to_numpy()
        R_swig = H_swig.R()
        R = np.array([[R_swig.get(0, 0), R_swig.get(0, 1), R_swig.get(0, 2)],
                      [R_swig.get(1, 0), R_swig.get(1, 1), R_swig.get(1, 2)],
                      [R_swig.get(2, 0), R_swig.get(2, 1), R_swig.get(2, 2)]])

        # Position in centimeters, Y-up coordinates (OpenSim native)
        position = [
            round(float(T[0]) * 100, 3),  # X in cm
            round(float(T[1]) * 100, 3),  # Y in cm (up)
            round(float(T[2]) * 100, 3)   # Z in cm
        ]

        # Extract rotation as quaternion
        quat = rotation_matrix_to_quaternion(R)
        rotation = [round(q, 6) for q in quat]  # Quaternion (w, x, y, z)

    # Store global origin for BVH
    if coordinates == 'local' and global_transforms:
        global_origin = global_transforms[body_name][0:3, 3] * 100  # cm
        parent_global_origin = None
        if body_name in child_to_parent:
            parent_name = child_to_parent[body_name]
            parent_global_origin = global_transforms[parent_name][0:3, 3] * 100  # cm
    else:
        # For global coordinates, use position as global origin
        global_origin = np.array(position)
        parent_global_origin = None

    # Build the skeleton node
    node = {
        'name': hik_name,
        'hikname': hik_name,
        'position': position,
        'rotation': rotation,
        'rotation_matrix': R,
        'global_origin': global_origin,  # For BVH OFFSET calculation
        'parent_global_origin': parent_global_origin,
        'children': []
    }

    # Recursively add children
    if body_name in parent_to_children:
        for child_body in parent_to_children[body_name]:
            child_node = build_skeleton_node(child_body, model, state, parent_to_children,
                                           coordinates, child_to_parent, global_transforms)
            if child_node:
                node['children'].append(child_node)

    return node


def export_opensim_skeleton_to_yaml(osim_file_path: str, output_file: str,
                                   skeleton_name: str = "opensim_skeleton",
                                   coordinates: str = 'local',
                                   force_overwrite: bool = False) -> bool:
    """
    Export OpenSim model rest pose as skeleton hierarchy YAML.

    Args:
        osim_file_path: Path to OpenSim model file (.osim)
        output_file: Output YAML file path
        skeleton_name: Name for the skeleton (default: "opensim_skeleton")
        coordinates: Coordinate system - 'local' (parent-relative) or 'global' (ground-relative)
        force_overwrite: If True, overwrite without asking (default False)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check for file overwrite permission
        if not check_file_overwrite(output_file, force_overwrite):
            print("Export cancelled.")
            return False

        print(f"Loading OpenSim model: {osim_file_path}")

        # Load OpenSim model
        model = osim.Model(osim_file_path)

        # Initialize model state (rest pose - default coordinate values)
        state = model.initSystem()

        # Set all coordinates to their default values for rest pose
        coord_set = model.getCoordinateSet()
        for i in range(coord_set.getSize()):
            coord = coord_set.get(i)
            coord.setValue(state, coord.getDefaultValue(), enforceContraints=False)

        # Realize position to get body transforms
        model.realizePosition(state)

        # Build body hierarchy
        parent_to_children, child_to_parent = get_body_hierarchy(model)

        # Find root body
        root_body = find_root_body(model, child_to_parent)
        if not root_body:
            print("Error: Could not find root body in OpenSim model")
            return False

        print(f"Root body: {root_body}")
        print(f"Body hierarchy: {len(parent_to_children)} parent bodies")

        # Build skeleton hierarchy starting from root
        root_node = build_skeleton_node(root_body, model, state, parent_to_children, coordinates, child_to_parent)

        # Create skeleton structure in unified format
        output_data = {
            'skeleton': {
                'name': skeleton_name,
                'up': 'y',           # Y-up coordinate system (OpenSim native)
                'forward': 'z',      # Z-forward (OpenSim convention)
                'handiness': 'right', # Right-handed coordinate system
                'transform': coordinates, # Coordinate system (local or global)
                'rotation': 'quaternion', # Rotation format (quaternion w,x,y,z)
                'units': 'cm',       # Centimeters
                'root': root_node
            }
        }

        # Write to YAML
        with open(output_file, 'w') as f:
            yaml.dump(output_data, f, default_flow_style=False,
                     sort_keys=False, allow_unicode=True)

        print(f"Successfully exported skeleton to: {output_file}")
        print(f"Root body: {root_body} -> {bone_to_hik_map.get(root_body, root_body)}")

        return True

    except Exception as e:
        print(f"Error exporting OpenSim skeleton: {e}")
        traceback.print_exc()
        return False


def rotation_matrix_to_euler_xyz(R):
    """
    Convert a 3x3 rotation matrix to XYZ Euler angles (in degrees) for BVH format.
    Extracts angles for rotation order: R = Rx(x) * Ry(y) * Rz(z)
    This matches BVH's CHANNELS Xrotation Yrotation Zrotation convention.
    """
    # For R = Rx * Ry * Rz, the key matrix elements are:
    # R[0,2] = sin(y)
    # R[1,2] = -sin(x)*cos(y)
    # R[2,2] = cos(x)*cos(y)
    # R[0,1] = -cos(y)*sin(z)
    # R[0,0] = cos(y)*cos(z)

    sy = R[0, 2]

    if abs(sy) < 1.0:
        y = math.asin(sy)
        x = math.atan2(-R[1, 2], R[2, 2])
        z = math.atan2(R[0, 1], R[0, 0])  # Note: positive sign, not negative
    else:
        # Gimbal lock
        y = math.copysign(math.pi / 2, sy)
        x = math.atan2(R[2, 1], R[1, 1])
        z = 0

    # Convert to degrees
    return (math.degrees(x), math.degrees(y), math.degrees(z))


def write_bvh_hierarchy(f, node, indent=0, is_root=True, parent_global_origin=None):
    """
    Recursively write BVH hierarchy section for a skeleton node.

    Args:
        f: File handle to write to
        node: Skeleton node dictionary
        indent: Current indentation level
        is_root: Whether this is the root node
        parent_global_origin: Parent's global origin for offset calculation
    """
    indent_str = "  " * indent
    node_type = "ROOT" if is_root else "JOINT"

    # Write node declaration
    f.write(f"{indent_str}{node_type} {node['name']}\n")
    f.write(f"{indent_str}{{\n")

    # Calculate offset as difference between global origins
    if is_root:
        # Root offset is its global position
        offset = node['global_origin']
    elif parent_global_origin is not None:
        # Child offset = child_global - parent_global
        offset = node['global_origin'] - parent_global_origin
    else:
        # Fallback to stored position
        offset = np.array(node['position'])

    f.write(f"{indent_str}  OFFSET {offset[0]:.6f} {offset[1]:.6f} {offset[2]:.6f}\n")

    # Write channels
    if is_root:
        # Root has 6 channels: 3 position + 3 rotation
        f.write(f"{indent_str}  CHANNELS 6 Xposition Yposition Zposition Xrotation Yrotation Zrotation\n")
    else:
        # Other joints have 3 rotation channels
        f.write(f"{indent_str}  CHANNELS 3 Xrotation Yrotation Zrotation\n")

    # Process children
    if node.get('children'):
        for child in node['children']:
            write_bvh_hierarchy(f, child, indent + 1, is_root=False, parent_global_origin=node['global_origin'])
    else:
        # End site (leaf node) - use a small offset
        f.write(f"{indent_str}  End Site\n")
        f.write(f"{indent_str}  {{\n")
        f.write(f"{indent_str}    OFFSET 0.0 5.0 0.0\n")  # Small offset for end effector
        f.write(f"{indent_str}  }}\n")

    f.write(f"{indent_str}}}\n")


def collect_bvh_channel_data(node, frame_data, rest_rotations, is_root=True, log=False):
    """
    Collect channel data for a node and its children in BVH order.

    Args:
        node: Skeleton node
        frame_data: Dictionary mapping bone names to their transform data
        rest_rotations: Dictionary mapping bone names to rest pose rotation matrices
        is_root: Whether this is the root node

    Returns:
        List of channel values in BVH order
    """
    values = []

    # Find this node's data in the frame
    node_data = None
    for change in frame_data:
        if change['name'] == node['name']:
            node_data = change
            break

    if node_data:
        if is_root:
            # Root: position (relative to rest pose offset)
            # OFFSET in HIERARCHY already defines rest position, so subtract it
            pos = node_data['position']
            rest_pos = node.get('global_origin', np.array([0, 0, 0]))
            relative_pos = np.array(pos) - rest_pos
            values.extend([relative_pos[0], relative_pos[1], relative_pos[2]])

        # Convert quaternion to rotation matrix (this is the full local rotation)
        quat = node_data['rotation']  # (w, x, y, z)
        w, x, y, z = quat[0], quat[1], quat[2], quat[3]
        R_anim = np.array([
            [1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)],
            [2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)],
            [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)]
        ])

        # Compute rotation relative to rest pose: R_relative = R_rest^T @ R_anim
        R_rest = rest_rotations.get(node['name'])
        if R_rest is not None:
            R_relative = R_rest.T @ R_anim
        else:
            R_relative = R_anim

        # Convert relative rotation to Euler XYZ (for BVH Xrotation Yrotation Zrotation)
        # BVH applies rotations in order: Rx * Ry * Rz
        euler_xyz = rotation_matrix_to_euler_xyz(R_relative)
        values.extend(euler_xyz)
    else:
        # No data for this node - use zeros
        if is_root:
            values.extend([0, 0, 0])  # Position
        values.extend([0, 0, 0])  # Rotation

    if log:
        print(f"Node {node['name']} values: {values}")

    if  node['name'] in ['LeftUpLeg', 'RightUpLeg', 'LeftArm', 'Spine']:
        print(f"\n=== {node['name']} ===")
        print(f"Rest quaternion: {node.get('rotation')}")
        print(f"Rest rotation matrix:\n{R_rest}")
        print(f"Animation quaternion: {quat}")
        print(f"Animation rotation matrix:\n{R_anim}")
        print(f"Relative rotation matrix:\n{R_relative}")
        euler = rotation_matrix_to_euler_xyz(R_relative)
        print(f"Output Euler XYZ (degrees): {euler}")
        # Also try other orderings
        print(f"If ZXY: {rotation_matrix_to_euler_zxy(R_relative)}")

        # Test simple rotations
        Rx_90 = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])  # -90° around X
        Rz_60 = np.array([[0.5, -0.866, 0], [0.866, 0.5, 0], [0, 0, 1]])  # 60° around Z

        print(f"\nTest Rx(-90°): {rotation_matrix_to_euler_zxy(Rx_90)}")
        print(f"Test Rz(60°): {rotation_matrix_to_euler_zxy(Rz_60)}")
        print(f"Test Rx*Rz: {rotation_matrix_to_euler_zxy(Rx_90 @ Rz_60)}")

        print(f"\nActual R_relative for {node['name']}:")

    # Recursively collect from children
    if node.get('children'):
        for child in node['children']:
            values.extend(collect_bvh_channel_data(child, frame_data, rest_rotations, is_root=False, log=log))
    return values


def export_opensim_animation_to_bvh(osim_file_path: str, mot_file_path: str,
                                   output_file: str, frame_start: int = 0,
                                   frame_end: int | None = None,
                                   target_framerate: float = 60.0,
                                   force_overwrite: bool = False) -> bool:
    """
    Export OpenSim animation to BVH format.

    Args:
        osim_file_path: Path to OpenSim model file (.osim)
        mot_file_path: Path to motion file (.mot)
        output_file: Output BVH file path
        frame_start: Starting frame (default 0)
        frame_end: Ending frame (None for all frames)
        target_framerate: Target framerate for export (default 60.0)
        force_overwrite: Whether to overwrite existing files without asking

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check for file overwrite permission
        if not check_file_overwrite(output_file, force_overwrite):
            print("Export cancelled.")
            return False

        print(f"Loading OpenSim model: {osim_file_path}")
        print(f"Loading motion data: {mot_file_path}")

        # Load OpenSim model and motion data
        model = osim.Model(osim_file_path)
        motion_data = osim.TimeSeriesTable(mot_file_path)

        # Get model components
        model_bodySet = model.getBodySet()
        bodies = [model_bodySet.get(i) for i in range(model_bodySet.getSize())]

        # Get motion data
        times = motion_data.getIndependentColumn()
        coordinateNames = motion_data.getColumnLabels()
        motion_data_np = motion_data.getMatrix().to_numpy()

        # Convert rotational coordinates from degrees to radians if needed
        model_coordSet = model.getCoordinateSet()
        for i, c in enumerate(coordinateNames):
            try:
                if model_coordSet.get(c).getMotionType() == 1:  # 1: rotation
                    if motion_data.getTableMetaDataAsString('inDegrees') == 'yes':
                        motion_data_np[:, i] = motion_data_np[:, i] * np.pi / 180
            except Exception:
                pass

        # Calculate frame parameters
        fps = round((len(times) - 1) / (times[-1] - times[0])) if len(times) > 1 else target_framerate

        # Apply frame range limits
        if frame_end is None:
            frame_end = len(times) - 1
        frame_end = min(frame_end, len(times) - 1)
        frame_start = max(0, frame_start)

        conv_fac_frame_rate = max(1, fps // target_framerate)
        frame_time = 1.0 / target_framerate

        print(f"Motion data: {len(times)} frames at {fps:.1f} fps")
        print(f"Exporting frames {frame_start} to {frame_end} at {target_framerate} fps")
        print(f"Bodies: {len(bodies)}, Coordinates: {len(coordinateNames)}")

        # Initialize OpenSim model state
        state = model.initSystem()

        # Build body hierarchy for local coordinate calculations
        parent_to_children, child_to_parent = get_body_hierarchy(model)

        # Build rest pose skeleton for hierarchy
        rest_state = model.initSystem()
        coord_set = model.getCoordinateSet()
        for i in range(coord_set.getSize()):
            coord = coord_set.get(i)
            coord.setValue(rest_state, coord.getDefaultValue(), enforceContraints=False)
        model.realizePosition(rest_state)

        # Find root body
        root_body = find_root_body(model, child_to_parent)
        if not root_body:
            print("Error: Could not find root body in OpenSim model")
            return False

        # Build skeleton hierarchy for BVH (always use local coordinates for BVH)
        root_node = build_skeleton_node(root_body, model, rest_state, parent_to_children,
                                       'local', child_to_parent)

        # Collect animation frames
        frames_data = []

        print("Processing animation frames...")
        for n in range(frame_start, frame_end + 1, conv_fac_frame_rate):
            if n >= len(times):
                break

            # Set model state for this time frame
            for c, coord in enumerate(coordinateNames):
                try:
                    model.getCoordinateSet().get(coord).setValue(
                        state, motion_data_np[n, c], enforceContraints=False)
                except Exception:
                    pass

            # Realize position to get body transforms
            model.realizePosition(state)

            # Extract body transforms using local coordinates
            global_transforms = get_body_global_transforms(model, state, bodies)
            changes = []

            for body in bodies:
                body_name = body.getName()
                hik_name = bone_to_hik_map.get(body_name, body_name)

                if not hik_name or body_name.lower() == 'ground':
                    continue

                # Get this body's global transform
                global_H = global_transforms[body_name]

                # Convert to local coordinates relative to parent
                if body_name in child_to_parent:
                    parent_name = child_to_parent[body_name]
                    parent_global_H = global_transforms[parent_name]
                    local_H = global_to_local_transform(global_H, parent_global_H)
                else:
                    # Root body uses global coordinates
                    local_H = global_H

                # Extract position (convert to cm)
                position = [float(local_H[0, 3])*100, float(local_H[1, 3])*100, float(local_H[2, 3])*100]

                # Extract rotation matrix and convert to quaternion
                R = local_H[0:3, 0:3]
                quat = rotation_matrix_to_quaternion(R)

                # Create change entry
                change = {
                    'name': hik_name,
                    'position': position,
                    'rotation': quat
                }
                changes.append(change)

            frames_data.append(changes)

            if len(frames_data) % 100 == 0:
                print(f"Processed {len(frames_data)} frames...")

        # Extract rest rotations from skeleton
        def extract_rest_rotations(node, rotations_dict):
            """Recursively extract rest pose rotation matrices."""
            if 'rotation_matrix' in node and node['rotation_matrix'] is not None:
                rotations_dict[node['name']] = node['rotation_matrix']
            for child in node.get('children', []):
                extract_rest_rotations(child, rotations_dict)

        rest_rotations = {}
        extract_rest_rotations(root_node, rest_rotations)

        # Write BVH file
        print(f"Writing BVH file: {output_file}")
        with open(output_file, 'w') as f:
            # Write header
            f.write("HIERARCHY\n")

            # Write skeleton hierarchy
            write_bvh_hierarchy(f, root_node, indent=0, is_root=True)

            # Write motion section
            f.write("MOTION\n")
            f.write(f"Frames: {len(frames_data)}\n")
            f.write(f"Frame Time: {frame_time:.6f}\n")

            # Write frame data
            first_frame = True
            for frame_data in frames_data:
                values = collect_bvh_channel_data(root_node, frame_data, rest_rotations, is_root=True, log=first_frame)
                f.write(" ".join(f"{v:.6f}" for v in values) + "\n")
                first_frame = False

        print(f"Successfully exported animation to BVH: {output_file}")
        print(f"Exported {len(frames_data)} frames at {target_framerate} fps")

        return True

    except Exception as e:
        print(f"Error exporting OpenSim animation to BVH: {e}")
        traceback.print_exc()
        return False


def main():
    """Main function to handle command line arguments and run the export."""
    parser = argparse.ArgumentParser(
        description="Export OpenSim model animation and/or skeleton to unified YAML format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export animation with skeleton (default: local coordinates)
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml \\
      --start-frame 10 --end-frame 100
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml \\
      --framerate 30.0

  # Export skeleton rest pose only (default: local coordinates)
  python opensim_animation_exporter.py --skeleton --model model.osim -o skeleton.yaml

  # Export using global coordinates instead of local
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml \\
      --coordinates global

  # Force overwrite existing files
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml --force
        """)

    parser.add_argument('--model', '-m', type=str, required=True,
                        help='Path to OpenSim model file (.osim)')
    parser.add_argument('--motion', type=str,
                        help='Path to motion file (.mot) - required for animation export')
    parser.add_argument('-o', '--output', type=str, required=True,
                        help='Output file path (.yaml or .bvh)')
    parser.add_argument('--format', type=str, choices=['yaml', 'bvh'],
                        help='Output format: yaml or bvh (auto-detected from file extension if not specified)')
    parser.add_argument('--skeleton', action='store_true',
                        help='Export skeleton rest pose instead of animation (YAML format only)')
    parser.add_argument('--start-frame', type=int, default=0,
                        help='Starting frame number (default: 0)')
    parser.add_argument('--end-frame', type=int, default=None,
                        help='Ending frame number (default: all frames)')
    parser.add_argument('--framerate', type=float, default=60.0,
                        help='Target framerate for export (default: 60.0)')
    parser.add_argument('--skeleton-name', type=str, default='opensim_skeleton',
                        help='Name for skeleton export (default: opensim_skeleton)')
    parser.add_argument('--coordinates', type=str, choices=['local', 'global'],
                        default='local',
                        help='Coordinate system: local (parent-relative) or global (ground-relative) (default: local, BVH always uses local)')
    parser.add_argument('--force', '-f', action='store_true',
                        help='Force overwrite existing files without asking')

    args = parser.parse_args()

    # Check dependencies first
    if not check_dependencies():
        sys.exit(1)

    # Validate input files
    osim_path = Path(args.model)

    if not osim_path.exists():
        print(f"Error: OpenSim model file not found: {args.model}")
        sys.exit(1)

    # Check for file overwrite
    if not check_file_overwrite(args.output, args.force):
        sys.exit(1)

    # Create output directory if needed
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Auto-detect format from file extension if not specified
    output_format = args.format
    if not output_format:
        ext = output_path.suffix.lower()
        if ext == '.bvh':
            output_format = 'bvh'
        elif ext == '.yaml' or ext == '.yml':
            output_format = 'yaml'
        else:
            print(f"Error: Cannot auto-detect format from extension '{ext}'. Use --format to specify.")
            sys.exit(1)

    # Validate format-specific options
    if output_format == 'bvh':
        if args.skeleton:
            print("Error: Skeleton export is only supported for YAML format")
            sys.exit(1)
        if args.coordinates == 'global':
            print("Warning: BVH format always uses local coordinates, ignoring --coordinates global")
            args.coordinates = 'local'

    if args.skeleton:
        # Export skeleton rest pose (YAML only)
        success = export_opensim_skeleton_to_yaml(
            str(osim_path),
            str(output_path),
            args.skeleton_name,
            args.coordinates,
            args.force
        )
    else:
        # Export animation - require motion file
        if not args.motion:
            print("Error: Motion file required for animation export")
            parser.print_help()
            sys.exit(1)

        mot_path = Path(args.motion)
        if not mot_path.exists():
            print(f"Error: Motion file not found: {args.motion}")
            sys.exit(1)

        # Run the appropriate animation export
        if output_format == 'bvh':
            success = export_opensim_animation_to_bvh(
                str(osim_path),
                str(mot_path),
                str(output_path),
                args.start_frame,
                args.end_frame,
                args.framerate,
                args.force
            )
        else:  # yaml
            success = export_opensim_animation_to_yaml(
                str(osim_path),
                str(mot_path),
                str(output_path),
                args.start_frame,
                args.end_frame,
                args.framerate,
                args.coordinates,
                args.force
            )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()