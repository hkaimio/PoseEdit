#!/usr/bin/env python3
"""
OpenSim to BVH Exporter

Exports OpenSim models and animations to BVH format using the bvhsdk library.
Uses OpenSim body names directly as BVH joint names for standard compatibility.

Requirements:
- OpenSim Python API (opensim)
- numpy
- bvhsdk (from workspace)

Usage:
    # Export rest pose only
    python opensim_to_bvh.py --model model.osim -o output.bvh

    # Export animation
    python opensim_to_bvh.py --model model.osim --motion motion.mot -o output.bvh

    # With optional parameters
    python opensim_to_bvh.py --model model.osim --motion motion.mot -o output.bvh \\
        --start-frame 0 --end-frame 100 --framerate 30.0 --root-body pelvis
"""

import argparse
import sys
from pathlib import Path

# Add bvhsdk to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bvhsdk'))

try:
    import opensim as osim
except ImportError:
    print("Error: OpenSim Python API not available. Please install opensim-core.")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("Error: NumPy not available. Please install numpy.")
    sys.exit(1)

try:
    from bvhsdk import anim, bvh, mathutils
except ImportError:
    print("Error: bvhsdk not available. Please ensure bvhsdk is in the workspace.")
    sys.exit(1)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Export OpenSim model and animation to BVH format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--model', required=True, type=Path,
                        help='OpenSim model file (.osim)')
    parser.add_argument('-o', '--output', required=True, type=Path,
                        help='Output BVH file path')
    parser.add_argument('--motion', type=Path,
                        help='Motion file (.mot, .sto) - if omitted, exports rest pose only')
    parser.add_argument('--framerate', type=float, default=30.0,
                        help='Output framerate (default: 30.0 fps)')
    parser.add_argument('--start-frame', type=int, default=0,
                        help='Start frame (default: 0)')
    parser.add_argument('--end-frame', type=int,
                        help='End frame (default: all frames)')
    parser.add_argument('--root-body', type=str, default='pelvis',
                        help='OpenSim root body name (default: pelvis)')

    args = parser.parse_args()

    # Validate inputs
    if not args.model.exists():
        parser.error(f"Model file not found: {args.model}")
    if args.motion and not args.motion.exists():
        parser.error(f"Motion file not found: {args.motion}")

    return args


def build_skeleton_tree(model, root_body_name):
    """
    Build hierarchical skeleton structure from OpenSim model.

    Args:
        model: OpenSim Model object
        root_body_name: Name of the root body

    Returns:
        dict mapping body_name -> {
            'body': OpenSim Body object,
            'parent_body_name': str or None,
            'children': list of child body names,
            'joint': OpenSim Joint object connecting to parent
        }
    """
    skeleton_tree = {}

    # Get all bodies
    body_set = model.getBodySet()

    # Build parent-child relationships from joints
    joint_set = model.getJointSet()

    # Initialize all bodies in tree
    for i in range(body_set.getSize()):
        body = body_set.get(i)
        body_name = body.getName()
        skeleton_tree[body_name] = {
            'body': body,
            'parent_body_name': None,
            'children': [],
            'joint': None
        }

    # Populate parent-child relationships from joints
    for i in range(joint_set.getSize()):
        joint = joint_set.get(i)
        parent_body_name = joint.getParentFrame().findBaseFrame().getName()
        child_body_name = joint.getChildFrame().findBaseFrame().getName()

        # Set parent
        skeleton_tree[child_body_name]['parent_body_name'] = parent_body_name
        skeleton_tree[child_body_name]['joint'] = joint

        # Add to parent's children list
        if parent_body_name in skeleton_tree:
            skeleton_tree[parent_body_name]['children'].append(child_body_name)

    # Verify root body exists
    if root_body_name not in skeleton_tree:
        available_bodies = list(skeleton_tree.keys())[:10]
        raise ValueError(
            f"Root body '{root_body_name}' not found in model. "
            f"Available bodies: {', '.join(available_bodies)}..."
        )

    return skeleton_tree


