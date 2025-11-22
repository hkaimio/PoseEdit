# Generic Armature to OpenSim Export Design

## Overview

This design describes a configurable system for exporting Blender armatures to OpenSim models. The system uses Python configuration files to define armature-specific export parameters, making it easier to maintain and adapt for different character rigs.

## Goals

1. **Declarative Configuration**: Define export parameters in Python configuration files rather than bone collections
2. **Hierarchy Discovery**: Automatically extract bone hierarchy from Blender armature
3. **Flexible Joint Constraints**: Configure joint types (free vs. custom) and axis constraints per bone
4. **Bidirectional Workflow**: Support both export (Blender → OpenSim) and import (OpenSim solution → Blender)
5. **Maintainability**: Separate configuration from export logic

## Architecture

### Configuration System

#### Armature Configuration File Structure

Each armature type has a Python configuration file (e.g., `opensim_config_humanoid.py`):

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List

class JointType(Enum):
    """Type of joint to create in OpenSim"""
    FREE = "free"           # 6 DOF (3 translation + 3 rotation)
    CUSTOM = "custom"       # 0-3 DOF rotation only

@dataclass
class AxisConstraint:
    """Constraint configuration for a single rotation axis"""
    locked: bool = False           # If True, axis is completely locked (no coordinate)
    min_angle: float = -90.0       # Minimum angle in degrees
    max_angle: float = 90.0        # Maximum angle in degrees
    
    def to_radians(self):
        """Convert angles to radians for OpenSim"""
        import math
        return (math.radians(self.min_angle), math.radians(self.max_angle))

@dataclass
class JointConstraints:
    """Joint constraint configuration"""
    joint_type: JointType = JointType.CUSTOM
    
    # Rotation constraints (for CUSTOM joints)
    x_axis: AxisConstraint = None   # Rotation around X
    y_axis: AxisConstraint = None   # Rotation around Y
    z_axis: AxisConstraint = None   # Rotation around Z
    
    def __post_init__(self):
        # Set default constraints if not provided
        if self.joint_type == JointType.CUSTOM:
            if self.x_axis is None:
                self.x_axis = AxisConstraint()
            if self.y_axis is None:
                self.y_axis = AxisConstraint()
            if self.z_axis is None:
                self.z_axis = AxisConstraint()

@dataclass
class BoneConfig:
    """Configuration for a single bone export"""
    blender_name: str                    # Name in Blender armature
    opensim_name: str                    # Name in exported OpenSim model
    constraints: JointConstraints        # Joint constraints for this bone
    export_body: bool = True             # Whether to export as OpenSim Body
    body_mass: float = 1.0              # Mass for OpenSim Body (kg)
    body_inertia: tuple = (1, 1, 1, 0, 0, 0)  # Inertia tensor
    
@dataclass 
class MarkerConfig:
    """Configuration for marker name overrides"""
    overrides: Dict[str, str] = None    # {blender_bone_name: opensim_marker_name}
    
    def __post_init__(self):
        if self.overrides is None:
            self.overrides = {}

class ArmatureExportConfig:
    """
    Main configuration class for armature export
    """
    def __init__(self):
        self.model_name: str = "ExportedModel"
        self.bones: Dict[str, BoneConfig] = {}
        self.marker_config: MarkerConfig = MarkerConfig()
        self.marker_collection_name: str = "Markers"
        
    def add_bone(self, bone_config: BoneConfig):
        """Add a bone configuration"""
        self.bones[bone_config.blender_name] = bone_config
        
    def get_bone_config(self, blender_name: str) -> Optional[BoneConfig]:
        """Get configuration for a bone by Blender name"""
        return self.bones.get(blender_name)
        
    def is_exported(self, blender_name: str) -> bool:
        """Check if a bone should be exported"""
        return blender_name in self.bones
```

#### Example Configuration: Humanoid Rig

```python
# opensim_config_humanoid.py

