#!/usr/bin/env python3
"""
OpenSim to Blender Armature Converter - Implementation Outline

This file provides the structural outline for converting OpenSim models
to Blender armatures with proper bone hierarchy and positioning.
"""

import bpy
import bmesh
from mathutils import Vector, Quaternion, Matrix, Euler
from typing import Dict, List, Tuple, Optional, Any
import math

import xml.etree.ElementTree as ET
import math
import yaml
import argparse
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple, Any

@dataclass
class Coordinate:
    """Represents a generalized coordinate (DOF) of a joint"""
    name: str
    default_value: float
    range_min: float
    range_max: float
    clamped: bool
    locked: bool
    prescribed: bool
    coordinate_type: str  # 'rotational' or 'translational'

@dataclass 
class OffsetFrame:
    """Represents a PhysicalOffsetFrame with translation and orientation"""
    name: str
    parent_body: str
    translation: Tuple[float, float, float]  # meters
    orientation: Tuple[float, float, float]  # radians (x-y-z rotation sequence)
    
    def get_transform_matrix(self) -> Matrix:
        """Get the 4x4 transformation matrix for this offset frame"""
        # Create translation matrix
        translation_matrix = Matrix.Translation(Vector(self.translation))
        
        # Create rotation matrix from Euler angles (x-y-z sequence)
        rotation_matrix = Euler(self.orientation, 'XYZ').to_matrix().to_4x4()
        
        # Combine translation and rotation
        return translation_matrix @ rotation_matrix

@dataclass
class Body:
    """Represents an OpenSim body with all related information"""
    name: str
    mass: float
    inertia: Tuple[float, float, float, float, float, float]  # Ixx, Iyy, Izz, Ixy, Ixz, Iyz
    mass_center: Tuple[float, float, float]
    
    # Associated frames
    offset_frames: Dict[str, OffsetFrame]  # frame_name -> OffsetFrame
    
    # Hierarchy relationships
    parent_joint: Optional['Joint'] = None
    child_joints: List['Joint'] = None
    
    def __post_init__(self):
        if self.child_joints is None:
            self.child_joints = []
    
    def get_offset_frame(self, frame_name: str) -> Optional[OffsetFrame]:
        """Get an offset frame by name"""
        return self.offset_frames.get(frame_name)
    
    def get_transform(self, from_frame: str, to_frame: str) -> Matrix:
        """
        Get transformation matrix from one frame to another within this body
        
        Args:
            from_frame: Source frame name (or 'body' for body's root frame)
            to_frame: Target frame name (or 'body' for body's root frame)
            
        Returns:
            4x4 transformation matrix
        """
        # Identity if same frame
        if from_frame == to_frame:
            return Matrix.Identity(4)
        
        # Get transform from body root to target frame
        if from_frame == 'body':
            target_frame = self.get_offset_frame(to_frame)
            if target_frame:
                return target_frame.get_transform_matrix()
            else:
                return Matrix.Identity(4)
        
        # Get transform from source frame to body root
        elif to_frame == 'body':
            source_frame = self.get_offset_frame(from_frame)
            if source_frame:
                return source_frame.get_transform_matrix().inverted()
            else:
                return Matrix.Identity(4)
        
        # Transform from one frame to another via body root
        else:
            source_frame = self.get_offset_frame(from_frame)
            target_frame = self.get_offset_frame(to_frame)
            
            if source_frame and target_frame:
                # from_frame -> body -> to_frame
                source_to_body = source_frame.get_transform_matrix().inverted()
                body_to_target = target_frame.get_transform_matrix()
                return source_to_body @ body_to_target
            else:
                return Matrix.Identity(4)

@dataclass
class Joint:
    """Represents an OpenSim joint with all its properties"""
    name: str
    joint_type: str  # CustomJoint, PinJoint, WeldJoint, etc.
    parent_frame: str
    child_frame: str
    parent_body: str
    child_body: str
    coordinates: list[Coordinate]
    parent_offset_frame: Optional[OffsetFrame]
    child_offset_frame: Optional[OffsetFrame]

    # For CustomJoint, store the spatial transform details
    spatial_transform: Optional[dict[str, Any]] = None

    # Hierarchy relationships
    parent_body_obj: Optional['Body'] = None
    child_body_obj: Optional['Body'] = None

    def get_coordinate_default_rotation(self) -> Matrix:
        """
        Calculate the rotation matrix from coordinate default values using SpatialTransform data
        
        Returns:
            4x4 rotation matrix representing the rest pose from coordinate defaults
        """
        if not self.spatial_transform or not self.coordinates:
            return Matrix.Identity(4)
            
        # Start with identity
        combined_rotation = Matrix.Identity(4)
        
        axes = self.spatial_transform.get('axes', [])
        
        for coord in self.coordinates:
            coord_name = coord.name
            default_value = coord.default_value
            
            # Skip if no default value
            if abs(default_value) < 1e-6:
                continue
                
            # Find the transform axis that controls this coordinate
            coord_axis = None
            for axis in axes:
                if axis.get('coordinates') == coord_name and axis.get('name', '').startswith('rotation'):
                    coord_axis = axis
                    break
                    
            if coord_axis:
                # Get the rotation axis vector
                axis_vector = coord_axis.get('axis', (0, 0, 0))
                
                # Convert OpenSim axis vector to Blender coordinate system
                # OpenSim: Y-up (x, y, z) → Blender: Z-up (x, z, -y)
                opensim_axis = Vector(axis_vector)
                blender_axis = Vector((opensim_axis.x, opensim_axis.z, -opensim_axis.y))
                
                if blender_axis.length > 0:
                    blender_axis.normalize()
                    
                    # Create rotation matrix around the Blender axis
                    rotation_matrix = Matrix.Rotation(default_value, 4, blender_axis)
                    combined_rotation = combined_rotation @ rotation_matrix
        
        return combined_rotation
    
    def get_joint_transform(self) -> Matrix:
        """
        Calculate the complete transformation from parent body to child body
        
        This follows the OpenSim joint transformation chain:
        1. Start from parent body's coordinate frame
        2. Transform to parent offset frame (if exists)
        3. Apply coordinate default rotations (rest pose)
        4. Transform to child offset frame (if exists)
        5. End at child body's coordinate frame
        
        Returns:
            4x4 transformation matrix from parent body to child body
        """
        transform = Matrix.Identity(4)
        
        # Step 1: Transform from parent body to parent offset frame
        if self.parent_offset_frame:
            parent_offset_transform = self.parent_offset_frame.get_transform_matrix()
            transform = transform @ parent_offset_transform
        
        # Step 2: Apply coordinate default rotations for rest pose
        coord_rotation = self.get_coordinate_default_rotation()
        transform = transform @ coord_rotation
        
        # Step 3: Transform from child offset frame to child body
        if self.child_offset_frame:
            # Inverse transform from child offset frame to child body
            child_offset_transform = self.child_offset_frame.get_transform_matrix().inverted()
            transform = transform @ child_offset_transform
        
        return transform

