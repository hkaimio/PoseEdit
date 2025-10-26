import bpy
import math
import os


def parse_mot_file(mot_file_path):
    """
    Parse OpenSim MOT file to extract motion data
    Args:
        mot_file_path: Path to the .mot file
    Returns:
        (frame_rate, headers, motion_data, in_degrees) where:
        - frame_rate: inferred frame rate from time column
        - headers: list of coordinate names
        - motion_data: list of [time, *coordinate_values] for each frame
        - in_degrees: whether rotation values are in degrees
    """
    with open(mot_file_path) as f:
        lines = f.readlines()

    # Find endheader line
    header_end_idx = 0
    in_degrees = True  # Default assumption

    for i, line in enumerate(lines):
        if line.strip() == 'endheader':
            header_end_idx = i
            break
        if 'inDegrees' in line:
            in_degrees = 'yes' in line.lower()

    # Parse column headers (next line after endheader)
    header_line = lines[header_end_idx + 1].strip()
    headers = header_line.split('\t')

    # Parse data lines
    motion_data = []
    for line in lines[header_end_idx + 2:]:
        line = line.strip()
        if not line:
            continue

        values = [float(val) for val in line.split('\t')]
        motion_data.append(values)

    # Calculate frame rate from time differences
    frame_rate = 60.0  # Default
    if len(motion_data) >= 2:
        time_diff = motion_data[1][0] - motion_data[0][0]
        if time_diff > 0:
            frame_rate = 1.0 / time_diff

    return frame_rate, headers, motion_data, in_degrees


def create_coordinate_name_mapping(headers, bone_to_opensim_map):
    """
    Create mapping from MOT coordinate names to Blender bone names
    Args:
        headers: List of coordinate column names from MOT file
        bone_to_opensim_map: Dict mapping Blender bone names to OpenSim body names
    Returns:
        Dict mapping MOT coordinate names to (bone_name, coordinate_type, axis)
    """
    coord_mapping = {}

    # Create reverse mapping from OpenSim names to Blender names
    opensim_to_blender = {}
    for blender_name, opensim_name in bone_to_opensim_map.items():
        if opensim_name is not None:
            opensim_to_blender[opensim_name] = blender_name

    for header in headers:
        if header == 'time':
            continue

        # Parse coordinate name patterns:
        # joint_pelvis_coord_0-5 (FreeJoint coordinates)
        # joint_bodyname_coord_rot_x/y/z (CustomJoint rotations)

        if header.startswith('joint_'):
            # Extract body name and coordinate type
            parts = header.split('_')
            if len(parts) >= 4:
                # Everything between 'joint_' and '_coord_*'
                body_name = '_'.join(parts[1:-2])
                coord_spec = parts[-1]  # '0', 'rot', axis name

                if body_name in opensim_to_blender:
                    blender_bone = opensim_to_blender[body_name]

                    if coord_spec.startswith('rot_'):
                        # Rotation coordinate: joint_body_coord_rot_x
                        axis = coord_spec.split('_')[1]  # x, y, z
                        coord_mapping[header] = (blender_bone, 'rotation', axis)
                    elif coord_spec.isdigit():
                        # FreeJoint coordinate: joint_pelvis_coord_0
                        coord_idx = int(coord_spec)
                        if coord_idx < 3:
                            # Translation coordinates (0=x, 1=y, 2=z)
                            axis = ['x', 'y', 'z'][coord_idx]
                            coord_mapping[header] = (blender_bone, 'location', axis)
                        else:
                            # Rotation coordinates (3=rx, 4=ry, 5=rz)
                            axis = ['x', 'y', 'z'][coord_idx - 3]
                            coord_mapping[header] = (blender_bone, 'rotation', axis)

    return coord_mapping


