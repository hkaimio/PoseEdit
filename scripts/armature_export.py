import bpy
import yaml
import math
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
        global_matrix.translation.x * 100,  # Convert to centimeters
        global_matrix.translation.z * 100,  # Blender Z -> iClone Y (up)
        -global_matrix.translation.y * 100  # Blender -Y -> iClone Z (forward)
    ]
    
    # Extract rotation as Euler angles (ZXY order for iClone)
    euler = global_matrix.to_euler('ZXY')
    rotation = [
        math.degrees(euler.x),
        math.degrees(euler.y),
        math.degrees(euler.z)
    ]
    
    return position, rotation

def get_bone_local_transform(pose_bone):
    """
    Get local position and rotation relative to parent bone
    Returns: (position [x, y, z], rotation [rx, ry, rz] in degrees)
    """
    # Get local matrix (relative to parent)
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
    euler = local_matrix.to_euler('ZXY')
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
            position, rotation = get_bone_local_transform(pose_bone)
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
            'up': 'y',
            'forward': '-z',
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
                position, rotation = get_bone_local_transform(pose_bone)
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

# Example bone mapping with None for bones to skip
bone_to_hik_map = {
    'spine': 'Hips',
    'spine.001': 'Spine',
    'spine.002': 'Spine3',
    'chest_root': 'Spine6',    # Skip this bone but include its children
    'spine.003': 'Spine9',
    'spine.004': 'Neck',  
    'spine.005': 'Neck1',
    'spine.006': 'Head',
    'shoulder_connect.L': None,    # Skip
    'shoulder_connect.R': None,    # Skip
    'shoulder_place.R': 'RightShoulder',
    'upper_arm.R': 'RightArm',
    'forearm.R': 'RightForeArm',
    'hand.R': 'RightHand',
    'shoulder_place.L': 'LeftShoulder',
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

# Export T-pose (current pose as skeleton definition)
export_armature_tpose_to_yaml(
    armature_name,
    bone_to_hik_map,
    "c:\\temp\\skeleton_local_coords.yaml",
    use_local_coords=True
)

# Export animation (frames 1 to 100)
export_armature_animation_to_yaml(
    armature_name,
    bone_to_hik_map,
    "c:\\temp\\animation_local_coords.yaml",
    frame_start=1,
    frame_end=100,
    use_local_coords=True
)