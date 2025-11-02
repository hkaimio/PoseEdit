import bpy
import yaml
import math
import xml.etree.ElementTree as ET
from mathutils import Matrix, Euler


# Custom YAML representer to ensure strings are quoted
def str_representer(dumper, data):
    if len(data) == 0:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

yaml.add_representer(str, str_representer)

# Custom representer for floats to avoid scientific notation
def float_representer(dumper, value):
    text = '{0:.3f}'.format(value)
    return dumper.represent_scalar('tag:yaml.org,2002:float', text)

yaml.add_representer(float, float_representer)

def get_bone_global_transform(pose_bone):
    """
    Get global position and rotation for a pose bone
    Returns: (position [x, y, z], rotation [rx, ry, rz] in degrees)
    """
    # Get global matrix
    global_matrix = pose_bone.matrix

    # Extract position
    position = [
        global_matrix.translation.x * 100,
        global_matrix.translation.y * 100,
        global_matrix.translation.z * 100
    ]

    # Extract rotation as Euler angles (ZXY order for iClone)
    euler = global_matrix.to_euler('ZXY')
    rotation = [
        math.degrees(euler.x),
        math.degrees(euler.y),
        math.degrees(euler.z)
    ]

    return position, rotation

def find_exported_parent(pose_bone, bone_to_hik_map):
    """
    Find the closest ancestor bone that has a non-None HIK name (is actually exported)
    Args:
        pose_bone: The bone to find the exported parent for
        bone_to_hik_map: Dictionary mapping Blender bone names to HIK bone names
    Returns:
        The exported parent pose bone, or None if no exported parent exists
    """
    current = pose_bone.parent
    while current:
        if current.name in bone_to_hik_map and bone_to_hik_map[current.name] is not None:
            return current
        current = current.parent
    return None

def get_bone_local_transform(pose_bone, bone_to_hik_map=None):
    """
    Get local position and rotation relative to parent bone
    If bone_to_hik_map is provided, calculates relative to the exported parent
    (skipping any intermediate bones with None HIK names)
    Returns: (position [x, y, z], rotation [rx, ry, rz] in degrees)
    """
    # Get local matrix (relative to exported parent or immediate parent)
    if bone_to_hik_map:
        # Find the actual exported parent (skip bones with None HIK names)
        exported_parent = find_exported_parent(pose_bone, bone_to_hik_map)
        if exported_parent:
            local_matrix = exported_parent.matrix.inverted() @ pose_bone.matrix
        else:
            # No exported parent, use global transform
            local_matrix = pose_bone.matrix
    else:
        # Legacy behavior: use immediate parent
        if pose_bone.parent:
            local_matrix = pose_bone.parent.matrix.inverted() @ pose_bone.matrix
        else:
            local_matrix = pose_bone.matrix

    # Extract position
    position = [
        local_matrix.translation.x * 100,  # Convert to centimeters
        local_matrix.translation.z * 100,  # Blender Z -> iClone Y (up)
        -local_matrix.translation.y * 100  # Blender -Y -> iClone Z (forward)
    ]

    # Extract rotation as Euler angles (ZXY order for iClone)
    euler = local_matrix.to_euler('XYZ')
    rotation = [
        math.degrees(euler.x),
        math.degrees(euler.y),
        math.degrees(euler.z)
    ]

    return position, rotation

def build_bone_hierarchy(armature_obj, bone_to_hik_map, use_local_coords=True):
    """
    Build hierarchical bone structure from armature
    Args:
        armature_obj: Blender armature object
        bone_to_hik_map: Dictionary mapping Blender bone names to HIK bone names (None to skip bone but include children)
        use_local_coords: If True, use local coordinates; if False, use global
    Returns:
        (root_bone_dict, bone_list, t_pose_data)
    """
    pose_bones = armature_obj.pose.bones

    # Find root bone (first mapped bone with HIK name and no parent or parent not in map)
    root_bone = None
    for bone_name, hik_name in bone_to_hik_map.items():
        if bone_name in pose_bones and hik_name is not None:
            pose_bone = pose_bones[bone_name]
            # Check if parent is not in map or has None as HIK name
            parent_in_map = pose_bone.parent and pose_bone.parent.name in bone_to_hik_map
            parent_has_hik = parent_in_map and bone_to_hik_map[pose_bone.parent.name] is not None

            if not parent_has_hik:
                root_bone = pose_bone
                break

    if not root_bone:
        raise ValueError("No root bone found in bone mapping (bone with HIK name and no mapped parent)")

    # Build bone list and t_pose_data
    bone_list = []
    t_pose_data = []

    def process_bone(pose_bone, parent_name=""):
        """Recursively process bone and its children"""
        bone_name = pose_bone.name

        # Check if bone is in mapping
        if bone_name not in bone_to_hik_map:
            # Not in map, skip this bone and don't process children
            return None

        hik_name = bone_to_hik_map[bone_name]

        # If HIK name is None, skip this bone but process children
        if hik_name is None:
            # Process children with the same parent as this bone would have had
            children_nodes = []
            for child in pose_bone.children:
                if child.name in bone_to_hik_map:
                    child_result = process_bone(child, parent_name)
                    if child_result:
                        # If it's a single node, add it
                        if isinstance(child_result, dict):
                            children_nodes.append(child_result)
                        # If it's a list of nodes (from nested skipped bones), extend
                        elif isinstance(child_result, list):
                            children_nodes.extend(child_result)

            # Return list of children (will be flattened by parent)
            return children_nodes if children_nodes else None

        # Get transform
        if use_local_coords:
            position, rotation = get_bone_local_transform(pose_bone, bone_to_hik_map)
        else:
            position, rotation = get_bone_global_transform(pose_bone)

        # Add to bone_list
        bone_list.append([bone_name, parent_name, hik_name])

        # Add to t_pose_data
        t_pose_data.extend(position)
        t_pose_data.extend(rotation)

        # Build bone node
        bone_node = {
            'name': bone_name,
            'hikname': hik_name,
            'position': [round(p, 3) for p in position],
            'rotation': [round(r, 3) for r in rotation],
            'children': []
        }

        # Process children
        for child in pose_bone.children:
            if child.name in bone_to_hik_map:
                child_result = process_bone(child, bone_name)
                if child_result:
                    # If child_result is a dict (single bone), append it
                    if isinstance(child_result, dict):
                        bone_node['children'].append(child_result)
                    # If child_result is a list (from skipped bone), extend children
                    elif isinstance(child_result, list):
                        bone_node['children'].extend(child_result)

        # Return single bone node (not a list)
        return bone_node

    root_node = process_bone(root_bone)

    return root_node, bone_list, t_pose_data

