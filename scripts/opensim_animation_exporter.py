#!/usr/bin/env python3
"""
OpenSim Animation Exporter

Standalone script to export OpenSim model animations to YAML format.
Uses similar logic as motion.py (lines 132 onward) to extract body transforms
and exports them in a format compatible with armature_export.py from Blender.

Requirements:
- OpenSim Python API (opensim)
- numpy
- PyYAML

Usage:
    # Export animation with skeleton
    python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml
    
    # With optional parameters:
    python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml \\
        --start-frame 0 --end-frame 100 --framerate 30.0
        
    # Export skeleton rest pose only
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


# Example bone mapping with None for bones to skip
bone_to_hik_map = {
    'pelvis' : 'Hips',
    'spine1' : 'Spine',
    'spine2' : 'Spine3',
    'spine3' : 'Spine9',
    'spine4' : 'Neck',  
    'spine5' : 'Neck1',
    'spine6' : 'Head',
    'head' : 'Head',
    'neck' : 'Neck',
    'neck1' : 'Neck1',
    'r_shoulder' : 'RightShoulder',
    'r_upperarm' : 'RightArm',
    'r_forearm' : 'RightForeArm',
    'r_hand' : 'RightHand',
    'l_shoulder' : 'LeftShoulder',
    'l_upperarm' : 'LeftArm',
    'l_forearm' : 'LeftForeArm',
    'l_hand' : 'LeftHand',
    'r_thigh' : 'RightUpLeg',
    'r_shin' : 'RightLeg',
    'r_foot' : 'RightFoot',
    'l_thigh' : 'LeftUpLeg',
    'l_shin' : 'LeftLeg',
    'l_foot' : 'LeftFoot',
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



def export_opensim_animation_to_yaml(osim_file_path: str, mot_file_path: str,
                                   output_file: str, frame_start: int = 0,
                                   frame_end: int | None = None,
                                   target_framerate: float = 60.0,
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

            for body in bodies:
                body_name = body.getName()
                body_name = bone_to_hik_map.get(body_name, body_name)

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

                # Extract rotation as Euler angles 
                zxy = rotation_matrix_to_euler_zxy(R)

                # Convert to degrees
                rotation = [math.degrees(zxy[0]), math.degrees(zxy[1]), math.degrees(zxy[2])]

                # Create change entry (similar to armature_export.py format)
                change = {
                    'name': body_name,
                    'position': [round(p, 6) for p in position],  # meters, 6 decimal precision
                    'rotation': [round(r, 3) for r in rotation]   # degrees, 3 decimal precision
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
            root_node = build_skeleton_node(root_body, model, rest_state, parent_to_children)
            
            skeleton = {
                'name': 'opensim_skeleton',
                'up': 'y',           # Y-up coordinate system (OpenSim native)
                'forward': 'z',      # Z-forward (OpenSim convention)
                'handiness': 'right', # Right-handed coordinate system
                'transform': 'global', # Global coordinates
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


def build_skeleton_node(body_name, model, state, parent_to_children):
    """
    Recursively build a skeleton node with its children.
    """
    # Get the HIK name from mapping
    hik_name = bone_to_hik_map.get(body_name, body_name)
    
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
    
    # Extract rotation as ZXY Euler angles and convert to degrees
    zxy = rotation_matrix_to_euler_zxy(R)
    rotation = [
        round(math.degrees(zxy[0]), 3),  # Z rotation
        round(math.degrees(zxy[1]), 3),  # X rotation
        round(math.degrees(zxy[2]), 3)   # Y rotation
    ]
    
    # Build the skeleton node
    node = {
        'name': hik_name,
        'hikname': hik_name,
        'position': position,
        'rotation': rotation,
        'children': []
    }
    
    # Recursively add children
    if body_name in parent_to_children:
        for child_body in parent_to_children[body_name]:
            child_node = build_skeleton_node(child_body, model, state, parent_to_children)
            node['children'].append(child_node)
    
    return node


def export_opensim_skeleton_to_yaml(osim_file_path: str, output_file: str,
                                   skeleton_name: str = "opensim_skeleton",
                                   force_overwrite: bool = False) -> bool:
    """
    Export OpenSim model rest pose as skeleton hierarchy YAML.
    
    Args:
        osim_file_path: Path to OpenSim model file (.osim)
        output_file: Output YAML file path
        skeleton_name: Name for the skeleton (default: "opensim_skeleton")
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
        root_node = build_skeleton_node(root_body, model, state, parent_to_children)
        
        # Create skeleton structure in unified format
        output_data = {
            'skeleton': {
                'name': skeleton_name,
                'up': 'y',           # Y-up coordinate system (OpenSim native)
                'forward': 'z',      # Z-forward (OpenSim convention)
                'handiness': 'right', # Right-handed coordinate system
                'transform': 'global', # Global coordinates
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


def main():
    """Main function to handle command line arguments and run the export."""
    parser = argparse.ArgumentParser(
        description="Export OpenSim model animation and/or skeleton to unified YAML format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export animation with skeleton
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml --start-frame 10 --end-frame 100
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml --framerate 30.0
  
  # Export skeleton rest pose only
  python opensim_animation_exporter.py --skeleton --model model.osim -o skeleton.yaml
  
  # Force overwrite existing files
  python opensim_animation_exporter.py --model model.osim --motion motion.mot -o output.yaml --force
        """)

    parser.add_argument('--model', '-m', type=str, required=True,
                        help='Path to OpenSim model file (.osim)')
    parser.add_argument('--motion', type=str,
                        help='Path to motion file (.mot) - required for animation export')
    parser.add_argument('-o', '--output', type=str, required=True,
                        help='Output YAML file path')
    parser.add_argument('--skeleton', action='store_true',
                        help='Export skeleton rest pose instead of animation')
    parser.add_argument('--start-frame', type=int, default=0,
                        help='Starting frame number (default: 0)')
    parser.add_argument('--end-frame', type=int, default=None,
                        help='Ending frame number (default: all frames)')
    parser.add_argument('--framerate', type=float, default=60.0,
                        help='Target framerate for export (default: 60.0)')
    parser.add_argument('--skeleton-name', type=str, default='opensim_skeleton',
                        help='Name for skeleton export (default: opensim_skeleton)')
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

    if args.skeleton:
        # Export skeleton rest pose
        success = export_opensim_skeleton_to_yaml(
            str(osim_path),
            str(output_path),
            args.skeleton_name,
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

        # Run the animation export
        success = export_opensim_animation_to_yaml(
            str(osim_path),
            str(mot_path),
            str(output_path),
            args.start_frame,
            args.end_frame,
            args.framerate,
            args.force
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()