def create_humanoid_config() -> ArmatureExportConfig:
    """Create configuration for humanoid armature export"""
    config = ArmatureExportConfig()
    config.model_name = "HumanoidModel"
    
    # Root bone - use FREE joint (6 DOF)
    config.add_bone(BoneConfig(
        blender_name="pelvis",
        opensim_name="pelvis",
        constraints=JointConstraints(joint_type=JointType.FREE),
        body_mass=10.0
    ))
    
    # Spine - limited rotation on all axes
    config.add_bone(BoneConfig(
        blender_name="spine",
        opensim_name="lumbar",
        constraints=JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=30),
            y_axis=AxisConstraint(locked=False, min_angle=-45, max_angle=45),
            z_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=20)
        ),
        body_mass=8.0
    ))
    
    # Shoulder - ball joint (3 DOF)
    config.add_bone(BoneConfig(
        blender_name="shoulder.R",
        opensim_name="shoulder_r",
        constraints=JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False, min_angle=-180, max_angle=180),
            y_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=180),
            z_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=90)
        ),
        body_mass=3.0
    ))
    
    # Elbow - hinge joint (1 DOF)
    config.add_bone(BoneConfig(
        blender_name="forearm.R",
        opensim_name="elbow_r",
        constraints=JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=True),     # No rotation
            y_axis=AxisConstraint(locked=False, min_angle=0, max_angle=140),
            z_axis=AxisConstraint(locked=True)      # No rotation
        ),
        body_mass=1.5
    ))
    
    # Wrist - limited 2 DOF
    config.add_bone(BoneConfig(
        blender_name="hand.R",
        opensim_name="wrist_r",
        constraints=JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False, min_angle=-70, max_angle=70),
            y_axis=AxisConstraint(locked=True),
            z_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=30)
        ),
        body_mass=0.5
    ))
    
    # Mirror for left side
    config.add_bone(BoneConfig(
        blender_name="shoulder.L",
        opensim_name="shoulder_l",
        constraints=JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False, min_angle=-180, max_angle=180),
            y_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=180),
            z_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=90)
        ),
        body_mass=3.0
    ))
    
    # Marker name overrides
    config.marker_config.overrides = {
        "MRK-shoulder.R": "R_Shoulder",
        "MRK-shoulder.L": "L_Shoulder",
        "MRK-elbow.R": "R_Elbow",
        "MRK-elbow.L": "L_Elbow",
    }
    
    return config
```

### Export System

#### Main Export Function

```python
def export_armature_to_opensim_with_config(
    armature_name: str,
    config: ArmatureExportConfig,
    output_file: str
):
    """
    Export armature to OpenSim using configuration
    
    Args:
        armature_name: Name of Blender armature object
        config: Export configuration
        output_file: Output .osim file path
    """
    # Get armature
    armature_obj = get_armature(armature_name)
    
    # Build hierarchy from Blender armature
    hierarchy = build_export_hierarchy(armature_obj, config)
    
    # Create OpenSim document
    doc = create_opensim_document(config.model_name)
    
    # Export bodies and joints
    export_bodies_and_joints(doc, hierarchy, config)
    
    # Export markers
    export_markers(doc, armature_obj, config)
    
    # Write file
    write_opensim_file(doc, output_file)