def get_body_global_transform_matrix(model, state, body_name):
    """
    Extract 4x4 global transform matrix for an OpenSim body.

    Args:
        model: OpenSim Model object
        state: OpenSim State object
        body_name: Name of the body

    Returns:
        4x4 numpy array [R | t; 0 0 0 1] where R is rotation, t is translation
    """
    body = model.getBodySet().get(body_name)
    transform_osim = body.getTransformInGround(state)

    # Convert OpenSim::Transform to 4x4 matrix
    rotation = transform_osim.R()
    translation = transform_osim.T()

    matrix = np.eye(4)
    for i in range(3):
        for j in range(3):
            matrix[i, j] = rotation.get(i, j)
        matrix[i, 3] = translation.get(i)

    # Convert from meters to centimeters (BVH standard)
    matrix[0:3, 3] *= 100.0

    return matrix


def calculate_end_site_from_geometry(body, body_transform):
    """
    Calculate end site position for a leaf node based on body's cylinder geometry.

    Args:
        body: OpenSim Body object
        body_transform: 4x4 global transform matrix of the body

    Returns:
        3D offset vector in body's local frame (in centimeters)
    """
    # Try to get cylinder geometry
    try:
        geometry_list = body.get_attached_geometry()

        for i in range(geometry_list.getSize()):
            geometry = geometry_list.get(i)

            # Check if it's a cylinder
            if geometry.getConcreteClassName() == 'Cylinder':
                # Get cylinder properties
                cylinder = osim.Cylinder.safeDownCast(geometry)
                half_height = cylinder.get_half_height()

                # End site at cylinder tip (2 * half_height along Y axis in body frame)
                # Convert from meters to centimeters
                end_site = np.array([0.0, half_height * 2.0 * 100.0, 0.0])
                return end_site
    except:
        pass

    # Default: 10cm along Y axis if no geometry found
    return np.array([0.0, 10.0, 0.0])


def create_bvh_hierarchy(skeleton_tree, model, root_body_name, num_frames, framerate):
    """
    Create bvhsdk Animation object with proper hierarchy.

    Args:
        skeleton_tree: Skeleton structure from build_skeleton_tree()
        model: OpenSim Model object
        root_body_name: Name of the root body
        num_frames: Number of frames in animation
        framerate: Frames per second

    Returns:
        anim.Animation object
    """
    # Initialize state at default pose
    state = model.initSystem()
    model.realizePosition(state)

    # Create root joint recursively
    root_joint = create_joint_recursive(
        body_name=root_body_name,
        skeleton_tree=skeleton_tree,
        parent=None,
        depth=0,
        model=model,
        state=state
    )

    # Create animation
    animation = anim.Animation(filename="opensim_export", root=root_joint)
    animation.frames = num_frames
    animation.frametime = 1.0 / framerate

    return animation


def create_joint_recursive(body_name, skeleton_tree, parent, depth, model, state):
    """
    Recursively create Joint objects for bvhsdk.

    Args:
        body_name: Name of current body
        skeleton_tree: Skeleton structure
        parent: Parent Joint object (None for root)
        depth: Depth in hierarchy
        model: OpenSim Model object
        state: OpenSim State object (for getting transforms)

    Returns:
        anim.Joints object
    """
    node = skeleton_tree[body_name]

    # Create joint with OpenSim body name
    joint = anim.Joints(name=body_name, depth=depth, parent=parent)

    # Get global transform for this body
    body_transform = get_body_global_transform_matrix(model, state, body_name)
    body_global_pos = body_transform[0:3, 3]

    # Calculate offset in parent's local coordinate frame
    if parent is None:
        # Root offset = global position at rest pose
        offset = body_global_pos
    else:
        # Child offset = bone vector transformed to parent's local frame
        parent_body_name = node['parent_body_name']
        parent_transform = get_body_global_transform_matrix(model, state, parent_body_name)
        parent_global_pos = parent_transform[0:3, 3]
        parent_global_rot = parent_transform[0:3, 0:3]

        # Offset in global frame
        offset_global = body_global_pos - parent_global_pos

        # Transform to parent's local frame
        offset = parent_global_rot.T @ offset_global

    joint.addOffset(offset)

    # Set rotation order and channels
    joint.order = 'ZXY'  # BVH rotation order (supported by bvhsdk)
    joint.n_channels = 6 if parent is None else 3

    # Add end site for leaf nodes
    if len(node['children']) == 0:
        endsite = calculate_end_site_from_geometry(node['body'], body_transform)
        joint.addEndSite(endsite)

    # Recurse for children
    for child_body_name in node['children']:
        create_joint_recursive(child_body_name, skeleton_tree, joint, depth + 1, model, state)

    return joint