def export_armature_tpose_to_yaml(armature_name, bone_to_hik_map, output_file, use_local_coords=True):
    """
    Export armature's current pose as T-pose skeleton YAML
    Args:
        armature_name: Name of the armature object
        bone_to_hik_map: Dictionary {blender_bone_name: hik_bone_name} (use None to skip bone but include children)
        output_file: Output YAML file path
        use_local_coords: If True, use local coordinates; if False, use global
    """
    # Get armature object
    if armature_name not in bpy.data.objects:
        raise ValueError(f"Armature '{armature_name}' not found")

    armature_obj = bpy.data.objects[armature_name]

    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object '{armature_name}' is not an armature")

    # Build hierarchy
    root_node, bone_list, t_pose_data = build_bone_hierarchy(
        armature_obj,
        bone_to_hik_map,
        use_local_coords
    )

    # Build skeleton structure
    skeleton = {
        'skeleton': {
            'name': armature_name,
            'up': 'z',
            'forward': '-y',
            'handiness': 'right',
            'transform': 'local' if use_local_coords else 'global',
            'units': 'cm',
            'root': root_node
        }
    }

    # Write to YAML with explicit quoting for strings
    with open(output_file, 'w') as f:
        yaml.dump(skeleton, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Exported T-pose skeleton to: {output_file}")
    print(f"Total bones: {len(bone_list)}")
    print(f"Skipped bones with None HIK mapping")
    return bone_list, t_pose_data

def export_armature_animation_to_yaml(armature_name, bone_to_hik_map, output_file,
                                     frame_start, frame_end, use_local_coords=True):
    """
    Export armature animation to animation YAML
    Args:
        armature_name: Name of the armature object
        bone_to_hik_map: Dictionary {blender_bone_name: hik_bone_name} (use None to skip bone but include children)
        output_file: Output YAML file path
        frame_start: First frame to export
        frame_end: Last frame to export
        use_local_coords: If True, use local coordinates; if False, use global
    """
    # Get armature object
    if armature_name not in bpy.data.objects:
        raise ValueError(f"Armature '{armature_name}' not found")

    armature_obj = bpy.data.objects[armature_name]

    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object '{armature_name}' is not an armature")

    # Get scene
    scene = bpy.context.scene
    fps = scene.render.fps

    # Build bone list (use first frame to get structure)
    scene.frame_set(frame_start)
    _, bone_list, _ = build_bone_hierarchy(armature_obj, bone_to_hik_map, use_local_coords)

    # Create ordered list of bone names (only bones with HIK names)
    bone_names_ordered = [bone[0] for bone in bone_list]

    # Collect animation data
    frames = []

    for frame_num in range(frame_start, frame_end + 1):
        scene.frame_set(frame_num)

        # Calculate time in seconds
        time = (frame_num - frame_start) / fps

        # Collect bone transforms for this frame
        changes = []

        for bone_name in bone_names_ordered:
            pose_bone = armature_obj.pose.bones[bone_name]

            # Get transform
            if use_local_coords:
                position, rotation = get_bone_local_transform(pose_bone, bone_to_hik_map)
            else:
                position, rotation = get_bone_global_transform(pose_bone)

            change = {
                'name': bone_name,
                'position': [round(p, 3) for p in position],
                'rotation': [round(r, 3) for r in rotation]
            }

            changes.append(change)

        frame_data = {
            'time': round(time, 3),
            'changes': changes
        }

        frames.append(frame_data)

    # Build animation structure
    animation = {
        'frames': frames
    }

    # Write to YAML
    with open(output_file, 'w') as f:
        yaml.dump(animation, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Exported animation to: {output_file}")
    print(f"Frames: {frame_start} to {frame_end} ({len(frames)} frames)")
    print(f"Total bones: {len(bone_list)}")


def zup_to_yup_position(T_zup):


    # Define the rotation matrix for -90 degrees around X-axis
    angle_rad = math.radians(-90)
    R_x_neg_90 = Matrix.Rotation(angle_rad, 4, 'X')

    # Inverse of the rotation matrix
    R_x_neg_90_inv = R_x_neg_90.inverted()

    # Convert the transformation matrix from Z-up to Y-up
    T_yup = R_x_neg_90 @ T_zup @ R_x_neg_90_inv
    return T_yup


def blender_to_opensim_position(blender_pos):
    """Convert Blender position to OpenSim coordinate system"""
    # Blender: X-right, Y-forward, Z-up
    # OpenSim: X-right, Y-up, Z-forward
    # return [
    #     blender_pos[0],    # X stays the same
    #     blender_pos[2],    # Blender Z -> OpenSim Y (up)
    #     -blender_pos[1]    # Blender -Y -> OpenSim Z (forward)
    # ]
    return blender_pos

def blender_to_opensim_rotation(blender_euler):
    """Convert Blender Euler rotation to OpenSim coordinate system"""
    # Convert from Blender coordinate system to OpenSim
    # This is a simplified conversion - may need refinement based on actual joint behavior
    # return [
    #     blender_euler[0],    # X rotation
    #     blender_euler[2],    # Blender Z -> OpenSim Y
    #     -blender_euler[1]    # Blender -Y -> OpenSim Z
    # ]
    return blender_euler

def get_bone_length(pose_bone):
    """Calculate bone length from head to tail"""
    bone_vector = pose_bone.bone.tail_local - pose_bone.bone.head_local
    return bone_vector.length

def get_bone_opensim_transform(pose_bone, bone_collection=None):
    """
    Get bone transform in OpenSim coordinate system
    Returns: (position, rotation, length)
    """
    # Get local transform relative to exported parent
    bone_matrix = pose_bone.matrix
    if bone_collection:
        exported_parent = find_exported_parent_in_collection(pose_bone, bone_collection)
        if exported_parent:
            parent_matrix = exported_parent.matrix
        else:
            parent_matrix = Matrix.Identity(4)
            rot_y_up_mat = Matrix.Rotation(-math.pi/2, 4, 'X')
            bone_matrix =   rot_y_up_mat @ bone_matrix
    else:
        if pose_bone.parent:
            parent_matrix = pose_bone.parent.matrix
        else:
            parent_matrix = Matrix.Identity(4)
            rot_y_up_mat = Matrix.Rotation(-math.pi/2, 4, 'X')
            bone_matrix = rot_y_up_mat @ bone_matrix

    print(f"Bone: {pose_bone.name} trans: {bone_matrix.translation} rot: {bone_matrix.to_euler('XYZ')}")
    #bone_matrix = zup_to_yup_position(bone_matrix)
    print(f"   after coord frame change: trans: {bone_matrix.translation} rot: {bone_matrix.to_euler('XYZ')}")
    bone_trans = bone_matrix.translation
    #parent_matrix = zup_to_yup_position(parent_matrix)
    parent_trans = parent_matrix.translation
    local_matrix = parent_matrix.inverted() @ bone_matrix
    print(f"   local transform: trans: {local_matrix.translation} rot: {local_matrix.to_euler('XYZ')}")
    if pose_bone.name == "shoulder.R":
        print(f"   parent matrix: {parent_matrix}")
        print(f"   global matrix {bone_matrix}")
        print(f"   local matrix {local_matrix}")
        print("Debug upperarm_R")

    # Extract position and rotation
    position = local_matrix.translation
    euler = local_matrix.to_euler('ZYX')

    # Get bone length
    bone_length = get_bone_length(pose_bone)

    return position, euler, bone_length

def get_bone_radius(bone_name):
    """
    Calculate bone radius based on bone name
    Args:
        bone_name: Name of the bone
    Returns:
        Radius for the bone cylinder visualization
    """
    bone_name_lower = bone_name.lower()
    
    # Small radius for finger bones, thumb bones, and palm bones
    if (bone_name_lower.startswith("f_") or 
        bone_name_lower.startswith("thumb") or 
        bone_name_lower.startswith("palm")):
        return 0.005
    
    # Default radius for other bones
    return 0.02

def create_opensim_body(name, bone_length):
    """Create OpenSim Body XML element"""
    body = ET.Element("Body", name=name)

    # Calculate radius based on bone name
    radius = get_bone_radius(name)

    # Add components section with PhysicalOffsetFrame for visualization
    components = ET.SubElement(body, "components")

    # Create cylinder frame for visualization
    cyl_frame_name = f"cyl_{name}_frame"
    cyl_frame = ET.SubElement(components, "PhysicalOffsetFrame", name=cyl_frame_name)

    # Frame geometry
    frame_geom = ET.SubElement(cyl_frame, "FrameGeometry", name="frame_geometry")
    ET.SubElement(frame_geom, "socket_frame").text = ".."
    scale_factors = ET.SubElement(frame_geom, "scale_factors")
    scale_factors.text = "0.20000000000000001 0.20000000000000001 0.20000000000000001"

    # Attached geometry (cylinder)
    attached_geom = ET.SubElement(cyl_frame, "attached_geometry")
    cylinder = ET.SubElement(attached_geom, "Cylinder", name=f"{cyl_frame_name}_geom_1")
    ET.SubElement(cylinder, "socket_frame").text = ".."
    ET.SubElement(cylinder, "radius").text = f"{radius:.6f}"
    # Use half the bone length for half_height
    ET.SubElement(cylinder, "half_height").text = f"{bone_length/2:.6f}"

    # Frame positioning
    ET.SubElement(cyl_frame, "socket_parent").text = ".."
    ET.SubElement(cyl_frame, "translation").text = f"0 {bone_length/2:.6f} 0"
    ET.SubElement(cyl_frame, "orientation").text = "-0 0 -0"

    # Body frame geometry
    body_frame_geom = ET.SubElement(body, "FrameGeometry", name="frame_geometry")
    ET.SubElement(body_frame_geom, "socket_frame").text = ".."
    body_scale = ET.SubElement(body_frame_geom, "scale_factors")
    body_scale.text = "0.20000000000000001 0.20000000000000001 0.20000000000000001"

    # Body properties (defaults as requested)
    ET.SubElement(body, "mass").text = "1"
    ET.SubElement(body, "mass_center").text = "0 0 0"
    ET.SubElement(body, "inertia").text = "1 1 1 0 0 0"

    return body

def create_opensim_free_joint(name, parent_body, child_body, parent_pos, parent_rot, child_pos, child_rot):
    """Create OpenSim FreeJoint XML element for root bone"""
    joint = ET.Element("FreeJoint", name=name)

    # Socket connections
    ET.SubElement(joint, "socket_parent_frame").text = f"{name}_parent_offset"
    ET.SubElement(joint, "socket_child_frame").text = f"{name}_child_offset"

    # Coordinates (6 DOF for free joint)
    coordinates = ET.SubElement(joint, "coordinates")
    for i in range(6):
        coord = ET.SubElement(coordinates, "Coordinate", name=f"{name}_coord_{i}")
        # All properties default

    # Physical offset frames
    frames = ET.SubElement(joint, "frames")

    # Parent frame
    parent_frame = ET.SubElement(frames, "PhysicalOffsetFrame", name=f"{name}_parent_offset")
    parent_geom = ET.SubElement(parent_frame, "FrameGeometry", name="frame_geometry")
    ET.SubElement(parent_geom, "socket_frame").text = ".."
    parent_scale = ET.SubElement(parent_geom, "scale_factors")
    parent_scale.text = "0.20000000000000001 0.20000000000000001 0.20000000000000001"
    ET.SubElement(parent_frame, "socket_parent").text = f"/bodyset/{parent_body}" if parent_body != "ground" else "/ground"
    ET.SubElement(parent_frame, "translation").text = f"{parent_pos[0]:.6f} {parent_pos[1]:.6f} {parent_pos[2]:.6f}"
    ET.SubElement(parent_frame, "orientation").text = f"{parent_rot[0]:.6f} {parent_rot[1]:.6f} {parent_rot[2]:.6f}"

    # Child frame
    child_frame = ET.SubElement(frames, "PhysicalOffsetFrame", name=f"{name}_child_offset")
    child_geom = ET.SubElement(child_frame, "FrameGeometry", name="frame_geometry")
    ET.SubElement(child_geom, "socket_frame").text = ".."
    child_scale = ET.SubElement(child_geom, "scale_factors")
    child_scale.text = "0.20000000000000001 0.20000000000000001 0.20000000000000001"
    ET.SubElement(child_frame, "socket_parent").text = f"/bodyset/{child_body}"
    ET.SubElement(child_frame, "translation").text = f"{child_pos[0]:.6f} {child_pos[1]:.6f} {child_pos[2]:.6f}"
    ET.SubElement(child_frame, "orientation").text = f"{child_rot[0]:.6f} {child_rot[1]:.6f} {child_rot[2]:.6f}"

    return joint

def create_opensim_custom_joint(name, parent_body, child_body, parent_pos, parent_rot,
                               child_pos, child_rot, pose_bone=None):
    """Create OpenSim CustomJoint XML element with IK constraints from pose bone"""
    joint = ET.Element("CustomJoint", name=name)

    # Socket connections
    ET.SubElement(joint, "socket_parent_frame").text = f"{name}_parent_offset"
    ET.SubElement(joint, "socket_child_frame").text = f"{name}_child_offset"

    # Determine which coordinates to include based on IK locks
    coord_info = []
    if pose_bone:
        # Check IK locks for each axis
        axes = [
            ("rot_x", "lock_ik_x", "use_ik_limit_x", "ik_min_x", "ik_max_x", "1 0 0"),
            ("rot_y", "lock_ik_y", "use_ik_limit_y", "ik_min_y", "ik_max_y", "0 1 0"),
            ("rot_z", "lock_ik_z", "use_ik_limit_z", "ik_min_z", "ik_max_z", "0 0 1")
        ]

        for coord_name, lock_attr, limit_attr, min_attr, max_attr, axis_vec in axes:
            is_locked = getattr(pose_bone, lock_attr, False)
            if not is_locked:  # Only add coordinate if not locked
                has_limits = getattr(pose_bone, limit_attr, False)
                if has_limits:
                    min_val = getattr(pose_bone, min_attr, -1.5707963267948966)  # Default -90 degrees
                    max_val = getattr(pose_bone, max_attr, 1.5707963267948966)   # Default +90 degrees
                else:
                    min_val = -1.5707963267948966  # Default -90 degrees
                    max_val = 1.5707963267948966   # Default +90 degrees

                coord_info.append({
                    'name': coord_name,
                    'axis_vec': axis_vec,
                    'min_val': min_val,
                    'max_val': max_val,
                    'is_locked': False
                })
            else:
                # Locked axis - will use Constant transform
                coord_info.append({
                    'name': coord_name,
                    'axis_vec': axis_vec,
                    'min_val': 0,
                    'max_val': 0,
                    'is_locked': True
                })
    else:
        # Default behavior when no pose bone provided
        coord_info = [
            {
                'name': 'rot_x', 'axis_vec': '1 0 0',
                'min_val': -1.5707963267948966, 'max_val': 1.5707963267948966,
                'is_locked': False
            },
            {
                'name': 'rot_y', 'axis_vec': '0 1 0',
                'min_val': -1.5707963267948966, 'max_val': 1.5707963267948966,
                'is_locked': False
            },
            {
                'name': 'rot_z', 'axis_vec': '0 0 1',
                'min_val': -1.5707963267948966, 'max_val': 1.5707963267948966,
                'is_locked': False
            }
        ]

    # Create coordinates for unlocked axes only
    coordinates = ET.SubElement(joint, "coordinates")
    active_coords = [info for info in coord_info if not info['is_locked']]

    for coord_info_item in active_coords:
        coord_name = coord_info_item['name']
        min_val = coord_info_item['min_val']
        max_val = coord_info_item['max_val']

        coord = ET.SubElement(coordinates, "Coordinate", name=f"{name}_coord_{coord_name}")
        ET.SubElement(coord, "default_value").text = "0"
        ET.SubElement(coord, "default_speed_value").text = "0"
        ET.SubElement(coord, "range").text = f"{min_val:.10f} {max_val:.10f}"
        ET.SubElement(coord, "clamped").text = "true"
        ET.SubElement(coord, "locked").text = "false"
        ET.SubElement(coord, "prescribed_function")

    # Physical offset frames
    frames = ET.SubElement(joint, "frames")

    # Parent frame
    parent_frame = ET.SubElement(frames, "PhysicalOffsetFrame", name=f"{name}_parent_offset")
    parent_geom = ET.SubElement(parent_frame, "FrameGeometry", name="frame_geometry")
    ET.SubElement(parent_geom, "socket_frame").text = ".."
    parent_scale = ET.SubElement(parent_geom, "scale_factors")
    parent_scale.text = "0.20000000000000001 0.20000000000000001 0.20000000000000001"
    ET.SubElement(parent_frame, "socket_parent").text = f"/bodyset/{parent_body}"
    ET.SubElement(parent_frame, "translation").text = f"{parent_pos[0]:.6f} {parent_pos[1]:.6f} {parent_pos[2]:.6f}"
    ET.SubElement(parent_frame, "orientation").text = f"{parent_rot[0]:.6f} {parent_rot[1]:.6f} {parent_rot[2]:.6f}"

    # Child frame
    child_frame = ET.SubElement(frames, "PhysicalOffsetFrame", name=f"{name}_child_offset")
    child_geom = ET.SubElement(child_frame, "FrameGeometry", name="frame_geometry")
    ET.SubElement(child_geom, "socket_frame").text = ".."
    child_scale = ET.SubElement(child_geom, "scale_factors")
    child_scale.text = "0.20000000000000001 0.20000000000000001 0.20000000000000001"
    ET.SubElement(child_frame, "socket_parent").text = f"/bodyset/{child_body}"
    ET.SubElement(child_frame, "translation").text = f"{child_pos[0]:.6f} {child_pos[1]:.6f} {child_pos[2]:.6f}"
    ET.SubElement(child_frame, "orientation").text = f"{child_rot[0]:.6f} {child_rot[1]:.6f} {child_rot[2]:.6f}"

    # SpatialTransform - configure based on IK constraints
    spatial_transform = ET.SubElement(joint, "SpatialTransform")

    # Rotational axes - map to coordinate info
    rotation_mapping = [
        ("rotation1", "rot_x", "1 0 0"),
        ("rotation2", "rot_z", "0 0 1"),
        ("rotation3", "rot_y", "0 1 0")
    ]

    for axis_name, coord_type, axis_vec in rotation_mapping:
        transform_axis = ET.SubElement(spatial_transform, "TransformAxis", name=axis_name)

        # Find the corresponding coordinate info
        coord_info_item = next((info for info in coord_info if info['name'] == coord_type), None)

        if coord_info_item and not coord_info_item['is_locked']:
            # Use coordinate if not locked
            ET.SubElement(transform_axis, "coordinates").text = f"{name}_coord_{coord_type}"
            ET.SubElement(transform_axis, "axis").text = axis_vec
            linear_func = ET.SubElement(transform_axis, "LinearFunction", name="function")
            ET.SubElement(linear_func, "coefficients").text = " 1 0"
        else:
            # Use constant transform for locked axes
            ET.SubElement(transform_axis, "coordinates").text = ""
            ET.SubElement(transform_axis, "axis").text = axis_vec
            constant_func = ET.SubElement(transform_axis, "Constant", name="function")
            ET.SubElement(constant_func, "value").text = "0"

    # Translational axes (locked)
    for i, axis_vec in enumerate(["1 0 0", "0 1 0", "0 0 1"]):
        transform_axis = ET.SubElement(spatial_transform, "TransformAxis", name=f"translation{i+1}")
        ET.SubElement(transform_axis, "coordinates").text = ""
        ET.SubElement(transform_axis, "axis").text = axis_vec
        constant_func = ET.SubElement(transform_axis, "Constant", name="function")
        ET.SubElement(constant_func, "value").text = "0"

    return joint

def format_marker_name(marker_bone_name, marker_name_overrides=None):
    """
    Format marker name according to OpenSim conventions
    Args:
        marker_bone_name: Original Blender bone name
        marker_name_overrides: Dictionary of {bone_name: override_name}
    Returns:
        Formatted marker name
    """
    # Check for override first
    if marker_name_overrides and marker_bone_name in marker_name_overrides:
        return marker_name_overrides[marker_bone_name]

    name = marker_bone_name

    # Remove "MRK-" prefix if present
    if name.startswith("MRK-"):
        name = name[4:]

    # Capitalize first letter
    if name:
        name = name[0].upper() + name[1:]

    # Handle .L/.R postfix -> L/R prefix conversion
    if name.endswith(".L"):
        name = "L" + name[:-2]
    elif name.endswith(".R"):
        name = "R" + name[:-2]



    return name

def get_marker_local_position(marker_bone, parent_body_bone):
    """
    Get marker position in parent body's local coordinate system
    Args:
        marker_bone: The marker bone
        parent_body_bone: The parent body bone
    Returns:
        [x, y, z] position in OpenSim coordinates
    """
    if parent_body_bone is None:
        # No parent body, use global position
        global_pos = marker_bone.matrix.translation
    else:
        # Calculate position relative to parent body
        parent_matrix_inv = parent_body_bone.matrix.inverted()
        local_matrix = parent_matrix_inv @ marker_bone.matrix
        global_pos = local_matrix.translation

    # Convert to OpenSim coordinate system
    return blender_to_opensim_position([global_pos.x, global_pos.y, global_pos.z])

def find_marker_parent_body(marker_bone, bone_to_opensim_map):
    """
    Find the OpenSim body that should be the parent of this marker
    Args:
        marker_bone: The marker bone
        bone_to_opensim_map: Dictionary mapping bone names to OpenSim body names
    Returns:
        (parent_bone, opensim_body_name) or (None, "ground") if no parent found
    """
    current = marker_bone.parent
    while current:
        if current.name in bone_to_opensim_map:
            opensim_name = bone_to_opensim_map[current.name]
            if opensim_name is not None:  # Skip bones with None mapping
                return current, opensim_name
        current = current.parent

    # No mapped parent found, attach to ground
    return None, "ground"

def create_opensim_marker(marker_name, parent_body_name, local_position):
    """Create OpenSim Marker XML element"""
    marker = ET.Element("Marker", name=marker_name)

    # Set parent frame
    if parent_body_name == "ground":
        parent_frame_path = "/ground"
    else:
        parent_frame_path = f"/bodyset/{parent_body_name}"

    ET.SubElement(marker, "socket_parent_frame").text = parent_frame_path

    # Set location (in meters)
    location_str = f"{local_position[0]:.6f} {local_position[1]:.6f} {local_position[2]:.6f}"
    ET.SubElement(marker, "location").text = location_str

    # Set as fixed marker
    ET.SubElement(marker, "fixed").text = "true"

    return marker

def get_bones_from_collection(armature_obj, collection_name):
    """
    Get all bone names from a specified bone collection
    Args:
        armature_obj: Blender armature object
        collection_name: Name of the bone collection
    Returns:
        Set of bone names in the collection
    """
    if collection_name not in armature_obj.data.collections:
        print(f"Warning: Bone collection '{collection_name}' not found")
        return set()

    collection = armature_obj.data.collections[collection_name]
    return {bone.name for bone in collection.bones}

def find_exported_parent_in_collection(pose_bone, bone_collection):
    """
    Find the closest ancestor bone that is in the bone collection
    Args:
        pose_bone: The bone to find the exported parent for
        bone_collection: Set of bone names that are exported
    Returns:
        The exported parent pose bone, or None if no exported parent exists
    """
    current = pose_bone.parent
    while current:
        if current.name in bone_collection:
            return current
        current = current.parent
    return None

def find_marker_parent_body_in_collection(marker_bone, bone_collection):
    """
    Find the OpenSim body that should be the parent of this marker
    Args:
        marker_bone: The marker bone
        bone_collection: Set of bone names that are exported as OpenSim bodies
    Returns:
        (parent_bone, opensim_body_name) or (None, "ground") if no parent found
    """
    current = marker_bone.parent
    while current:
        if current.name in bone_collection:
            # Use the bone name directly as the OpenSim body name
            return current, current.name
        current = current.parent

    # No exported parent found, attach to ground
    return None, "ground"

def process_markers_from_collection(armature_obj, collection_name, bone_collection, marker_name_overrides=None):
    """
    Process all bones in a specific bone collection to create markers
    Args:
        armature_obj: Blender armature object
        collection_name: Name of the bone collection containing markers
        bone_collection: Set of bone names that are exported as OpenSim bodies
        marker_name_overrides: Optional dictionary of marker name overrides
    Returns:
        List of marker XML elements
    """
    markers = []

    # Store current mode and switch to object mode to access bone collections
    current_mode = bpy.context.mode
    current_object = bpy.context.active_object

    # Set the armature as active object
    bpy.context.view_layer.objects.active = armature_obj

    if current_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    try:
        # Check if the collection exists
        if collection_name not in armature_obj.data.collections:
            print(f"Warning: Bone collection '{collection_name}' not found")
            return markers

        collection = armature_obj.data.collections[collection_name]

        # Process each bone in the collection
        for bone in collection.bones:
            if bone.name not in armature_obj.pose.bones:
                continue

            marker_bone = armature_obj.pose.bones[bone.name]

            # Find parent body for this marker
            parent_bone, parent_body_name = find_marker_parent_body_in_collection(marker_bone, bone_collection)

            # Get marker position in parent body's local coordinates
            local_position = get_marker_local_position(marker_bone, parent_bone)

            # Format marker name
            marker_name = format_marker_name(bone.name, marker_name_overrides)

            # Create marker XML element
            marker_xml = create_opensim_marker(marker_name, parent_body_name, local_position)
            markers.append(marker_xml)

            print(f"Created marker '{marker_name}' on body '{parent_body_name}' at {local_position}")

    finally:
        # Restore original active object and mode
        if current_object:
            bpy.context.view_layer.objects.active = current_object

        if current_mode == 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        elif current_mode == 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

    return markers

def export_armature_to_opensim(armature_name, output_file,
                               opensim_collection_name="opensim", model_name="ExportedModel",
                               marker_collection_name="Markers", marker_name_overrides=None):
    """
    Export armature T-pose as OpenSim model with markers
    Args:
        armature_name: Name of the armature object
        output_file: Output .osim file path
        opensim_collection_name: Name of bone collection containing bones to export
        model_name: Name for the OpenSim model
        marker_collection_name: Name of bone collection containing markers
        marker_name_overrides: Optional dictionary for marker name overrides
    """
    # Get armature object
    if armature_name not in bpy.data.objects:
        raise ValueError(f"Armature '{armature_name}' not found")

    armature_obj = bpy.data.objects[armature_name]

    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object '{armature_name}' is not an armature")

    pose_bones = armature_obj.pose.bones

    # Get bones from the specified collection
    bone_collection = get_bones_from_collection(armature_obj, opensim_collection_name)

    if not bone_collection:
        raise ValueError(f"No bones found in collection '{opensim_collection_name}'")

    # Find root bone (first bone in collection with no parent in collection)
    root_bone = None
    for bone_name in bone_collection:
        if bone_name in pose_bones:
            pose_bone = pose_bones[bone_name]
            # Check if parent is not in collection
            parent_in_collection = pose_bone.parent and pose_bone.parent.name in bone_collection

            if not parent_in_collection:
                root_bone = pose_bone
                break

    if not root_bone:
        raise ValueError(f"No root bone found in collection '{opensim_collection_name}' (bone with no parent in collection)")

    # Create OpenSim document structure
    doc = ET.Element("OpenSimDocument", Version="40600")
    model = ET.SubElement(doc, "Model", name=model_name)

    # Ground
    ground = ET.SubElement(model, "Ground", name="ground")
    ground_geom = ET.SubElement(ground, "FrameGeometry", name="frame_geometry")
    ET.SubElement(ground_geom, "socket_frame").text = ".."
    ground_scale = ET.SubElement(ground_geom, "scale_factors")
    ground_scale.text = "0.20000000000000001 0.20000000000000001 0.20000000000000001"

    # BodySet
    bodyset = ET.SubElement(model, "BodySet", name="bodyset")
    bodyset_objects = ET.SubElement(bodyset, "objects")
    ET.SubElement(bodyset, "groups")

    # JointSet
    jointset = ET.SubElement(model, "JointSet", name="jointset")
    jointset_objects = ET.SubElement(jointset, "objects")
    ET.SubElement(jointset, "groups")

    # Process bones
    processed_bones = set()

    def process_bone_recursive(pose_bone, parent_opensim_name="ground"):
        """Recursively process bone and its children"""
        bone_name = pose_bone.name

        if bone_name not in bone_collection or bone_name in processed_bones:
            return

        # Use the bone name directly as the OpenSim body name
        opensim_name = bone_name

        processed_bones.add(bone_name)

        # Get bone transform and length
        opensim_pos, opensim_rot, bone_length = get_bone_opensim_transform(pose_bone, bone_collection)

        # Create body
        body = create_opensim_body(opensim_name, bone_length)
        bodyset_objects.append(body)

        # Create joint
        if parent_opensim_name == "ground":
            # Root bone gets FreeJoint
            joint = create_opensim_free_joint(f"joint_{opensim_name}", "ground", opensim_name,
                opensim_pos,  # Parent frame position (bone head in parent coordinates)
                opensim_rot,  # Parent frame orientation
                [0, 0, 0],    # Child frame position (at child body origin)
                [0, 0, 0]     # Child frame orientation (aligned with child body))
            )
        else:
            # Child bones get CustomJoint
            # For joint frames, we need positions relative to parent and child bodies
            joint = create_opensim_custom_joint(
                f"joint_{opensim_name}",
                parent_opensim_name,
                opensim_name,
                opensim_pos,  # Parent frame position (bone head in parent coordinates)
                opensim_rot,  # Parent frame orientation
                [0, 0, 0],    # Child frame position (at child body origin)
                [0, 0, 0],    # Child frame orientation (aligned with child body)
                pose_bone     # Pass pose bone for IK constraints
            )

        jointset_objects.append(joint)

        # Process children
        for child in pose_bone.children:
            if child.name in bone_collection:
                process_bone_recursive(child, opensim_name)

    # Start processing from root bone
    process_bone_recursive(root_bone)

    # Add other required sections (empty for now)
    controller_set = ET.SubElement(model, "ControllerSet", name="controllerset")
    ET.SubElement(controller_set, "objects")
    ET.SubElement(controller_set, "groups")

    force_set = ET.SubElement(model, "ForceSet", name="forceset")
    ET.SubElement(force_set, "objects")
    ET.SubElement(force_set, "groups")

    marker_set = ET.SubElement(model, "MarkerSet", name="markers")
    marker_objects = ET.SubElement(marker_set, "objects")
    ET.SubElement(marker_set, "groups")

    # Process markers from bone collection
    markers = process_markers_from_collection(
        armature_obj,
        marker_collection_name,
        bone_collection,
        marker_name_overrides
    )

    # Add markers to marker set
    for marker in markers:
        marker_objects.append(marker)

    # Write XML file
    tree = ET.ElementTree(doc)
    ET.indent(tree, space="  ", level=0)

    with open(output_file, 'wb') as f:
        tree.write(f, encoding='utf-8', xml_declaration=True)

    print(f"Exported OpenSim model to: {output_file}")
    print(f"Total bodies: {len(processed_bones)}")
    print(f"Model name: {model_name}")

# Example bone mapping with None for bones to skip
bone_to_hik_map = {
    'spine': 'Hips',
    'spine.001': 'Spine',
    'spine.002': 'Spine3',
#    'chest_root': 'Spine6',    # Skip this bone but include its children
    'spine.003': 'Spine9',
    'spine.004': 'Neck',
    'spine.005': 'Neck1',
    'spine.006': 'Head',
    'shoulder_connect.L': None,    # Skip
    'shoulder_connect.R': None,    # Skip
    'shoulder.R': 'RightShoulder',
    'upper_arm.R': 'RightArm',
    'forearm.R': 'RightForeArm',
    'hand.R': 'RightHand',
    'shoulder.L': 'LeftShoulder',
    'upper_arm.L': 'LeftArm',
    'forearm.L': 'LeftForeArm',
    'hand.L': 'LeftHand',
    'thigh.R': 'RightUpLeg',
    'shin.R': 'RightLeg',
    'foot.R': 'RightFoot',
    'thigh.L': 'LeftUpLeg',
    'shin.L': 'LeftLeg',
    'foot.L': 'LeftFoot',
}



armature_name = "metarig"  # Replace with your armature name
use_local = False
# Export T-pose (current pose as skeleton definition)
export_armature_tpose_to_yaml(
    armature_name,
    bone_to_hik_map,
    "c:\\temp\\skeleton_local_coords.yaml",
    use_local_coords=use_local
)

# Export animation (frames 1 to 100)
export_armature_animation_to_yaml(
    armature_name,
    bone_to_hik_map,
    "c:\\temp\\animation_local_coords.yaml",
    frame_start=0,
    frame_end=700,
    use_local_coords=use_local
)

# Example OpenSim export - uncomment to use
# Export to OpenSim using bone collection (uncomment to use)
export_armature_to_opensim(
    armature_name,
    "c:\\temp\\exported_model.osim",
    opensim_collection_name="opensim",  # Bone collection containing bones to export
    model_name="BlenderExportedModel"
)