class OpenSimSkeletonAnalyzer:
    """Analyzes OpenSim model files and extracts skeleton structure"""
    
    def __init__(self, osim_file_path: str):
        self.osim_file_path = osim_file_path
        self.tree = ET.parse(osim_file_path)
        self.root = self.tree.getroot()
        self.joints: List[Joint] = []
        self.bodies: Dict[str, Any] = {}
        self.joint_hierarchy: Dict[str, List[str]] = {}  # parent_body -> [child_bodies]
        
    def analyze(self) -> Dict[str, Any]:
        """Main analysis method that extracts all skeleton information"""
        print(f"Analyzing OpenSim model: {self.osim_file_path}")
        
        # Extract bodies first
        self._extract_bodies()
        
        # Extract joints
        self._extract_joints()
        
        # Build hierarchy
        self._build_hierarchy()
        
        # Create analysis results
        results = {
            'model_info': self._get_model_info(),
            'bodies': self.bodies,
            'joints': [asdict(joint) for joint in self.joints],
            'joint_hierarchy': self.joint_hierarchy,
            'coordinate_summary': self._get_coordinate_summary(),
            'hierarchy_tree': self._build_hierarchy_tree()
        }
        
        return results
    
    def _extract_bodies(self):
        """Extract all bodies from the BodySet"""
        bodyset = self.root.find('.//BodySet')
        if bodyset is not None:
            for body in bodyset.findall('.//Body'):
                name = body.get('name')
                if name:
                    self.bodies[name] = {
                        'name': name,
                        'mass': self._get_body_property(body, 'mass', 1.0),
                        'inertia': self._get_body_inertia(body),
                        'mass_center': self._get_body_mass_center(body)
                    }
    
    def _get_body_property(self, body_elem, prop_name: str, default_value: float) -> float:
        """Extract a numeric property from a body element"""
        prop_elem = body_elem.find(f'.//{prop_name}')
        if prop_elem is not None and prop_elem.text:
            try:
                return float(prop_elem.text.strip())
            except ValueError:
                pass
        return default_value
    
    def _get_body_inertia(self, body_elem) -> Tuple[float, float, float, float, float, float]:
        """Extract inertia tensor from body (Ixx, Iyy, Izz, Ixy, Ixz, Iyz)"""
        inertia_elem = body_elem.find('.//inertia')
        if inertia_elem is not None and inertia_elem.text:
            try:
                values = [float(x) for x in inertia_elem.text.strip().split()]
                if len(values) >= 6:
                    return tuple(values[:6])
            except ValueError:
                pass
        return (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
    
    def _get_body_mass_center(self, body_elem) -> Tuple[float, float, float]:
        """Extract mass center from body"""
        center_elem = body_elem.find('.//mass_center')
        if center_elem is not None and center_elem.text:
            try:
                values = [float(x) for x in center_elem.text.strip().split()]
                if len(values) >= 3:
                    return tuple(values[:3])
            except ValueError:
                pass
        return (0.0, 0.0, 0.0)
    
    def _extract_joints(self):
        """Extract all joints from the JointSet"""
        jointset = self.root.find('.//JointSet')
        if jointset is None:
            print("Warning: No JointSet found in the model")
            return
            
        joint_elements = jointset.findall('.//CustomJoint') + \
                        jointset.findall('.//PinJoint') + \
                        jointset.findall('.//WeldJoint') + \
                        jointset.findall('.//BallJoint') + \
                        jointset.findall('.//FreeJoint')
        
        for joint_elem in joint_elements:
            joint = self._parse_joint(joint_elem)
            if joint:
                self.joints.append(joint)

    def _parse_joint(self, joint_elem) -> Optional[Joint]:
        """Parse a single joint element"""
        name = joint_elem.get('name')
        joint_type = joint_elem.tag
        
        if not name:
            return None
        
        # Get parent and child frames
        parent_frame_elem = joint_elem.find('.//socket_parent_frame')
        child_frame_elem = joint_elem.find('.//socket_child_frame')
        
        parent_frame = parent_frame_elem.text if parent_frame_elem is not None else ""
        child_frame = child_frame_elem.text if child_frame_elem is not None else ""
        
        # Extract coordinates
        coordinates = self._extract_coordinates(joint_elem)
        
        # Extract offset frames
        parent_offset, child_offset = self._extract_offset_frames(joint_elem)
        
        # Determine parent and child bodies
        parent_body = self._get_body_from_frame(joint_elem, parent_offset, parent_frame)
        child_body = self._get_body_from_frame(joint_elem, child_offset, child_frame)
        
        # Extract spatial transform for CustomJoint
        spatial_transform = None
        if joint_type == "CustomJoint":
            spatial_transform = self._extract_spatial_transform(joint_elem)
        
        return Joint(
            name=name,
            joint_type=joint_type,
            parent_frame=parent_frame,
            child_frame=child_frame,
            parent_body=parent_body,
            child_body=child_body,
            coordinates=coordinates,
            parent_offset_frame=parent_offset,
            child_offset_frame=child_offset,
            spatial_transform=spatial_transform
        )
    
    def _extract_coordinates(self, joint_elem) -> List[Coordinate]:
        """Extract all coordinates (DOFs) from a joint"""
        coordinates = []
        coords_section = joint_elem.find('.//coordinates')
        
        if coords_section is not None:
            for coord_elem in coords_section.findall('.//Coordinate'):
                coord_name = coord_elem.get('name')
                if not coord_name:
                    continue
                
                # Extract coordinate properties
                default_value = self._get_float_value(coord_elem, 'default_value', 0.0)
                
                # Parse range
                range_elem = coord_elem.find('.//range')
                range_min, range_max = -float('inf'), float('inf')
                if range_elem is not None and range_elem.text:
                    try:
                        range_values = [float(x) for x in range_elem.text.strip().split()]
                        if len(range_values) >= 2:
                            range_min, range_max = range_values[0], range_values[1]
                    except ValueError:
                        pass
                
                clamped = self._get_bool_value(coord_elem, 'clamped', False)
                locked = self._get_bool_value(coord_elem, 'locked', False)
                prescribed = self._get_bool_value(coord_elem, 'prescribed', False)
                
                # Determine coordinate type (rotational vs translational)
                coord_type = "rotational"  # Default assumption
                if "translation" in coord_name.lower() or "tx" in coord_name.lower() or "ty" in coord_name.lower() or "tz" in coord_name.lower():
                    coord_type = "translational"
                
                coordinates.append(Coordinate(
                    name=coord_name,
                    default_value=default_value,
                    range_min=range_min,
                    range_max=range_max,
                    clamped=clamped,
                    locked=locked,
                    prescribed=prescribed,
                    coordinate_type=coord_type
                ))
        
        return coordinates

    def _extract_offset_frames(self, joint_elem) -> tuple[Optional[OffsetFrame], Optional[OffsetFrame]]:
        """Extract parent and child offset frames from a joint"""
        frames_section = joint_elem.find('.//frames')
        
        # Get parent and child frame names from sockets
        parent_frame_elem = joint_elem.find('.//socket_parent_frame')
        child_frame_elem = joint_elem.find('.//socket_child_frame')
        
        parent_frame_name = parent_frame_elem.text if parent_frame_elem is not None else ""
        child_frame_name = child_frame_elem.text if child_frame_elem is not None else ""
        
        parent_offset = None
        child_offset = None
        
        if frames_section is not None:
            for frame_elem in frames_section.findall('.//PhysicalOffsetFrame'):
                frame_name = frame_elem.get('name')
                if not frame_name:
                    continue
                
                # Get parent body
                parent_socket = frame_elem.find('.//socket_parent')
                parent_body = ""
                if parent_socket is not None and parent_socket.text:
                    parent_body = parent_socket.text.strip()
                    # Remove path prefixes like "/bodyset/"
                    if "/" in parent_body:
                        parent_body = parent_body.split("/")[-1]
                
                # Get translation
                translation_elem = frame_elem.find('.//translation')
                translation = (0.0, 0.0, 0.0)
                if translation_elem is not None and translation_elem.text:
                    try:
                        values = [float(x) for x in translation_elem.text.strip().split()]
                        if len(values) >= 3:
                            translation = tuple(values[:3])
                    except ValueError:
                        pass
                
                # Get orientation
                orientation_elem = frame_elem.find('.//orientation')
                orientation = (0.0, 0.0, 0.0)
                if orientation_elem is not None and orientation_elem.text:
                    try:
                        values = [float(x) for x in orientation_elem.text.strip().split()]
                        if len(values) >= 3:
                            orientation = tuple(values[:3])
                    except ValueError:
                        pass
                
                offset_frame = OffsetFrame(
                    name=frame_name,
                    parent_body=parent_body,
                    translation=translation,
                    orientation=orientation
                )
                
                # Match frame names with socket frame references
                if frame_name == parent_frame_name:
                    parent_offset = offset_frame
                elif frame_name == child_frame_name:
                    child_offset = offset_frame
        
        return parent_offset, child_offset
    
    def _extract_spatial_transform(self, joint_elem) -> Optional[Dict[str, Any]]:
        """Extract SpatialTransform details from CustomJoint"""
        spatial_elem = joint_elem.find('.//SpatialTransform')
        if spatial_elem is None:
            return None
        
        transform_data = {}
        
        # Extract transformation axes
        axes = []
        for axis_elem in spatial_elem.findall('.//TransformAxis'):
            axis_name = axis_elem.get('name')
            if axis_name:
                coordinates_elem = axis_elem.find('.//coordinates')
                coordinates = coordinates_elem.text.strip() if coordinates_elem is not None and coordinates_elem.text else ""
                
                axis_elem_inner = axis_elem.find('.//axis')
                axis_vector = (0, 0, 0)
                if axis_elem_inner is not None and axis_elem_inner.text:
                    try:
                        values = [float(x) for x in axis_elem_inner.text.strip().split()]
                        if len(values) >= 3:
                            axis_vector = tuple(values[:3])
                    except ValueError:
                        pass
                
                axes.append({
                    'name': axis_name,
                    'coordinates': coordinates,
                    'axis': axis_vector
                })
        
        transform_data['axes'] = axes
        return transform_data
    
    def _get_body_from_frame(self, joint_elem, offset_frame: Optional[OffsetFrame], frame_name: str) -> str:
        """Determine the body name from frame information"""
        if offset_frame:
            return offset_frame.parent_body
        
        # Fallback: try to parse body name from frame_name
        if "/" in frame_name:
            parts = frame_name.split("/")
            if len(parts) >= 2 and parts[-2] in self.bodies:
                return parts[-2]
        
        # Try to infer from frame name by removing _offset suffix
        if "_offset" in frame_name:
            body_name = frame_name.replace("_offset", "")
            if body_name in self.bodies:
                return body_name
        
        # Special handling for ground frame
        if frame_name == "ground" or "ground" in frame_name:
            return "ground"
        
        return "unknown"
    
    def _build_hierarchy(self):
        """Build the joint hierarchy mapping"""
        for joint in self.joints:
            parent_body = joint.parent_body
            child_body = joint.child_body
            
            # Skip joints where parent and child are the same (self-connections)
            if parent_body == child_body:
                continue
            
            # Skip unknown bodies
            if parent_body == "unknown" or child_body == "unknown":
                continue
            
            if parent_body not in self.joint_hierarchy:
                self.joint_hierarchy[parent_body] = []
            
            if child_body not in self.joint_hierarchy[parent_body]:
                self.joint_hierarchy[parent_body].append(child_body)
    
    def _build_hierarchy_tree(self) -> Dict[str, Any]:
        """Build a hierarchical tree structure starting from ground/pelvis"""
        
        def build_tree_recursive(body_name: str, visited: set) -> Dict[str, Any]:
            if body_name in visited:
                return {"name": body_name, "children": [], "note": "circular_reference"}
            
            visited.add(body_name)
            
            # Find joint connecting to this body
            connecting_joint = None
            for joint in self.joints:
                if joint.child_body == body_name and joint.parent_body != joint.child_body:
                    connecting_joint = joint
                    break
            
            node = {
                "name": body_name,
                "joint": asdict(connecting_joint) if connecting_joint else None,
                "children": []
            }
            
            # Add children
            if body_name in self.joint_hierarchy:
                for child_body in self.joint_hierarchy[body_name]:
                    child_node = build_tree_recursive(child_body, visited.copy())
                    node["children"].append(child_node)
            
            return node
        
        # Find root (usually ground or pelvis)
        root_candidates = ["ground", "pelvis"]
        root_body = None
        
        for candidate in root_candidates:
            if candidate in self.joint_hierarchy:
                root_body = candidate
                break
        
        if not root_body:
            # Find a body that is parent but never child
            all_children = set()
            for children in self.joint_hierarchy.values():
                all_children.update(children)
            
            for parent in self.joint_hierarchy.keys():
                if parent not in all_children:
                    root_body = parent
                    break
        
        if root_body:
            return build_tree_recursive(root_body, set())
        else:
            return {"error": "Could not determine root body", "available_parents": list(self.joint_hierarchy.keys())}
        
        # Find root (usually ground or pelvis)
        root_candidates = ["ground", "pelvis"]
        root_body = None
        
        for candidate in root_candidates:
            if candidate in self.joint_hierarchy:
                root_body = candidate
                break
        
        if not root_body:
            # Find a body that is parent but never child
            all_children = set()
            for children in self.joint_hierarchy.values():
                all_children.update(children)
            
            for parent in self.joint_hierarchy.keys():
                if parent not in all_children:
                    root_body = parent
                    break
        
        if root_body:
            return build_tree_recursive(root_body, set())
        else:
            return {"error": "Could not determine root body"}
    
    def _get_model_info(self) -> Dict[str, Any]:
        """Extract general model information"""
        model_elem = self.root.find('.//Model')
        
        info = {
            "name": model_elem.get('name') if model_elem is not None else "Unknown",
            "length_units": self._get_text_value('length_units', 'meters'),
            "force_units": self._get_text_value('force_units', 'N'),
            "gravity": self._get_gravity(),
            "credits": self._get_text_value('credits', ''),
            "publications": self._get_text_value('publications', '')
        }
        
        return info
    
    def _get_coordinate_summary(self) -> Dict[str, Any]:
        """Generate a summary of all coordinates in the model"""
        total_dofs = 0
        rotational_dofs = 0
        translational_dofs = 0
        locked_dofs = 0
        prescribed_dofs = 0
        
        dof_by_joint = {}
        
        for joint in self.joints:
            dof_by_joint[joint.name] = len(joint.coordinates)
            total_dofs += len(joint.coordinates)
            
            for coord in joint.coordinates:
                if coord.coordinate_type == "rotational":
                    rotational_dofs += 1
                else:
                    translational_dofs += 1
                
                if coord.locked:
                    locked_dofs += 1
                if coord.prescribed:
                    prescribed_dofs += 1
        
        return {
            "total_dofs": total_dofs,
            "rotational_dofs": rotational_dofs,
            "translational_dofs": translational_dofs,
            "locked_dofs": locked_dofs,
            "prescribed_dofs": prescribed_dofs,
            "active_dofs": total_dofs - locked_dofs - prescribed_dofs,
            "dofs_by_joint": dof_by_joint
        }
    
    def _get_gravity(self) -> Tuple[float, float, float]:
        """Extract gravity vector"""
        gravity_elem = self.root.find('.//gravity')
        if gravity_elem is not None and gravity_elem.text:
            try:
                values = [float(x) for x in gravity_elem.text.strip().split()]
                if len(values) >= 3:
                    return tuple(values[:3])
            except ValueError:
                pass
        return (0.0, -9.80665, 0.0)
    
    def _get_text_value(self, tag_name: str, default: str = "") -> str:
        """Helper to extract text content from XML element"""
        elem = self.root.find(f'.//{tag_name}')
        return elem.text.strip() if elem is not None and elem.text else default
    
    def _get_float_value(self, parent_elem, tag_name: str, default: float = 0.0) -> float:
        """Helper to extract float value from XML element"""
        elem = parent_elem.find(f'.//{tag_name}')
        if elem is not None and elem.text:
            try:
                return float(elem.text.strip())
            except ValueError:
                pass
        return default
    
    def _get_bool_value(self, parent_elem, tag_name: str, default: bool = False) -> bool:
        """Helper to extract boolean value from XML element"""
        elem = parent_elem.find(f'.//{tag_name}')
        if elem is not None and elem.text:
            text = elem.text.strip().lower()
            return text in ('true', '1', 'yes')
        return default

def print_joint_hierarchy(results: Dict[str, Any], indent: int = 0):
    """Print the joint hierarchy in a readable format"""
    
    def print_tree(node: Dict[str, Any], depth: int = 0):
        prefix = "  " * depth
        body_name = node["name"]
        
        joint_info = ""
        if node.get("joint"):
            joint = node["joint"]
            joint_info = f" [{joint['joint_type']}: {joint['name']}]"
            
            # Add coordinate info
            if joint['coordinates']:
                coord_names = [coord['name'] for coord in joint['coordinates']]
                joint_info += f" DOFs: {', '.join(coord_names)}"
            
            # Add offset frame info
            if joint.get('child_offset_frame'):
                offset = joint['child_offset_frame']
                translation = offset['translation']
                orientation = offset['orientation']
                joint_info += f"\n{prefix}    Translation: [{translation[0]:.3f}, {translation[1]:.3f}, {translation[2]:.3f}] m"
                joint_info += f"\n{prefix}    Orientation: [{math.degrees(orientation[0]):.1f}°, {math.degrees(orientation[1]):.1f}°, {math.degrees(orientation[2]):.1f}°]"
        
        print(f"{prefix}{body_name}{joint_info}")
        
        for child in node.get("children", []):
            print_tree(child, depth + 1)
    
    hierarchy = results.get("hierarchy_tree", {})
    if hierarchy and not hierarchy.get("error"):
        print("\n=== JOINT HIERARCHY ===")
        print_tree(hierarchy)
    else:
        print(f"\nError building hierarchy: {hierarchy.get('error', 'Unknown error')}")

def print_coordinate_summary(results: Dict[str, Any]):
    """Print a summary of all coordinates"""
    coord_summary = results.get("coordinate_summary", {})
    
    print("\n=== COORDINATE SUMMARY ===")
    print(f"Total DOFs: {coord_summary.get('total_dofs', 0)}")
    print(f"  - Rotational: {coord_summary.get('rotational_dofs', 0)}")
    print(f"  - Translational: {coord_summary.get('translational_dofs', 0)}")
    print(f"  - Locked: {coord_summary.get('locked_dofs', 0)}")
    print(f"  - Prescribed: {coord_summary.get('prescribed_dofs', 0)}")
    print(f"Active DOFs: {coord_summary.get('active_dofs', 0)}")

def print_detailed_joint_info(results: Dict[str, Any]):
    """Print detailed information about each joint"""
    joints = results.get("joints", [])
    
    print("\n=== DETAILED JOINT INFORMATION ===")
    for joint in joints:
        print(f"\nJoint: {joint['name']} ({joint['joint_type']})")
        print(f"  Parent: {joint['parent_body']} -> Child: {joint['child_body']}")
        
        # Print coordinates
        if joint['coordinates']:
            print("  Coordinates:")
            for coord in joint['coordinates']:
                range_str = f"[{coord['range_min']:.2f}, {coord['range_max']:.2f}]"
                if coord['coordinate_type'] == 'rotational':
                    range_str += " rad"
                else:
                    range_str += " m"
                
                flags = []
                if coord['locked']:
                    flags.append("LOCKED")
                if coord['prescribed']:
                    flags.append("PRESCRIBED")
                if coord['clamped']:
                    flags.append("CLAMPED")
                
                flag_str = f" ({', '.join(flags)})" if flags else ""
                print(f"    - {coord['name']}: {coord['default_value']:.3f} {range_str}{flag_str}")
        
        # Print offset frames
        if joint.get('parent_offset_frame'):
            pof = joint['parent_offset_frame']
            print(f"  Parent Offset Frame: {pof['name']}")
            print(f"    Translation: [{pof['translation'][0]:.3f}, {pof['translation'][1]:.3f}, {pof['translation'][2]:.3f}] m")
            print(f"    Orientation: [{math.degrees(pof['orientation'][0]):.1f}°, {math.degrees(pof['orientation'][1]):.1f}°, {math.degrees(pof['orientation'][2]):.1f}°]")
        
        if joint.get('child_offset_frame'):
            cof = joint['child_offset_frame']
            print(f"  Child Offset Frame: {cof['name']}")
            print(f"    Translation: [{cof['translation'][0]:.3f}, {cof['translation'][1]:.3f}, {cof['translation'][2]:.3f}] m")
            print(f"    Orientation: [{math.degrees(cof['orientation'][0]):.1f}°, {math.degrees(cof['orientation'][1]):.1f}°, {math.degrees(cof['orientation'][2]):.1f}°]")


class CoordinateTransformer:
    """Handles coordinate system conversions between OpenSim and Blender"""
    
    @staticmethod
    def opensim_to_blender_position(opensim_pos: Tuple[float, float, float]) -> Vector:
        """
        Convert position from OpenSim (Y-up) to Blender (Z-up) coordinates
        OpenSim: X-right, Y-up, Z-forward
        Blender: X-right, Y-forward, Z-up
        """
        x, y, z = opensim_pos
        return Vector((x, -z, y))
    
    @staticmethod
    def opensim_to_blender_rotation(opensim_euler: Tuple[float, float, float], 
                                  sequence: str = 'XYZ') -> Quaternion:
        """
        Convert Euler rotation from OpenSim to Blender coordinates
        """
        # Convert to Blender coordinate system
        x, y, z = opensim_euler
        # Apply coordinate transformation: Y->Z, Z->-Y
        blender_euler = Euler((x, -z, y), sequence)
        return blender_euler.to_quaternion()
    
    @staticmethod
    def apply_offset_frame(base_transform: Matrix, 
                          translation: Tuple[float, float, float],
                          rotation: Tuple[float, float, float]) -> Matrix:
        """Apply offset frame transformation to base transform"""
        offset_translation = CoordinateTransformer.opensim_to_blender_position(translation)
        offset_rotation = CoordinateTransformer.opensim_to_blender_rotation(rotation)
        
        offset_matrix = Matrix.Translation(offset_translation) @ offset_rotation.to_matrix().to_4x4()
        return base_transform @ offset_matrix

class BoneNaming:
    """Handles OpenSim to Blender bone naming conventions"""
    
    @staticmethod
    def convert_opensim_to_blender_suffix(name: str) -> str:
        """Convert OpenSim _l/_r suffixes to Blender .L/.R convention"""
        if name.endswith('_l'):
            return name[:-2] + '.L'
        elif name.endswith('_r'):
            return name[:-2] + '.R'
        return name
    
    @staticmethod
    def create_joint_bone_name(opensim_joint_name: str) -> str:
        """Create Blender bone name for OpenSim joint"""
        converted_name = BoneNaming.convert_opensim_to_blender_suffix(opensim_joint_name)
        return f"JOINT-{converted_name}"
    
    @staticmethod
    def create_body_bone_name(opensim_body_name: str) -> str:
        """Create Blender bone name for OpenSim body"""
        converted_name = BoneNaming.convert_opensim_to_blender_suffix(opensim_body_name)
        return f"BODY-{converted_name}"

class OpenSimBone:
    """Represents a bone to be created in Blender"""
    
    def __init__(self, name: str, bone_type: str, opensim_data: Dict[str, Any]):
        self.name = name
        self.bone_type = bone_type  # 'joint' or 'body'
        self.opensim_data = opensim_data
        self.head_position = Vector((0, 0, 0))
        self.tail_position = Vector((0, 0, 1))  # Default 1 unit length
        self.rotation = Quaternion()
        self.parent_name: Optional[str] = None
        self.children: List[str] = []
        self.collection_name = "OpenSim Joints" if bone_type == 'joint' else "OpenSim Bodies"

class OpenSimToBlenderConverter:
    """Main converter class for OpenSim to Blender armature conversion"""
    
    def __init__(self, opensim_analysis: Dict[str, Any]):
        self.opensim_data = opensim_analysis
        self.bones: Dict[str, OpenSimBone] = {}
        self.armature_obj = None
        self.armature_data = None
        
        # Configuration
        self.default_bone_length = 0.1  # meters
        self.min_bone_length = 0.01     # minimum visible length
        
    def convert(self, armature_name: str = "OpenSim_Skeleton") -> bpy.types.Object:
        """
        Main conversion method
        Returns the created armature object
        """
        try:
            print(f"Starting conversion to armature: {armature_name}")
            
            # Step 1: Analyze and prepare bone data
            print("Step 1: Preparing bone data...")
            self._prepare_bone_data()
            print(f"Created {len(self.bones)} bones")
            
            # Step 2: Create armature
            print("Step 2: Creating armature...")
            self._create_armature(armature_name)
            
            # Step 3: Create bone collections
            print("Step 3: Creating bone collections...")
            self._create_bone_collections()
            
            # Step 4: Enter edit mode and create bones
            print("Step 4: Creating bones in edit mode...")
            bpy.context.view_layer.objects.active = self.armature_obj
            bpy.ops.object.mode_set(mode='EDIT')
            
            self._create_bones()
            print("Step 5: Positioning bones...")
            self._position_bones()
            print("Step 6: Setting up hierarchy...")
            self._setup_hierarchy()
            
            # Step 5: Exit edit mode and finalize
            print("Step 7: Finalizing...")
            bpy.ops.object.mode_set(mode='OBJECT')
            self._assign_bone_collections()
            self._add_metadata()
            
            print(f"Conversion completed successfully!")
            return self.armature_obj
            
        except Exception as e:
            print(f"Error during conversion: {e}")
            # Cleanup on error
            if self.armature_obj:
                bpy.data.objects.remove(self.armature_obj)
            raise
    
    def _prepare_bone_data(self):
        """Analyze OpenSim data and prepare bone structures"""
        joints = self.opensim_data.get('joints', [])
        bodies = self.opensim_data.get('bodies', {})
        hierarchy = self.opensim_data.get('joint_hierarchy', {})
        
        # Create bone data structures
        for joint in joints:
            joint_name = BoneNaming.create_joint_bone_name(joint['name'])
            body_name = BoneNaming.create_body_bone_name(joint['child_body'])
            
            # Create joint bone
            joint_bone = OpenSimBone(joint_name, 'joint', joint)
            self.bones[joint_name] = joint_bone
            
            # Create body bone (if not already exists)
            if body_name not in self.bones:
                body_data = bodies.get(joint['child_body'], {})
                body_bone = OpenSimBone(body_name, 'body', body_data)
                self.bones[body_name] = body_bone
        
        # Handle root body (ground/pelvis)
        self._handle_root_body()
        
        # Establish relationships FIRST, then calculate positions
        self._establish_relationships()
        self._calculate_bone_positions()
        
        # Apply coordinate default values to achieve rest pose
        print("\nApplying coordinate default values...")
        self._apply_coordinate_defaults_to_bodies()
    
    def _handle_root_body(self):
        """Handle the root body (typically ground or pelvis)"""
        hierarchy_tree = self.opensim_data.get('hierarchy_tree',    {})
        if hierarchy_tree and not hierarchy_tree.get('error'):
            root_body_name = hierarchy_tree['name']
            
            # Skip 'ground' and use pelvis as root if ground->pelvis exists
            if root_body_name == 'ground':
                children = hierarchy_tree.get('children', [])
                if children and children[0]['name'] == 'pelvis':
                    root_body_name = 'pelvis'
            
            blender_root_name = BoneNaming.create_body_bone_name(root_body_name)
            if blender_root_name not in self.bones:
                root_bone = OpenSimBone(blender_root_name, 'body', {'name': root_body_name})
                root_bone.head_position = Vector((0, 0, 0))  # Origin
                self.bones[blender_root_name] = root_bone
    
    def _calculate_bone_positions(self):
        """Calculate global positions for all bones based on OpenSim data"""
        # Reset all positions
        for bone in self.bones.values():
            bone.head_position = Vector((0, 0, 0))
            bone.tail_position = Vector((0, 0, self.default_bone_length))
        
        # Calculate positions hierarchically, starting from root
        self._calculate_global_positions()
    
    def _calculate_global_positions(self):
        """Calculate global positions by traversing the hierarchy"""
        # Find root bones (bones without parents)
        root_bones = [bone for bone in self.bones.values() if not bone.parent_name]
        
        print(f"\nFound {len(root_bones)} root bones:")
        for root_bone in root_bones:
            print(f"  - {root_bone.name} ({root_bone.bone_type})")
        
        # Calculate positions recursively from each root
        for root_bone in root_bones:
            print(f"\nCalculating positions from root: {root_bone.name}")
            self._calculate_bone_global_position(root_bone, Matrix.Identity(4))
    
    def _calculate_bone_global_position(self, bone: OpenSimBone, parent_global_matrix: Matrix):
        """Calculate global position for a bone given parent's global matrix"""
        
        print(f"  Calculating position for {bone.name} ({bone.bone_type})")
        print(f"    Parent matrix translation: {parent_global_matrix.translation}")
        print(f"    Children: {bone.children}")
        
        # Start with parent's global transformation
        global_matrix = parent_global_matrix.copy()
        
        if bone.bone_type == 'joint':
            # For joint bones, use the parent offset frame transformation plus coordinate default values
            joint_data = bone.opensim_data
            parent_offset = joint_data.get('parent_offset_frame')
            
            if parent_offset:
                translation = parent_offset.get('translation', (0, 0, 0))
                orientation = parent_offset.get('orientation', (0, 0, 0))
                
                print(f"    Joint parent offset: translation={translation}, orientation={orientation}")
                
                # Convert to Blender coordinates
                blender_translation = CoordinateTransformer.opensim_to_blender_position(translation)
                blender_rotation = CoordinateTransformer.opensim_to_blender_rotation(orientation)
                
                # Apply coordinate default values to get rest pose
                coordinate_rotation = self._calculate_coordinate_default_rotation(joint_data)
                final_rotation = blender_rotation @ coordinate_rotation
                
                print(f"    Converted to Blender: translation={blender_translation}")
                print(f"    Base rotation: {blender_rotation}")
                print(f"    Coordinate rotation: {coordinate_rotation}")
                print(f"    Final rotation: {final_rotation}")
                
                # Create transformation matrix
                transform_matrix = Matrix.Translation(blender_translation) @ final_rotation.to_matrix().to_4x4()
                
                # Apply transformation
                global_matrix = global_matrix @ transform_matrix
            else:
                print("    No parent offset frame found")
        
        elif bone.bone_type == 'body':
            # For body bones, use the child offset frame of the joint that creates them
            creating_joint = self._find_creating_joint(bone)
            if creating_joint:
                joint_data = creating_joint.opensim_data
                child_offset = joint_data.get('child_offset_frame')
                
                if child_offset:
                    translation = child_offset.get('translation', (0, 0, 0))
                    orientation = child_offset.get('orientation', (0, 0, 0))
                    
                    print(f"    Body child offset: translation={translation}, orientation={orientation}")
                    
                    # Convert to Blender coordinates
                    blender_translation = CoordinateTransformer.opensim_to_blender_position(translation)
                    blender_rotation = CoordinateTransformer.opensim_to_blender_rotation(orientation)
                    print(f"    Converted to Blender: translation={blender_translation}, rotation={blender_rotation}")

                    # Create transformation matrix
                    transform_matrix = Matrix.Translation(blender_translation) @ blender_rotation.to_matrix().to_4x4()
                    print(f"    Transformation matrix:\n{transform_matrix}")

                    # Apply transformation
                    global_matrix = global_matrix @ transform_matrix
                    print(f"    Updated global matrix translation: {global_matrix.translation}")
                    print(f"    Updated global matrix rotation: {global_matrix.to_quaternion()}")
                else:
                    print("    No child offset frame found")
            else:
                print("    No creating joint found")
        
        # Set the bone's global position
        bone.head_position = global_matrix.translation
        bone.tail_position = bone.head_position + Vector((0, 0, self.default_bone_length))
        bone.rotation = global_matrix.to_quaternion()
        
        print(f"    Final position: {bone.head_position}")
        
        # Recursively calculate positions for children
        for child_name in bone.children:
            child_bone = self.bones.get(child_name)
            if child_bone:
                self._calculate_bone_global_position(child_bone, global_matrix)
    
    def _calculate_coordinate_default_rotation(self, joint_data: dict[str, Any]) -> Quaternion:
        """Calculate the rotation from coordinate default values using SpatialTransform data"""
        coordinates = joint_data.get('coordinates', [])
        
        # Start with identity
        final_rotation = Quaternion()
        
        print(f"    Processing {len(coordinates)} coordinates:")
        
        for coord in coordinates:
            coord_name = coord.get('name', '')
            default_value = coord.get('default_value', 0.0)
            coord_type = coord.get('coordinate_type', 'rotational')
            
            print(f"      {coord_name}: {default_value} ({coord_type})")
            
            # Only apply rotational coordinates to bone orientation
            if coord_type == 'rotational' and abs(default_value) > 1e-6:
                # Use SpatialTransform data to determine rotation axis
                rotation_quat = self._get_coordinate_rotation(coord_name, default_value, joint_data)
                if rotation_quat:
                    final_rotation = final_rotation @ rotation_quat
                    print(f"        Applied rotation: {rotation_quat}")
        
        return final_rotation
        
        return final_rotation

    def _get_coordinate_rotation(self, coord_name: str, angle: float, joint_data: dict) -> Optional[Quaternion]:
        """Get rotation quaternion for a coordinate using SpatialTransform data"""
        
        # Look for spatial transform data
        spatial_transform = joint_data.get('spatial_transform')
        if not spatial_transform:
            print(f"        No spatial transform data for coordinate '{coord_name}', skipping")
            return None
            
        axes = spatial_transform.get('axes', [])
        if not axes:
            print(f"        No transform axes found for coordinate '{coord_name}', skipping")
            return None
            
        # Find the transform axis that controls this coordinate
        coord_axis = None
        for axis in axes:
            axis_coordinates = axis.get('coordinates', '')
            # Check if this axis is controlled by our coordinate
            if axis_coordinates == coord_name:
                coord_axis = axis
                break
                
        if not coord_axis:
            print(f"        No transform axis found for coordinate '{coord_name}', skipping")
            return None
            
        # Get the rotation axis vector
        axis_vector = coord_axis.get('axis', (0, 0, 0))
        axis_name = coord_axis.get('name', 'unknown')
        
        print(f"        Coordinate '{coord_name}' maps to axis '{axis_name}': {axis_vector}")
        
        # Only process rotation axes (translation axes should not affect bone orientation)
        if not axis_name.startswith('rotation'):
            print(f"        Skipping non-rotation axis: {axis_name}")
            return None
            
        # Convert OpenSim axis vector to Blender coordinate system
        # OpenSim: Y-up coordinate system (X, Y, Z)
        # Blender: Z-up coordinate system (X, Z, -Y) 
        # Transformation: OpenSim (x,y,z) → Blender (x,z,-y)
        opensim_axis = Vector(axis_vector)
        blender_axis = Vector((opensim_axis.x, opensim_axis.z, -opensim_axis.y))
        
        # Normalize the axis vector
        if blender_axis.length > 0:
            blender_axis.normalize()
        else:
            print(f"        Warning: Zero-length axis vector for {coord_name}")
            return None
        
        print(f"        OpenSim axis: {opensim_axis} → Blender axis: {blender_axis}")
        
        # Create rotation quaternion around the Blender axis
        # The angle is already in the correct OpenSim coordinate space,
        # we just need to apply it around the converted axis
        rotation = Quaternion(blender_axis, angle)
        
        print(f"        Created rotation: {rotation} (angle: {angle:.3f} rad = {math.degrees(angle):.1f}°)")
        
        return rotation

    def _apply_coordinate_defaults_to_bodies(self):
        """Apply coordinate default rotations to body bones"""
        print("    Applying coordinate defaults to body bones...")
        
        joints = self.opensim_data.get('joints', [])
        
        for bone_name, bone_obj in self.bones.items():
            if bone_obj.bone_type != 'body':
                continue
                
            print(f"      Processing body: {bone_name}")
            
            # Find the joint that positions this body
            positioning_joint = None
            for joint in joints:
                if joint.get('child_body') == bone_obj.opensim_data.get('name', ''):
                    positioning_joint = joint
                    break
                    
            if not positioning_joint:
                print(f"        No positioning joint found for body {bone_name}")
                continue
                
            print(f"        Positioning joint: {positioning_joint.get('name', 'unknown')}")
            
            # Calculate coordinate default rotation
            coord_rotation = self._calculate_coordinate_default_rotation(positioning_joint)
            
            if coord_rotation != Quaternion():
                # Apply the coordinate rotation to the body's orientation
                current_orientation = getattr(bone_obj, 'orientation', Quaternion())
                new_orientation = current_orientation @ coord_rotation
                bone_obj.orientation = new_orientation
                
                print("        Updated body orientation with coordinate defaults")
                print(f"        Previous: {current_orientation}")
                print(f"        New: {new_orientation}")

    def _find_creating_joint(self, body_bone: OpenSimBone) -> Optional[OpenSimBone]:
        """Find the joint that creates this body bone"""
        body_name = body_bone.opensim_data.get('name', '')
        
        for bone in self.bones.values():
            if bone.bone_type == 'joint':
                joint_data = bone.opensim_data
                if joint_data.get('child_body') == body_name:
                    return bone
        return None
    
    def _establish_relationships(self):
        """Establish parent-child relationships between bones"""
        joints = self.opensim_data.get('joints', [])
        
        print(f"Establishing relationships for {len(joints)} joints...")
        
        for joint in joints:
            joint_name = BoneNaming.create_joint_bone_name(joint['name'])
            parent_body_name = BoneNaming.create_body_bone_name(joint['parent_body'])
            child_body_name = BoneNaming.create_body_bone_name(joint['child_body'])
            
            print(f"Processing joint {joint['name']}: {joint['parent_body']} -> {joint['child_body']}")
            print(f"  Blender names: {parent_body_name} -> {joint_name} -> {child_body_name}")
            
            # Skip if parent/child don't exist or are unknown
            if (joint['parent_body'] == 'unknown' or 
                joint['child_body'] == 'unknown' or
                joint['parent_body'] == joint['child_body']):
                print("  Skipping - unknown or self-connection")
                continue
            
            # Joint's parent is the parent body
            if parent_body_name in self.bones:
                self.bones[joint_name].parent_name = parent_body_name
                self.bones[parent_body_name].children.append(joint_name)
                print(f"  Set parent: {joint_name}.parent = {parent_body_name}")
            else:
                print(f"  Warning: Parent body bone {parent_body_name} not found")
            
            # Body's parent is the joint
            if child_body_name in self.bones:
                self.bones[child_body_name].parent_name = joint_name
                self.bones[joint_name].children.append(child_body_name)
                print(f"  Set parent: {child_body_name}.parent = {joint_name}")
            else:
                print(f"  Warning: Child body bone {child_body_name} not found")
        
        # Debug: Print final relationships
        print("\nFinal bone relationships:")
        for bone_name, bone in self.bones.items():
            print(f"  {bone_name}: parent={bone.parent_name}, children={bone.children}")
    
    def _create_armature(self, name: str):
        """Create the Blender armature object"""
        # Create armature data
        self.armature_data = bpy.data.armatures.new(name)
        self.armature_data.display_type = 'STICK'
        
        # Create armature object
        self.armature_obj = bpy.data.objects.new(name, self.armature_data)
        bpy.context.collection.objects.link(self.armature_obj)
        
        # Set as active object
        bpy.context.view_layer.objects.active = self.armature_obj
    
    def _create_bone_collections(self):
        """Create bone collections for organization"""
        if hasattr(self.armature_data, 'collections'):  # Blender 4.0+
            joint_collection = self.armature_data.collections.new("OpenSim Joints")
            body_collection = self.armature_data.collections.new("OpenSim Bodies")
        # For older Blender versions, we'll assign collections after creation
    
    def _create_bones(self):
        """Create all bones in the armature"""
        edit_bones = self.armature_data.edit_bones
        
        # Create bones in order: bodies first, then joints
        # This ensures parents exist before children
        for bone in self.bones.values():
            if bone.bone_type == 'body':
                edit_bone = edit_bones.new(bone.name)
                edit_bone.head = bone.head_position
                edit_bone.tail = bone.tail_position
        
        for bone in self.bones.values():
            if bone.bone_type == 'joint':
                edit_bone = edit_bones.new(bone.name)
                edit_bone.head = bone.head_position
                edit_bone.tail = bone.tail_position
    
    def _position_bones(self):
        """Adjust bone positions and orientations to point towards children"""
        edit_bones = self.armature_data.edit_bones
        
        for bone_name, bone_data in self.bones.items():
            edit_bone = edit_bones.get(bone_name)
            if not edit_bone:
                continue
            
            # Update the edit bone's head position from calculated global position
            edit_bone.head = bone_data.head_position
            
            # Calculate tail position based on children
            if bone_data.children:
                # Point towards first child
                child_name = bone_data.children[0]
                child_bone_data = self.bones.get(child_name)
                if child_bone_data:
                    direction = child_bone_data.head_position - bone_data.head_position
                    if direction.length > self.min_bone_length:
                        edit_bone.tail = bone_data.head_position + direction
                    else:
                        # Use default direction if too close
                        edit_bone.tail = bone_data.head_position + Vector((0, 0, self.default_bone_length))
                else:
                    # Child bone not found, use default direction
                    edit_bone.tail = bone_data.head_position + Vector((0, 0, self.default_bone_length))
            else:
                # No children, use default direction
                edit_bone.tail = bone_data.head_position + Vector((0, 0, self.default_bone_length))
            
            # Ensure minimum bone length
            bone_length = (edit_bone.tail - edit_bone.head).length
            if bone_length < self.min_bone_length:
                direction = (edit_bone.tail - edit_bone.head).normalized()
                edit_bone.tail = edit_bone.head + direction * self.min_bone_length
                
            # Debug output
            print(f"Bone {bone_name}: head={edit_bone.head}, tail={edit_bone.tail}, length={bone_length:.3f}")
    
    def _setup_hierarchy(self):
        """Establish parent-child relationships"""
        edit_bones = self.armature_data.edit_bones
        
        for bone_name, bone_data in self.bones.items():
            if bone_data.parent_name:
                edit_bone = edit_bones.get(bone_name)
                parent_bone = edit_bones.get(bone_data.parent_name)
                
                if edit_bone and parent_bone:
                    edit_bone.parent = parent_bone
    
    def _assign_bone_collections(self):
        """Assign bones to their respective collections"""
        if hasattr(self.armature_data, 'collections'):  # Blender 4.0+
            joint_collection = self.armature_data.collections.get("OpenSim Joints")
            body_collection = self.armature_data.collections.get("OpenSim Bodies")
            
            for bone_name, bone_data in self.bones.items():
                pose_bone = self.armature_obj.pose.bones.get(bone_name)
                if pose_bone:
                    if bone_data.bone_type == 'joint' and joint_collection:
                        joint_collection.assign(pose_bone)
                    elif bone_data.bone_type == 'body' and body_collection:
                        body_collection.assign(pose_bone)
    
    def _add_metadata(self):
        """Add OpenSim metadata as custom properties"""
        # Add model info as custom properties
        model_info = self.opensim_data.get('model_info', {})
        for key, value in model_info.items():
            self.armature_obj[f"opensim_{key}"] = str(value)
        
        # Add coordinate summary
        coord_summary = self.opensim_data.get('coordinate_summary', {})
        for key, value in coord_summary.items():
            self.armature_obj[f"opensim_coords_{key}"] = value

    def _create_body_objects(self):
        """Create Body objects from the OpenSim analysis for better organization"""
        print("Creating Body objects for better organization...")
        
        # Get analysis object
        analyzer = OpenSimSkeletonAnalyzer("")  # Empty path since we have data
        analyzer.bodies = self.opensim_data.get('bodies', {})
        analyzer.joints = self.opensim_data.get('joints', [])
        
        # Create a mapping from body name to Body object
        self.body_objects = {}
        
        for body_name, body_data in analyzer.bodies.items():
            # Find offset frames for this body
            offset_frames = []
            for joint in analyzer.joints:
                if joint.parent_body == body_name and joint.parent_offset_frame:
                    offset_frames.append(joint.parent_offset_frame)
                if joint.child_body == body_name and joint.child_offset_frame:
                    offset_frames.append(joint.child_offset_frame)
            
            # Create the Body object
            body_obj = Body(
                name=body_name,
                mass=body_data.get('mass', 1.0),
                mass_center=body_data.get('mass_center', (0, 0, 0)),
                inertia=body_data.get('inertia', (1, 1, 1, 0, 0, 0)),
                offset_frames=offset_frames
            )
            
            self.body_objects[body_name] = body_obj
        
        # Set up body-to-body relationships through joints
        for joint in analyzer.joints:
            parent_body = self.body_objects.get(joint.parent_body)
            child_body = self.body_objects.get(joint.child_body)
            
            if parent_body and child_body:
                # Set joint references in Body objects
                joint.parent_body_obj = parent_body
                joint.child_body_obj = child_body
        
        print(f"Created {len(self.body_objects)} Body objects")

    def _create_bones_from_body_hierarchy(self):
        """Create Blender bones using the Body/Joint hierarchy"""
        print("Creating bones from Body/Joint hierarchy...")
        
        # Get joints from opensim_data
        joints = self.opensim_data.get('joints', [])
        
        # Find the root body (usually 'ground' or one with no parent)
        root_bodies = []
        child_bodies = set()
        
        for joint in joints:
            child_bodies.add(joint.child_body)
        
        for body_name in self.body_objects:
            if body_name not in child_bodies:
                root_bodies.append(body_name)
        
        if not root_bodies:
            # Fallback: use first body as root
            root_bodies = [list(self.body_objects.keys())[0]]
        
        print(f"Root bodies: {root_bodies}")
        
        # Create bones recursively from root
        created_bones = set()
        for root_body in root_bodies:
            self._create_bone_recursive(root_body, None, created_bones, joints)

    def _create_bone_recursive(self, body_name: str, parent_bone_name: str, created_bones: set, joints: list):
        """Recursively create bones for a body and its children"""
        if body_name in created_bones:
            return
        
        created_bones.add(body_name)
        
        # Get body object
        body = self.body_objects.get(body_name)
        if not body:
            print(f"Warning: Body {body_name} not found")
            return
        
        # Create bone for this body
        bone = self.armature_data.edit_bones.new(body_name)
        
        if parent_bone_name and parent_bone_name in self.armature_data.edit_bones:
            bone.parent = self.armature_data.edit_bones[parent_bone_name]
            
            # Find the joint connecting parent to this body
            connecting_joint = None
            for joint in joints:
                if joint.child_body == body_name:
                    connecting_joint = joint
                    break
            
            if connecting_joint:
                # Use joint transformation to position bone
                joint_transform = connecting_joint.get_joint_transform()
                
                # Convert to Blender coordinate system and apply to bone
                parent_bone = self.armature_data.edit_bones[parent_bone_name]
                
                # Start from parent bone's tail
                bone.head = parent_bone.tail
                
                # Apply transformation to get bone direction and length
                # Extract translation from transform matrix
                translation = joint_transform.to_translation()
                blender_translation = Vector((translation.x, translation.z, -translation.y))
                
                # Set bone tail position
                bone.tail = bone.head + blender_translation
                
                # Ensure minimum bone length
                if (bone.tail - bone.head).length < 0.01:
                    bone.tail = bone.head + Vector((0, 0, 0.05))
            else:
                # Default positioning relative to parent
                parent_bone = self.armature_data.edit_bones[parent_bone_name]
                bone.head = parent_bone.tail
                bone.tail = bone.head + Vector((0, 0, 0.1))
        else:
            # Root bone positioning
            bone.head = Vector((0, 0, 0))
            bone.tail = Vector((0, 0, 0.1))
        
        # Find child bodies connected through joints
        child_bodies = []
        for joint in joints:
            if joint.parent_body == body_name:
                child_bodies.append(joint.child_body)
        
        # Recursively create bones for children
        for child_body in child_bodies:
            self._create_bone_recursive(child_body, body_name, created_bones, joints)

    def _apply_joint_transformations(self):
        """Apply coordinate transformations using joint spatial transforms"""
        print("Applying joint transformations using spatial transforms...")
        
        joints = self.opensim_data.get('joints', [])
        
        for joint in joints:
            if not joint.coordinates or not joint.spatial_transform:
                continue
            
            # Find the child bone
            child_bone_name = joint.child_body
            if child_bone_name not in bpy.context.object.pose.bones:
                continue
            
            pose_bone = bpy.context.object.pose.bones[child_bone_name]
            
            # Get coordinate default rotation
            coord_rotation = joint.get_coordinate_default_rotation()
            
            # Apply the rotation to the pose bone
            pose_bone.rotation_mode = 'QUATERNION'
            pose_bone.rotation_quaternion = coord_rotation.to_quaternion()
            
            print(f"Applied coordinate rotation to {child_bone_name}: {[c.name for c in joint.coordinates]}")


# IMPORTANT!!! DO NOT CHANGE THE CODE BELOW THIS LINE WITHOUT CONSULTING THE USER !!!
import bpy

# Clear existing armatures
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Load and analyze OpenSim model
osim_file = "C:/temp/aikido-2024-08-25-harri-tests6/h5koe/kinematics/h5koe_0-700_filt_butterworth.osim"
analyzer = OpenSimSkeletonAnalyzer(osim_file)
opensim_data = analyzer.analyze()

# Convert to Blender armature
converter = OpenSimToBlenderConverter(opensim_data)
armature = converter.convert("OpenSim_Skeleton")

print(f"Created armature: {armature.name}")
print(f"Total bones: {len(armature.data.bones)}")

