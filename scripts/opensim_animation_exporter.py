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
    python opensim_animation_exporter.py model.osim motion.mot output.yaml
    
    # With optional parameters:
    python opensim_animation_exporter.py model.osim motion.mot output.yaml \\
        --start-frame 0 --end-frame 100 --framerate 30.0
"""

import argparse
import math
import sys
import traceback
from pathlib import Path

try:
    import opensim as osim
except ImportError as e:
    print(f"Error: OpenSim Python API not found: {e}")
    print("Please install OpenSim with Python bindings.")
    sys.exit(1)

try:
    import numpy as np
except ImportError as e:
    print(f"Error: numpy not found: {e}")
    print("Please install numpy: pip install numpy")
    sys.exit(1)

try:
    import yaml
except ImportError as e:
    print(f"Error: PyYAML not found: {e}")
    print("Please install PyYAML: pip install pyyaml")
    sys.exit(1)


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
    'pelvis' : 'spine',
    'spine1' : 'spine.001',
    'spine2' : 'spine.002',
    'spine3' : 'spine.003',
    'spine4' : 'spine.004',  
    'spine5' : 'spine.005',
    'spine6' : 'spine.006',
    'r_shoulder' : 'shoulder.R',
    'r_upperarm' : 'upper_arm.R',
    'r_forearm' : 'forearm.R',
    'r_hand' : 'hand.R',
    'l_shoulder' : 'shoulder.L',
    'l_upperarm' : 'upper_arm.L',
    'l_forearm' : 'forearm.L',
    'l_hand' : 'hand.L',
    'r_thigh' : 'thigh.R',
    'r_shin' : 'shin.R',
    'r_foot' : 'foot.R',
    'l_thigh' : 'thigh.L',
    'l_shin' : 'shin.L',
    'l_foot' : 'foot.L',
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
                                   target_framerate: float = 60.0) -> bool:
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

    Returns:
        bool: True if successful, False otherwise
    """
    try:
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
                R_mat = H[0:3, 0:3]
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



        # Write to YAML (similar to armature_export.py)
        with open(output_file, 'w') as f:
            yaml.dump(animation, f, default_flow_style=False,
                     sort_keys=False, allow_unicode=True)

        print(f"Successfully exported animation to: {output_file}")
        print(f"Exported {len(frames)} frames with {len(changes)} bodies each")
        print(f"Duration: {frames[-1]['time']:.3f} seconds" if frames else "No frames exported")

        return True

    except Exception as e:
        print(f"Error exporting OpenSim animation: {e}")
        traceback.print_exc()
        return False


def main():
    """Main function to handle command line arguments and run the export."""
    parser = argparse.ArgumentParser(
        description="Export OpenSim model animation to YAML format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python opensim_animation_exporter.py model.osim motion.mot output.yaml
  python opensim_animation_exporter.py model.osim motion.mot output.yaml --start-frame 10 --end-frame 100
  python opensim_animation_exporter.py model.osim motion.mot output.yaml --framerate 30.0
        """)

    parser.add_argument('osim_file', type=str,
                        help='Path to OpenSim model file (.osim)')
    parser.add_argument('mot_file', type=str,
                        help='Path to motion file (.mot)')
    parser.add_argument('output_file', type=str,
                        help='Output YAML file path')
    parser.add_argument('--start-frame', type=int, default=0,
                        help='Starting frame number (default: 0)')
    parser.add_argument('--end-frame', type=int, default=None,
                        help='Ending frame number (default: all frames)')
    parser.add_argument('--framerate', type=float, default=60.0,
                        help='Target framerate for export (default: 60.0)')

    args = parser.parse_args()

    # Validate input files
    osim_path = Path(args.osim_file)
    mot_path = Path(args.mot_file)

    if not osim_path.exists():
        print(f"Error: OpenSim model file not found: {args.osim_file}")
        sys.exit(1)

    if not mot_path.exists():
        print(f"Error: Motion file not found: {args.mot_file}")
        sys.exit(1)

    # Create output directory if needed
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run the export
    success = export_opensim_animation_to_yaml(
        str(osim_path),
        str(mot_path),
        str(output_path),
        args.start_frame,
        args.end_frame,
        args.framerate
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()