def apply_motion_to_armature(armature_name, coord_mapping, headers, motion_data, frame_rate=60.0,
                           start_frame=1, in_degrees=True):
    """
    Apply motion data to armature bones as keyframes
    Args:
        armature_name: Name of the armature object
        coord_mapping: Dict mapping coordinate names to (bone_name, coord_type, axis)
        headers: List of column headers from MOT file
        motion_data: List of motion frames
        frame_rate: Animation frame rate
        start_frame: Starting frame number in Blender
        in_degrees: Whether rotation values are in degrees
    """
    # Ensure we have a context
    if not bpy.context:
        raise RuntimeError("No Blender context available")
    
    # Ensure we have a valid scene
    if not bpy.context.scene:
        raise RuntimeError("No active scene available")
    
    # Get armature object
    if armature_name not in bpy.data.objects:
        raise ValueError(f"Armature '{armature_name}' not found. Available objects: {list(bpy.data.objects.keys())}")

    armature_obj = bpy.data.objects[armature_name]
    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object '{armature_name}' is not an armature, it's a {armature_obj.type}")

    # Set up scene
    scene = bpy.context.scene
    scene.render.fps = int(frame_rate)

    # Store current mode and switch to pose mode
    current_mode = bpy.context.mode
    current_object = bpy.context.active_object

    print(f"Current mode: {current_mode}")
    print(f"Setting active object to: {armature_obj.name}")
    
    # Ensure we're in object mode first
    if current_mode not in ('OBJECT', 'POSE'):
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception as e:
            print(f"Warning: Could not switch to object mode: {e}")

    # Set the armature as active object
    bpy.context.view_layer.objects.active = armature_obj

    # Select the armature
    bpy.ops.object.select_all(action='DESELECT')
    armature_obj.select_set(True)

    # Switch to pose mode
    try:
        bpy.ops.object.mode_set(mode='POSE')
        print("Successfully switched to POSE mode")
    except Exception as e:
        raise RuntimeError(f"Failed to switch to POSE mode: {e}") from e

    try:
        # Clear existing keyframes on all pose bones
        for pose_bone in armature_obj.pose.bones:
            pose_bone.rotation_euler = (0, 0, 0)
            pose_bone.location = (0, 0, 0)
            if pose_bone.animation_data:
                pose_bone.animation_data.action = None

        # Create header to column index mapping
        header_to_index = {header: i for i, header in enumerate(headers)}

        # Group coordinates by bone for efficiency
        bone_coordinates = {}
        for coord_name, (bone_name, coord_type, axis) in coord_mapping.items():
            if coord_name not in header_to_index:
                continue  # Skip coordinates not found in MOT file

            if bone_name not in bone_coordinates:
                bone_coordinates[bone_name] = {}
            if coord_type not in bone_coordinates[bone_name]:
                bone_coordinates[bone_name][coord_type] = {}
            bone_coordinates[bone_name][coord_type][axis] = header_to_index[coord_name]

        print(f"Applying motion data to {len(bone_coordinates)} bones...")
        print(f"Found coordinates for bones: {list(bone_coordinates.keys())}")

        # Apply keyframes for each frame
        for frame_idx, frame_data in enumerate(motion_data):
            frame_number = start_frame + frame_idx
            scene.frame_set(frame_number)

            # Apply values to each bone
            for bone_name, bone_coords in bone_coordinates.items():
                if bone_name not in armature_obj.pose.bones:
                    continue

                pose_bone = armature_obj.pose.bones[bone_name]

                # Apply rotations
                if 'rotation' in bone_coords:
                    rot_coords = bone_coords['rotation']
                    current_rot = list(pose_bone.rotation_euler)

                    for axis, column_idx in rot_coords.items():
                        value = frame_data[column_idx]

                        if in_degrees:
                            value = math.radians(value)

                        axis_idx = ['x', 'y', 'z'].index(axis)
                        current_rot[axis_idx] = value

                    pose_bone.rotation_euler = current_rot
                    pose_bone.keyframe_insert(data_path="rotation_euler")

                # Apply locations (for root bone)
                if 'location' in bone_coords:
                    loc_coords = bone_coords['location']
                    current_loc = list(pose_bone.location)

                    for axis, column_idx in loc_coords.items():
                        value = frame_data[column_idx]

                        # Convert from meters to Blender units (assuming 1:1)
                        axis_idx = ['x', 'y', 'z'].index(axis)
                        current_loc[axis_idx] = value

                    pose_bone.location = current_loc
                    pose_bone.keyframe_insert(data_path="location")

        print(f"Applied {len(motion_data)} frames of motion data")

    finally:
        # Restore original state
        if current_object:
            bpy.context.view_layer.objects.active = current_object

        if current_mode == 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        elif current_mode == 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')