def matrix_to_euler_zxy(R):
    """
    Convert 3x3 rotation matrix to Euler ZXY angles (in radians).

    Args:
        R: 3x3 rotation matrix

    Returns:
        (rz, rx, ry) tuple in radians (bvhsdk expects radians)
    """
    # Use bvhsdk's built-in conversion
    euler_rad, warning = mathutils.eulerFromMatrix(R, 'ZXY')
    return tuple(euler_rad)


def set_rest_pose_frame(animation, model, state, frame_idx=0):
    """
    Set animation frame to rest pose (all OpenSim coordinates at default values).
    Compute local rotations from OpenSim's rest pose global transforms.

    Args:
        animation: bvhsdk Animation object
        model: OpenSim Model object
        state: OpenSim State at default pose
        frame_idx: Frame index to set (default 0)
    """
    joints_list = animation.getlistofjoints()

    for joint in joints_list:
        body_name = joint.name

        # Get global transform from OpenSim
        global_transform = get_body_global_transform_matrix(model, state, body_name)
        global_rotation = global_transform[0:3, 0:3]
        global_position = global_transform[0:3, 3]

        # Compute local rotation
        if joint.parent:
            parent_body_name = joint.parent.name
            parent_transform = get_body_global_transform_matrix(model, state, parent_body_name)
            parent_global_rotation = parent_transform[0:3, 0:3]
            local_rotation_matrix = parent_global_rotation.T @ global_rotation
        else:
            # Root uses global rotation directly
            local_rotation_matrix = global_rotation

        # Convert to Euler ZXY (radians)
        euler_zxy = matrix_to_euler_zxy(local_rotation_matrix)

        # Initialize arrays if needed
        if len(joint.rotation) == 0 or joint.rotation.shape[0] == 0:
            joint.rotation = np.zeros((animation.frames, 3))

        joint.rotation[frame_idx] = euler_zxy

        # Set translation (only for root)
        if joint.parent is None:
            if len(joint.translation) == 0 or joint.translation.shape[0] == 0:
                joint.translation = np.zeros((animation.frames, 3))
            # Translation relative to rest pose offset
            joint.translation[frame_idx] = global_position - joint.offset


def populate_animation_from_motion(animation, model, motion_table, skeleton_tree,
                                   start_frame, end_frame):
    """
    Populate animation frames from OpenSim motion data.

    Args:
        animation: bvhsdk Animation object
        model: OpenSim Model object
        motion_table: OpenSim TimeSeriesTable with motion data
        skeleton_tree: Skeleton structure
        start_frame: First frame to export
        end_frame: Last frame to export (inclusive)
    """
    state = model.initSystem()
    coordinate_set = model.getCoordinateSet()

    # Get column labels (coordinate names)
    labels = motion_table.getColumnLabels()

    # Debug: print first few coordinate names
    print(f"  Motion table has {len(labels) if isinstance(labels, tuple) else labels.getSize()} coordinates")

    num_coords_set = 0
    for frame_idx in range(start_frame, end_frame + 1):
        # Get time and state values for this frame
        time = motion_table.getIndependentColumn()[frame_idx]
        row_vec = motion_table.getRowAtIndex(frame_idx)

        # Reset coordinate counter for this frame
        coords_changed = 0

        # Set coordinate values in state
        # labels can be either a tuple or an OpenSim object
        if isinstance(labels, tuple):
            # Python tuple - iterate directly
            for i, coord_name in enumerate(labels):
                try:
                    coord = coordinate_set.get(coord_name)
                    value = row_vec[i]
                    coord.setValue(state, value)
                    coords_changed += 1
                    if frame_idx == start_frame and num_coords_set < 5:
                        print(f"    {coord_name} = {value}")
                        num_coords_set += 1
                except Exception as e:
                    # Coordinate might not exist in model
                    if frame_idx == start_frame:
                        print(f"    Warning: Could not set {coord_name}: {e}")
                    pass
        else:
            # OpenSim object with getSize() method
            for i in range(labels.getSize()):
                coord_name = labels.get(i)
                try:
                    coord = coordinate_set.get(coord_name)
                    value = row_vec.get(i)
                    coord.setValue(state, value)
                    coords_changed += 1
                    if frame_idx == start_frame and num_coords_set < 5:
                        print(f"    {coord_name} = {value}")
                        num_coords_set += 1
                except Exception as e:
                    # Coordinate might not exist in model
                    if frame_idx == start_frame:
                        print(f"    Warning: Could not set {coord_name}: {e}")
                    pass

        if frame_idx == start_frame:
            print(f"  Set {coords_changed} coordinates for frame {frame_idx}")

        # Realize position to update body transforms
        model.realizePosition(state)

        # Set frame data (frame_idx - start_frame + 1 because frame 0 is rest pose)
        output_frame_idx = frame_idx - start_frame + 1
        set_frame_from_state(animation, model, state, output_frame_idx)

        if frame_idx % 100 == 0:
            print(f"  Processed frame {frame_idx - start_frame + 1}/{end_frame - start_frame + 1}")