```

#### Hierarchy Builder

```python
@dataclass
class BoneHierarchyNode:
    """Node in the export hierarchy tree"""
    blender_bone: bpy.types.PoseBone
    config: BoneConfig
    parent: Optional['BoneHierarchyNode'] = None
    children: List['BoneHierarchyNode'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []

def build_export_hierarchy(armature_obj, config: ArmatureExportConfig) -> BoneHierarchyNode:
    """
    Build hierarchy tree from Blender armature, including only configured bones
    
    Args:
        armature_obj: Blender armature object
        config: Export configuration
        
    Returns:
        Root node of hierarchy tree
    """
    pose_bones = armature_obj.pose.bones
    
    # Find root bone (configured bone with no configured parent)
    root_bone = None
    for bone_name, bone_config in config.bones.items():
        if bone_name not in pose_bones:
            raise ValueError(f"Bone '{bone_name}' not found in armature")
            
        pose_bone = pose_bones[bone_name]
        
        # Check if parent is in configuration
        has_configured_parent = False
        current_parent = pose_bone.parent
        while current_parent:
            if config.is_exported(current_parent.name):
                has_configured_parent = True
                break
            current_parent = current_parent.parent
            
        if not has_configured_parent:
            root_bone = pose_bone
            break
    
    if not root_bone:
        raise ValueError("No root bone found in configuration")
    
    # Build tree recursively
    def build_node(pose_bone, parent_node=None):
        bone_config = config.get_bone_config(pose_bone.name)
        if not bone_config:
            return None
            
        node = BoneHierarchyNode(
            blender_bone=pose_bone,
            config=bone_config,
            parent=parent_node
        )
        
        # Process children (only configured bones)
        for child_bone in pose_bone.children:
            child_node = build_node_recursive(child_bone, node)
            if child_node:
                node.children.append(child_node)
        
        return node
    
    def build_node_recursive(pose_bone, parent_node):
        """Recursively find next configured bone in hierarchy"""
        if config.is_exported(pose_bone.name):
            return build_node(pose_bone, parent_node)
        else:
            # Skip this bone but check its children
            for child in pose_bone.children:
                child_node = build_node_recursive(child, parent_node)
                if child_node:
                    return child_node
            return None
    
    return build_node(root_bone)
```

#### Joint and Body Export

```python
def export_bodies_and_joints(
    doc: ET.Element,
    hierarchy: BoneHierarchyNode,
    config: ArmatureExportConfig
):
    """
    Export bodies and joints from hierarchy
    
    Args:
        doc: OpenSim XML document
        hierarchy: Root of bone hierarchy
        config: Export configuration
    """
    model = doc.find("Model")
    bodyset_objects = model.find(".//BodySet/objects")
    jointset_objects = model.find(".//JointSet/objects")
    
    def export_node(node: BoneHierarchyNode, parent_body_name: str = "ground"):
        """Recursively export node and children"""
        bone = node.blender_bone
        bone_config = node.config
        
        # Get bone transform in OpenSim coordinate system
        position, rotation, length = get_bone_opensim_transform(
            bone, 
            node.parent.blender_bone if node.parent else None
        )
        
        # Create body
        if bone_config.export_body:
            body = create_opensim_body(
                bone_config.opensim_name,
                length,
                bone_config.body_mass,
                bone_config.body_inertia
            )
            bodyset_objects.append(body)
        
        # Create joint
        joint = create_joint_from_config(
            bone_config,
            parent_body_name,
            position,
            rotation,
            bone
        )
        jointset_objects.append(joint)
        
        # Process children
        for child_node in node.children:
            export_node(child_node, bone_config.opensim_name)
    
    # Start export from root
    export_node(hierarchy)

def create_joint_from_config(
    bone_config: BoneConfig,
    parent_body_name: str,
    position: tuple,
    rotation: tuple,
    pose_bone: bpy.types.PoseBone
) -> ET.Element:
    """
    Create OpenSim joint element based on configuration
    
    Args:
        bone_config: Bone configuration
        parent_body_name: Name of parent body
        position: Local position
        rotation: Local rotation
        pose_bone: Blender pose bone (for additional data)
        
    Returns:
        Joint XML element
    """
    constraints = bone_config.constraints
    joint_name = f"{bone_config.opensim_name}_joint"
    
    if constraints.joint_type == JointType.FREE:
        return create_opensim_free_joint(
            joint_name,
            parent_body_name,
            bone_config.opensim_name,
            position, rotation,
            (0, 0, 0), (0, 0, 0)  # Child offset defaults
        )
    else:  # CUSTOM joint
        return create_opensim_custom_joint_from_config(
            joint_name,
            parent_body_name,
            bone_config.opensim_name,
            position, rotation,
            (0, 0, 0), (0, 0, 0),  # Child offset defaults
            constraints
        )

def create_opensim_custom_joint_from_config(
    name: str,
    parent_body: str,
    child_body: str,
    parent_pos: tuple,
    parent_rot: tuple,
    child_pos: tuple,
    child_rot: tuple,
    constraints: JointConstraints
) -> ET.Element:
    """
    Create CustomJoint from configuration instead of pose bone IK locks
    
    Args:
        name: Joint name
        parent_body: Parent body name
        child_body: Child body name
        parent_pos: Parent frame position
        parent_rot: Parent frame rotation
        child_pos: Child frame position
        child_rot: Child frame rotation
        constraints: Joint constraints from configuration
        
    Returns:
        CustomJoint XML element
    """
    joint = ET.Element("CustomJoint", name=name)
    
    # Socket connections
    ET.SubElement(joint, "socket_parent_frame").text = f"{name}_parent_offset"
    ET.SubElement(joint, "socket_child_frame").text = f"{name}_child_offset"
    
    # Build coordinate info from constraints
    coord_info = []
    
    axes = [
        ("rot_x", constraints.x_axis, "1 0 0"),
        ("rot_y", constraints.y_axis, "0 1 0"),
        ("rot_z", constraints.z_axis, "0 0 1")
    ]
    
    for coord_name, axis_constraint, axis_vec in axes:
        if not axis_constraint.locked:
            min_val, max_val = axis_constraint.to_radians()
            coord_info.append({
                'name': coord_name,
                'axis_vec': axis_vec,
                'min_val': min_val,
                'max_val': max_val,
                'is_locked': False
            })
    
    # Create coordinates
    coordinates = ET.SubElement(joint, "coordinates")
    for info in coord_info:
        coord = ET.SubElement(coordinates, "Coordinate", name=f"{name}_coord_{info['name']}")
        ET.SubElement(coord, "default_value").text = "0"
        ET.SubElement(coord, "default_speed_value").text = "0"
        ET.SubElement(coord, "range").text = f"{info['min_val']:.10f} {info['max_val']:.10f}"
        ET.SubElement(coord, "clamped").text = "true"
        ET.SubElement(coord, "locked").text = "false"
        ET.SubElement(coord, "prescribed_function")
    
    # Add offset frames (same as before)
    frames = ET.SubElement(joint, "frames")
    
    # Parent frame
    parent_frame = ET.SubElement(frames, "PhysicalOffsetFrame", name=f"{name}_parent_offset")
    # ... (same as current implementation)
    
    # Child frame
    child_frame = ET.SubElement(frames, "PhysicalOffsetFrame", name=f"{name}_child_offset")
    # ... (same as current implementation)
    
    # Spatial transform
    spatial_transform = ET.SubElement(joint, "SpatialTransform")
    
    # Map coordinates to rotation axes
    rotation_mapping = [
        ("rotation1", "rot_x", "1 0 0"),
        ("rotation2", "rot_z", "0 0 1"),
        ("rotation3", "rot_y", "0 1 0")
    ]
    
    for axis_name, coord_type, axis_vec in rotation_mapping:
        transform_axis = ET.SubElement(spatial_transform, "TransformAxis", name=axis_name)
        
        # Find corresponding coordinate
        coord_found = False
        for info in coord_info:
            if info['name'] == coord_type:
                ET.SubElement(transform_axis, "coordinates").text = f"{name}_coord_{coord_type}"
                ET.SubElement(transform_axis, "axis").text = axis_vec
                ET.SubElement(transform_axis, "function")  # Linear by default
                coord_found = True
                break
        
        if not coord_found:
            # Locked axis
            ET.SubElement(transform_axis, "coordinates")
            ET.SubElement(transform_axis, "axis").text = axis_vec
            ET.SubElement(transform_axis, "function")
    
    # Translation axes (all locked)
    for axis_vec in ["1 0 0", "0 1 0", "0 0 1"]:
        transform_axis = ET.SubElement(spatial_transform, "TransformAxis", name=f"translation{len([t for t in spatial_transform.findall('TransformAxis') if 'translation' in t.get('name', '')]) + 1}")
        ET.SubElement(transform_axis, "coordinates")
        ET.SubElement(transform_axis, "axis").text = axis_vec
        ET.SubElement(transform_axis, "function")
    
    return joint
```

### Marker Export

Markers continue to use Blender bone collections, but apply name overrides from configuration:

```python
def export_markers(
    doc: ET.Element,
    armature_obj: bpy.types.Object,
    config: ArmatureExportConfig
):
    """
    Export markers from bone collection
    
    Args:
        doc: OpenSim XML document
        armature_obj: Blender armature
        config: Export configuration
    """
    marker_set = doc.find(".//MarkerSet/objects")
    
    # Get marker bones from collection
    markers = process_markers_from_collection(
        armature_obj,
        config.marker_collection_name,
        set(config.bones.keys()),  # Use configured bones as body set
        config.marker_config.overrides
    )
    
    for marker in markers:
        marker_set.append(marker)
```

## Bidirectional Workflow: Importing OpenSim Solutions

### OpenSim Solution Format

OpenSim inverse kinematics outputs joint coordinate values per frame:

```xml
<OpenSimDocument>
  <InverseKinematicsSolution>
    <time>0.000 0.033 0.066 ...</time>
    <pelvis_tx>0.0 0.1 0.2 ...</pelvis_tx>
    <pelvis_ty>0.0 0.0 0.0 ...</pelvis_ty>
    <pelvis_tilt>0.0 0.1 0.2 ...</pelvis_tilt>
    <lumbar_extension>0.0 0.05 0.1 ...</lumbar_extension>
    ...
  </InverseKinematicsSolution>
</OpenSimDocument>
```

### Import Strategy

```python
@dataclass
class OpenSimSolutionData:
    """Parsed OpenSim solution"""
    time_values: List[float]
    coordinate_values: Dict[str, List[float]]  # {coordinate_name: [values]}
    
def import_opensim_solution(
    solution_file: str,
    armature_name: str,
    config: ArmatureExportConfig,
    frame_start: int = 1,
    fps: float = 30.0
):
    """
    Import OpenSim IK solution back to Blender armature
    
    Args:
        solution_file: Path to OpenSim solution (.mot or .sto file)
        armature_name: Target Blender armature
        config: Same configuration used for export
        frame_start: First frame to write animation
        fps: Frames per second
    """
    # Parse solution file
    solution_data = parse_opensim_solution(solution_file)
    
    # Get armature
    armature_obj = get_armature(armature_name)
    
    # Build coordinate to bone mapping
    coord_to_bone_map = build_coordinate_to_bone_map(config)
    
    # Apply animation to armature
    apply_solution_to_armature(
        armature_obj,
        solution_data,
        coord_to_bone_map,
        config,
        frame_start,
        fps
    )

def build_coordinate_to_bone_map(config: ArmatureExportConfig) -> Dict[str, tuple]:
    """
    Build mapping from OpenSim coordinate names to (bone_name, axis)
    
    Returns:
        {coordinate_name: (blender_bone_name, axis_index, axis_name)}
        Example: {"shoulder_r_rot_x": ("shoulder.R", 0, "x")}
    """
    coord_map = {}
    
    for bone_name, bone_config in config.bones.items():
        opensim_name = bone_config.opensim_name
        joint_name = f"{opensim_name}_joint"
        constraints = bone_config.constraints
        
        if constraints.joint_type == JointType.FREE:
            # Free joint has 6 coordinates: 3 translation + 3 rotation
            for i, axis in enumerate(['x', 'y', 'z']):
                # Translation coordinates
                coord_name = f"{joint_name}_coord_{i}"
                coord_map[coord_name] = (bone_name, i, f"t{axis}")
                
                # Rotation coordinates
                coord_name = f"{joint_name}_coord_{i+3}"
                coord_map[coord_name] = (bone_name, i, f"r{axis}")
        else:
            # Custom joint - map based on unlocked axes
            axis_list = [
                (constraints.x_axis, 'x', 0),
                (constraints.y_axis, 'y', 1),
                (constraints.z_axis, 'z', 2)
            ]
            
            for axis_constraint, axis_name, axis_idx in axis_list:
                if not axis_constraint.locked:
                    coord_name = f"{joint_name}_coord_rot_{axis_name}"
                    coord_map[coord_name] = (bone_name, axis_idx, f"r{axis_name}")
    
    return coord_map

def apply_solution_to_armature(
    armature_obj: bpy.types.Object,
    solution_data: OpenSimSolutionData,
    coord_to_bone_map: Dict[str, tuple],
    config: ArmatureExportConfig,
    frame_start: int,
    fps: float
):
    """
    Apply OpenSim solution to Blender armature animation
    
    Args:
        armature_obj: Target armature
        solution_data: Parsed OpenSim solution
        coord_to_bone_map: Mapping from coordinates to bones
        config: Export configuration
        frame_start: First frame number
        fps: Frames per second
    """
    scene = bpy.context.scene
    scene.frame_start = frame_start
    
    # Calculate frame numbers from time values
    frame_numbers = [
        frame_start + int(t * fps)
        for t in solution_data.time_values
    ]
    scene.frame_end = frame_numbers[-1]
    
    # Clear existing animation
    if armature_obj.animation_data:
        armature_obj.animation_data.action = None
    
    # Create new action
    action = bpy.data.actions.new(name=f"{armature_obj.name}_opensim_ik")
    armature_obj.animation_data_create()
    armature_obj.animation_data.action = action
    
    # Apply coordinate values to bones
    for coord_name, values in solution_data.coordinate_values.items():
        if coord_name not in coord_to_bone_map:
            continue
            
        bone_name, axis_idx, axis_type = coord_to_bone_map[coord_name]
        pose_bone = armature_obj.pose.bones[bone_name]
        
        # Determine which property to keyframe
        if axis_type.startswith('t'):
            # Translation
            data_path = "location"
        else:
            # Rotation - use Euler angles
            data_path = "rotation_euler"
        
        # Create keyframes
        for frame_num, value in zip(frame_numbers, values):
            scene.frame_set(frame_num)
            
            if axis_type.startswith('t'):
                # Set translation
                pose_bone.location[axis_idx] = value
            else:
                # Set rotation (convert from radians if needed)
                pose_bone.rotation_euler[axis_idx] = value
            
            # Insert keyframe
            pose_bone.keyframe_insert(data_path=data_path, index=axis_idx, frame=frame_num)
    
    print(f"Imported OpenSim solution with {len(frame_numbers)} frames")
```

### Solution File Parsing

```python
def parse_opensim_solution(solution_file: str) -> OpenSimSolutionData:
    """
    Parse OpenSim .mot or .sto file
    
    Args:
        solution_file: Path to solution file
        
    Returns:
        Parsed solution data
    """
    with open(solution_file, 'r') as f:
        lines = f.readlines()
    
    # Find header end (line starting with "endheader")
    header_end = 0
    for i, line in enumerate(lines):
        if line.strip().lower().startswith('endheader'):
            header_end = i + 1
            break
    
    # Next line is column names
    column_names = lines[header_end].split()
    
    # Parse data
    data = {name: [] for name in column_names}
    
    for line in lines[header_end + 1:]:
        values = line.split()
        if len(values) != len(column_names):
            continue
        
        for name, value in zip(column_names, values):
            data[name].append(float(value))
    
    # Extract time and coordinate data
    time_values = data.pop('time', data.pop('Time', []))
    
    return OpenSimSolutionData(
        time_values=time_values,
        coordinate_values=data
    )
```

## Implementation Plan

### Phase 1: Configuration System
1. Create configuration dataclasses and enums
2. Implement example configurations (humanoid, quadruped)
3. Add configuration validation

### Phase 2: Export Refactoring
1. Implement hierarchy builder from configuration
2. Refactor joint creation to use configuration
3. Update marker export to use configuration overrides
4. Remove dependency on bone collections for body export

### Phase 3: Solution Import
1. Implement OpenSim solution file parser
2. Create coordinate-to-bone mapping system
3. Implement animation application logic
4. Add keyframe interpolation options

### Phase 4: Testing & Documentation
1. Test with various armature types
2. Create example configurations
3. Document configuration format
4. Add error handling and validation

## Benefits

1. **Maintainability**: Configuration is separate from export logic, easier to update
2. **Flexibility**: Different armature types can have different configurations
3. **Clarity**: Explicit configuration makes export behavior clear
4. **Bidirectional**: Design supports both export and import workflows
5. **Extensibility**: Easy to add new joint types or constraint options
6. **Version Control**: Configuration files can be tracked and diff'd easily

## Migration Path

For existing projects:
1. Keep old `export_armature_to_opensim()` function for backward compatibility
2. Add new `export_armature_to_opensim_with_config()` function
3. Create migration tool to generate configuration from bone collections
4. Gradually migrate projects to new system

## Future Enhancements

1. **GUI Integration**: Create Blender panel to edit configurations visually
2. **Configuration Inheritance**: Support base configurations that can be extended
3. **Joint Type Library**: Pre-defined joint configurations (ball, hinge, saddle, etc.)
4. **Validation Tools**: Check configuration against armature structure
5. **Animation Export**: Export animated sequences with joint coordinate values
6. **Muscle Attachments**: Support defining muscle paths in configuration