def import_opensim_motion(mot_file_path, armature_name, bone_to_opensim_map,
                         start_frame=1, clear_existing=True):
    """
    Import OpenSim MOT file motion data to Blender armature
    Args:
        mot_file_path: Path to the .mot file
        armature_name: Name of the target armature
        bone_to_opensim_map: Dict mapping Blender bone names to OpenSim body names
        start_frame: Starting frame number for animation
        clear_existing: Whether to clear existing animation data
    """
    if not os.path.exists(mot_file_path):
        raise FileNotFoundError(f"MOT file not found: {mot_file_path}")

    print(f"Importing motion from: {mot_file_path}")

    # Parse MOT file
    frame_rate, headers, motion_data, in_degrees = parse_mot_file(mot_file_path)
    print(f"Parsed {len(motion_data)} frames at {frame_rate:.1f} fps")
    print(f"Rotation values in {'degrees' if in_degrees else 'radians'}")

    # Create coordinate mapping
    coord_mapping = create_coordinate_name_mapping(headers, bone_to_opensim_map)
    print(f"Mapped {len(coord_mapping)} coordinates to bones")

    # Apply motion to armature
    apply_motion_to_armature(
        armature_name,
        coord_mapping,
        headers,
        motion_data,
        frame_rate,
        start_frame,
        in_degrees
    )

    print("Motion import completed!")



# Example bone mapping (should match your export mapping)
opensim_bone_map = {
    'spine': 'pelvis',
    'spine.001': 'spine1',
    'spine.002': 'spine2',
    'spine.003': 'spine3',
    'spine.004': 'neck',
    'spine.005': 'neck1',
    'spine.006': 'head',
    'shoulder.R': 'r_shoulder',
    'upper_arm.R': 'r_upperarm',
    'forearm.R': 'r_forearm',
    'hand.R': 'r_hand',
    'shoulder.L': 'l_shoulder',
    'upper_arm.L': 'l_upperarm',
    'forearm.L': 'l_forearm',
    'hand.L': 'l_hand',
    'thigh.R': 'r_thigh',
    'shin.R': 'r_shin',
    'foot.R': 'r_foot',
    'thigh.L': 'l_thigh',
    'shin.L': 'l_shin',
    'foot.L': 'l_foot',
}

# Import motion (comment out to avoid crash during debugging)
# import_opensim_motion(
#     "c:/temp/aikido-2024-08-25-harri-tests6/h5koe/pose-3d/blender_osim_test.mot",
#     "metarig",  # Armature name
#     opensim_bone_map,
#     start_frame=1
# )

def test_motion_import_safe():
    """Safe test function with comprehensive error handling"""
    try:
        print("Available objects:", list(bpy.data.objects.keys()))
        
        # Check if armature exists
        armature_name = "metarig"  # or "metarig"
        if armature_name not in bpy.data.objects:
            print(f"Armature '{armature_name}' not found. Available armatures:")
            for obj_name, obj in bpy.data.objects.items():
                if obj.type == 'ARMATURE':
                    print(f"  - {obj_name}")
            return
        
        # Check MOT file
        mot_file = "C:/temp/aikido-2024-08-25-harri-tests6/h5koe/pose-3d/blender_osim_test.mot"
        if not os.path.exists(mot_file):
            print(f"MOT file not found: {mot_file}")
            return
        
        print("Starting motion import test...")
        import_opensim_motion(mot_file, armature_name)
        print("Motion import completed successfully!")

    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()

# Uncomment to test:
test_motion_import_safe()