def set_frame_from_state(animation, model, state, frame_idx):
    """
    Set animation frame data from OpenSim state.

    Args:
        animation: bvhsdk Animation object
        model: OpenSim Model object
        state: OpenSim State object
        frame_idx: Frame index to set
    """
    joints_list = animation.getlistofjoints()

    for joint in joints_list:
        body_name = joint.name

        # Get global transform from OpenSim
        global_transform = get_body_global_transform_matrix(model, state, body_name)
        global_rotation = global_transform[0:3, 0:3]
        global_position = global_transform[0:3, 3]

        # Compute local rotation
        if joint.parent:
            parent_body_name = joint.parent.name
            parent_transform = get_body_global_transform_matrix(model, state, parent_body_name)
            parent_global_rotation = parent_transform[0:3, 0:3]
            local_rotation_matrix = parent_global_rotation.T @ global_rotation
        else:
            # Root uses global rotation directly
            local_rotation_matrix = global_rotation

        # Convert to Euler ZXY
        euler_zxy = matrix_to_euler_zxy(local_rotation_matrix)

        # Set rotation
        joint.rotation[frame_idx] = euler_zxy

        # Set translation (only for root)
        if joint.parent is None:
            # Translation relative to rest pose offset
            joint.translation[frame_idx] = global_position - joint.offset


def export_to_bvh(model_path, output_path, motion_path=None, framerate=30.0,
                  start_frame=0, end_frame=None, root_body='pelvis'):
    """
    Main export function.

    Args:
        model_path: Path to OpenSim model file
        output_path: Path to output BVH file
        motion_path: Path to motion file (optional)
        framerate: Output framerate
        start_frame: First frame to export
        end_frame: Last frame to export (None = all)
        root_body: Name of root body
    """
    print(f"Loading OpenSim model: {model_path}")
    model = osim.Model(str(model_path))

    print("Building skeleton tree...")
    skeleton_tree = build_skeleton_tree(model, root_body)
    print(f"  Found {len(skeleton_tree)} bodies")
    print(f"  Root body: {root_body}")

    # Determine number of frames
    if motion_path:
        print(f"Loading motion data: {motion_path}")
        motion_table = osim.TimeSeriesTable(str(motion_path))
        total_frames = motion_table.getNumRows()

        if end_frame is None:
            end_frame = total_frames - 1
        else:
            end_frame = min(end_frame, total_frames - 1)

        num_output_frames = end_frame - start_frame + 2  # +1 for rest pose at frame 0
        print(f"  Motion has {total_frames} frames")
        print(f"  Exporting frames {start_frame} to {end_frame} ({num_output_frames} total with rest pose)")
    else:
        print("No motion data - exporting rest pose only")
        num_output_frames = 1
        motion_table = None

    print("Creating BVH hierarchy...")
    animation = create_bvh_hierarchy(skeleton_tree, model, root_body,
                                     num_output_frames, framerate)

    print("Setting rest pose (frame 0)...")
    state = model.initSystem()
    model.realizePosition(state)
    set_rest_pose_frame(animation, model, state, frame_idx=0)

    if motion_table:
        print(f"Populating animation frames...")
        populate_animation_from_motion(animation, model, motion_table, skeleton_tree,
                                       start_frame, end_frame)

    print(f"Writing BVH file: {output_path}")
    bvh.WriteBVH(
        animation=animation,
        path=str(output_path.parent),
        name=output_path.stem,
        frametime=1.0 / framerate,
        writeTranslation=False,  # Only root has translation
        refTPose=True,           # First frame is reference pose
        precision=6
    )

    print("✓ Export complete!")


def main():
    """Main entry point."""
    args = parse_arguments()

    try:
        export_to_bvh(
            model_path=args.model,
            output_path=args.output,
            motion_path=args.motion,
            framerate=args.framerate,
            start_frame=args.start_frame,
            end_frame=args.end_frame,
            root_body=args.root_body
        )
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
