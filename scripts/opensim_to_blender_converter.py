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
    joint_name: str  # The joint this offset frame belongs to
    parent_body: str
    translation: Tuple[float, float, float]  # meters
    orientation: Tuple[float, float, float]  # radians (x-y-z rotation sequence)
    
    @property
    def unique_name(self) -> str:
        """Get globally unique name by combining joint and frame names"""
        return f"{self.joint_name}:{self.name}"
    
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
    
    def get_offset_frame(self, frame_name: str, joint_name: str = None) -> Optional[OffsetFrame]:
        """Get an offset frame by name, optionally filtered by joint"""
        if joint_name:
            # Look for frame with specific joint
            unique_name = f"{joint_name}:{frame_name}"
            return self.offset_frames.get(unique_name)
        else:
            # Look for any frame with this name
            for unique_name, frame in self.offset_frames.items():
                if frame.name == frame_name:
                    return frame
            return None
    
    def get_transform(self, from_frame: str = None, to_frame: str = None, 
                     from_joint: str = None, to_joint: str = None) -> Matrix:
        """
        Get transformation matrix from one frame to another within this body
        
        Args:
            from_frame: Source frame name (optional if only one frame for from_joint)
            to_frame: Target frame name (optional if only one frame for to_joint)
            from_joint: Joint name for source frame (None for body's root frame)
            to_joint: Joint name for target frame (None for body's root frame)
            
        Returns:
            4x4 transformation matrix
        """
        # Identity if same frame
        if from_frame == to_frame and from_joint == to_joint:
            return Matrix.Identity(4)
        
        # Get transform from body root to target frame
        if from_joint is None:  # from body root
            target_frame = self._get_frame_for_joint(to_frame, to_joint)
            if target_frame:
                return target_frame.get_transform_matrix()
            else:
                return Matrix.Identity(4)
        
        # Get transform from source frame to body root
        elif to_joint is None:  # to body root
            source_frame = self._get_frame_for_joint(from_frame, from_joint)
            if source_frame:
                return source_frame.get_transform_matrix().inverted()
            else:
                return Matrix.Identity(4)
        
        # Transform from one frame to another via body root
        else:
            source_frame = self._get_frame_for_joint(from_frame, from_joint)
            target_frame = self._get_frame_for_joint(to_frame, to_joint)
            
            if source_frame and target_frame:
                # from_frame -> body -> to_frame
                source_to_body = source_frame.get_transform_matrix().inverted()
                body_to_target = target_frame.get_transform_matrix()
                return source_to_body @ body_to_target
            else:
                return Matrix.Identity(4)
    
    def _get_frame_for_joint(self, frame_name: str = None, joint_name: str = None) -> OffsetFrame | None:
        """
        Helper method to get a frame for a specific joint
        If frame_name is None and there's only one frame for the joint, return that frame
        """
        if joint_name is None:
            return None
            
        if frame_name is not None:
            # Look for specific frame
            unique_name = f"{joint_name}:{frame_name}"
            return self.offset_frames.get(unique_name)
        else:
            # Look for any frame from this joint (useful when there's only one)
            matching_frames = []
            for unique_name, frame in self.offset_frames.items():
                if frame.joint_name == joint_name:
                    matching_frames.append(frame)
            
            if len(matching_frames) == 1:
                return matching_frames[0]
            elif len(matching_frames) > 1:
                # Multiple frames for this joint, need to specify frame_name
                print(f"Warning: Multiple frames found for joint {joint_name}, specify frame_name")
                return None
            else:
                return None

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
                # OpenSim: Y-up  → Blender: Z-up
                opensim_axis = Vector(axis_vector)
                blender_axis = Vector((opensim_axis.x, -opensim_axis.z, opensim_axis.y))
                
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
                        jointset.findall('.//FreeJoint') + \
                        jointset.findall('.//UniversalJoint')

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
        
        # Get joint name for unique frame identification
        joint_name = joint_elem.get('name', 'unknown')
        
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
                    joint_name=joint_name,
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
                
                # Extract function information
                function_data = self._extract_transform_function(axis_elem)
                
                axes.append({
                    'name': axis_name,
                    'coordinates': coordinates,
                    'axis': axis_vector,
                    'function': function_data
                })
        
        transform_data['axes'] = axes
        return transform_data
    
    def _extract_transform_function(self, axis_elem) -> Dict[str, Any]:
        """Extract function information from TransformAxis"""
        function_data = {'type': 'none'}
        
        # Check for LinearFunction
        linear_func = axis_elem.find('.//LinearFunction')
        if linear_func is not None:
            function_data['type'] = 'linear'
            coeffs_elem = linear_func.find('.//coefficients')
            if coeffs_elem is not None and coeffs_elem.text:
                try:
                    coeffs = [float(x) for x in coeffs_elem.text.strip().split()]
                    function_data['coefficients'] = coeffs
                except ValueError:
                    function_data['coefficients'] = [1, 0]  # Default
            else:
                function_data['coefficients'] = [1, 0]  # Default
            return function_data
        
        # Check for MultiplierFunction
        mult_func = axis_elem.find('.//MultiplierFunction')
        if mult_func is not None:
            function_data['type'] = 'multiplier'
            scale_elem = mult_func.find('.//scale')
            if scale_elem is not None and scale_elem.text:
                try:
                    function_data['scale'] = float(scale_elem.text.strip())
                except ValueError:
                    function_data['scale'] = 1.0
            else:
                function_data['scale'] = 1.0
            
            # Check for inner constant function
            const_func = mult_func.find('.//Constant')
            if const_func is not None:
                value_elem = const_func.find('.//value')
                if value_elem is not None and value_elem.text:
                    try:
                        function_data['constant_value'] = float(value_elem.text.strip())
                    except ValueError:
                        function_data['constant_value'] = 0.0
                else:
                    function_data['constant_value'] = 0.0
            return function_data
        
        # Check for SimmSpline
        spline_func = axis_elem.find('.//SimmSpline')
        if spline_func is not None:
            function_data['type'] = 'spline'
            
            # Extract x and y values
            x_elem = spline_func.find('.//x')
            y_elem = spline_func.find('.//y')
            
            x_values = []
            y_values = []
            
            if x_elem is not None and x_elem.text:
                try:
                    x_values = [float(x) for x in x_elem.text.strip().split()]
                except ValueError:
                    pass
            
            if y_elem is not None and y_elem.text:
                try:
                    y_values = [float(y) for y in y_elem.text.strip().split()]
                except ValueError:
                    pass
            
            function_data['x_values'] = x_values
            function_data['y_values'] = y_values
            return function_data
        
        return function_data
    
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


def print_body_joint_hierarchy(converter: 'OpenSimToBlenderConverter', indent_size: int = 2):
    """
    Print the Body/Joint hierarchy as an indented tree with key parameters
    
    Args:
        converter: OpenSimToBlenderConverter instance with body_objects and joint_objects
        indent_size: Number of spaces per indentation level
    """
    if not hasattr(converter, 'body_objects') or not hasattr(converter, 'joint_objects'):
        print("Error: Converter must have body_objects and joint_objects created")
        return
    
    print("\n=== BODY/JOINT HIERARCHY ===")
    
    # Find root bodies (bodies that are not children of any joint)
    child_bodies = set()
    for joint in converter.joint_objects:
        child_bodies.add(joint.child_body)
    
    root_bodies = []
    for body_name in converter.body_objects:
        if body_name not in child_bodies:
            root_bodies.append(body_name)
    
    if not root_bodies:
        root_bodies = [list(converter.body_objects.keys())[0]]  # Fallback
    
    root_bodies = ["pelvis"]
    print(f"Root bodies: {', '.join(root_bodies)}")
    
    # Print hierarchy recursively from each root
    visited = set()
    for root_body in root_bodies:
        _print_body_recursive(converter, root_body, 0, indent_size, visited)


def _print_body_recursive(converter: 'OpenSimToBlenderConverter', body_name: str, depth: int, indent_size: int, visited: set):
    """Recursively print body and its connected joints/bodies"""
    if body_name in visited:
        prefix = " " * (depth * indent_size)
        print(f"{prefix}[CIRCULAR REFERENCE: {body_name}]")
        return
    
    visited.add(body_name)
    prefix = " " * (depth * indent_size)
    
    # Print body information
    body = converter.body_objects.get(body_name)
    if body:
        print(f"{prefix}📦 BODY: {body_name}")
        print(f"{prefix}   Mass: {body.mass:.3f} kg")
        print(f"{prefix}   Mass Center: [{body.mass_center[0]:.3f}, {body.mass_center[1]:.3f}, {body.mass_center[2]:.3f}] m")
        
        # Print offset frames
        if body.offset_frames:
            print(f"{prefix}   📍 Offset Frames ({len(body.offset_frames)}):")
            for unique_name, frame in body.offset_frames.items():
                print(f"{prefix}     • {frame.name} (from {frame.joint_name})")
                print(f"{prefix}       Translation: [{frame.translation[0]:.3f}, {frame.translation[1]:.3f}, {frame.translation[2]:.3f}] m")
                print(f"{prefix}       Orientation: [{math.degrees(frame.orientation[0]):.1f}°, {math.degrees(frame.orientation[1]):.1f}°, {math.degrees(frame.orientation[2]):.1f}°]")
        else:
            print(f"{prefix}   📍 No offset frames")
    else:
        print(f"{prefix}📦 BODY: {body_name} [NOT FOUND]")
    
    # Find and print child joints
    child_joints = []
    for joint in converter.joint_objects:
        if joint.parent_body == body_name:
            child_joints.append(joint)
    
    for joint in child_joints:
        joint_prefix = " " * ((depth + 1) * indent_size)
        print(f"{joint_prefix}🔗 JOINT: {joint.name} ({joint.joint_type})")
        print(f"{joint_prefix}   Parent Frame: {joint.parent_frame}")
        print(f"{joint_prefix}   Child Frame: {joint.child_frame}")
        print(f"{joint_prefix}   Connection: {joint.parent_body} → {joint.child_body}")
        
        # Print coordinates (DOFs)
        if joint.coordinates:
            print(f"{joint_prefix}   🎛️ Coordinates ({len(joint.coordinates)}):")
            for coord in joint.coordinates:
                coord_info = f"{coord.name}: {coord.default_value:.3f}"
                if coord.coordinate_type == 'rotational':
                    coord_info += f" rad ({math.degrees(coord.default_value):.1f}°)"
                else:
                    coord_info += " m"
                
                flags = []
                if coord.locked:
                    flags.append("LOCKED")
                if coord.prescribed:
                    flags.append("PRESCRIBED")
                if coord.clamped:
                    flags.append("CLAMPED")
                
                if flags:
                    coord_info += f" [{', '.join(flags)}]"
                
                print(f"{joint_prefix}     • {coord_info}")
                print(f"{joint_prefix}       Range: [{coord.range_min:.2f}, {coord.range_max:.2f}]")
        else:
            print(f"{joint_prefix}   🎛️ No coordinates (0 DOF)")
        
        # Print offset frames
        if joint.parent_offset_frame or joint.child_offset_frame:
            print(f"{joint_prefix}   📍 Offset Frames:")
            if joint.parent_offset_frame:
                pof = joint.parent_offset_frame
                print(f"{joint_prefix}     • Parent: {pof.name}")
                print(f"{joint_prefix}       Translation: [{pof.translation[0]:.3f}, {pof.translation[1]:.3f}, {pof.translation[2]:.3f}] m")
                print(f"{joint_prefix}       Orientation: [{math.degrees(pof.orientation[0]):.1f}°, {math.degrees(pof.orientation[1]):.1f}°, {math.degrees(pof.orientation[2]):.1f}°]")
            if joint.child_offset_frame:
                cof = joint.child_offset_frame
                print(f"{joint_prefix}     • Child: {cof.name}")
                print(f"{joint_prefix}       Translation: [{cof.translation[0]:.3f}, {cof.translation[1]:.3f}, {cof.translation[2]:.3f}] m")
                print(f"{joint_prefix}       Orientation: [{math.degrees(cof.orientation[0]):.1f}°, {math.degrees(cof.orientation[1]):.1f}°, {math.degrees(cof.orientation[2]):.1f}°]")
        
        # Print spatial transform info
        if joint.spatial_transform:
            st = joint.spatial_transform
            if st.get('axes'):
                print(f"{joint_prefix}   🎯 Spatial Transform ({len(st['axes'])} axes):")
                for axis in st['axes']:
                    axis_info = f"{axis.get('name', 'unknown')}: {axis.get('coordinates', 'none')}"
                    axis_vector = axis.get('axis', (0, 0, 0))
                    axis_info += f" → [{axis_vector[0]:.1f}, {axis_vector[1]:.1f}, {axis_vector[2]:.1f}]"
                    print(f"{joint_prefix}     • {axis_info}")
        
        # Print body relationships
        if joint.parent_body_obj and joint.child_body_obj:
            print(f"{joint_prefix}   🔗 Body Objects: Connected")
        elif joint.parent_body_obj or joint.child_body_obj:
            missing = "child" if not joint.child_body_obj else "parent"
            print(f"{joint_prefix}   🔗 Body Objects: Missing {missing}")
        else:
            print(f"{joint_prefix}   🔗 Body Objects: Not connected")
        
        # Recursively print child body
        _print_body_recursive(converter, joint.child_body, depth + 2, indent_size, visited.copy())


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
        self.body_objects: Dict[str, Body] = {}  # New Body/Joint hierarchy
        self.joint_objects: list[Joint] = []  # New Joint objects
        self.bones: Dict[str, OpenSimBone] = {}  # Keep for compatibility
        self.armature_obj = None
        self.armature_data = None
        
        # Configuration
        self.default_bone_length = 0.1  # meters
        self.min_bone_length = 0.01     # minimum visible length
        
    def convert(self, armature_name: str = "OpenSim_Skeleton") -> bpy.types.Object:
        """
        Main conversion method using new Body/Joint hierarchy
        Returns the created armature object
        """
        try:
            print(f"Starting conversion to armature: {armature_name}")
            
            # Step 1: Create Body objects for better organization
            print("Step 1: Creating Body objects...")
            self._create_body_objects()
            print(f"Created {len(self.body_objects)} body objects")
            
            # Print hierarchy for debugging
            print("\nBody/Joint Hierarchy:")
            print_body_joint_hierarchy(self)
            
            # Step 2: Create armature
            print("Step 2: Creating armature...")
            self._create_armature(armature_name)
            
            # Step 3: Enter edit mode and create bones using Body/Joint hierarchy
            print("Step 3: Creating bones from Body/Joint hierarchy...")
            bpy.context.view_layer.objects.active = self.armature_obj
            bpy.ops.object.mode_set(mode='EDIT')
            
            self._create_bones_from_body_hierarchy()
            
            # Step 4: Switch to pose mode and apply coordinate transformations
            print("Step 4: Applying joint transformations...")
            bpy.ops.object.mode_set(mode='POSE')
            self._apply_joint_transformations()
            
            # Step 5: Setup animation system for PinJoints
            print("Step 5: Setting up animation system...")
            self._setup_animation_system()
            
            # Step 6: Exit to object mode and finalize
            print("Step 6: Finalizing...")
            bpy.ops.object.mode_set(mode='OBJECT')
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

    def _calculate_coordinate_default_rotation_for_joint(self, joint: Joint) -> Quaternion:
        """Calculate the rotation from coordinate default values for a Joint object"""
        if not joint.coordinates:
            return Quaternion()
        
        # Start with identity
        final_rotation = Quaternion()
        
        print(f"    Processing {len(joint.coordinates)} coordinates for joint {joint.name}:")
        
        for coord in joint.coordinates:
            print(f"      {coord.name}: {coord.default_value} ({coord.coordinate_type})")
            
            # Only apply rotational coordinates to bone orientation
            if coord.coordinate_type == 'rotational' and abs(coord.default_value) > 1e-6:
                # Use SpatialTransform data to determine rotation axis
                if joint.spatial_transform:
                    # Convert joint data to dict format for compatibility
                    coord_list = [
                        {'name': c.name, 'default_value': c.default_value, 'coordinate_type': c.coordinate_type} 
                        for c in joint.coordinates
                    ]
                    joint_data = {
                        'spatial_transform': joint.spatial_transform,
                        'coordinates': coord_list
                    }
                    rotation_quat = self._get_coordinate_rotation(coord.name, coord.default_value, joint_data)
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
        blender_axis = Vector((opensim_axis.x, -opensim_axis.z, opensim_axis.y))
        
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
        
        # Get data from opensim_data (these are dictionaries, not objects yet)
        joints_data = self.opensim_data.get('joints', [])
        bodies_data = self.opensim_data.get('bodies', {})
        
        # First, convert joint dictionaries to Joint objects
        self.joint_objects = []
        for joint_dict in joints_data:
            # Create Coordinate objects from joint data
            coordinates = []
            if 'coordinates' in joint_dict:
                for coord_dict in joint_dict['coordinates']:
                    coord = Coordinate(
                        name=coord_dict['name'],
                        default_value=coord_dict.get('default_value', 0.0),
                        range_min=coord_dict.get('range', [-180, 180])[0],
                        range_max=coord_dict.get('range', [-180, 180])[1],
                        clamped=coord_dict.get('clamped', False),
                        locked=coord_dict.get('locked', False), 
                        prescribed=coord_dict.get('prescribed', False),
                        coordinate_type=coord_dict.get('coordinate_type', 'rotational')
                    )
                    coordinates.append(coord)
            
            # Create OffsetFrame objects
            parent_offset_frame = None
            child_offset_frame = None
            
            if 'parent_offset_frame' in joint_dict:
                pof_data = joint_dict['parent_offset_frame']
                parent_offset_frame = OffsetFrame(
                    name=pof_data['name'],
                    joint_name=joint_dict['name'],
                    parent_body=joint_dict['parent_body'],
                    translation=pof_data.get('translation', (0, 0, 0)),
                    orientation=pof_data.get('orientation', (0, 0, 0))
                )
            
            if 'child_offset_frame' in joint_dict:
                cof_data = joint_dict['child_offset_frame']
                child_offset_frame = OffsetFrame(
                    name=cof_data['name'],
                    joint_name=joint_dict['name'],
                    parent_body=joint_dict['child_body'],
                    translation=cof_data.get('translation', (0, 0, 0)),
                    orientation=cof_data.get('orientation', (0, 0, 0))
                )
            
            # Create Joint object
            joint = Joint(
                name=joint_dict['name'],
                joint_type=joint_dict.get('joint_type', 'CustomJoint'),
                parent_frame=joint_dict.get('parent_frame', ''),
                child_frame=joint_dict.get('child_frame', ''),
                parent_body=joint_dict['parent_body'],
                child_body=joint_dict['child_body'],
                coordinates=coordinates,
                parent_offset_frame=parent_offset_frame,
                child_offset_frame=child_offset_frame,
                spatial_transform=joint_dict.get('spatial_transform')
            )
            
            self.joint_objects.append(joint)
        
        # Create Body objects
        self.body_objects = {}
        
        for body_name, body_data in bodies_data.items():
            # Find offset frames for this body from joints
            offset_frames = {}  # Use dict with unique names
            for joint in self.joint_objects:
                if joint.parent_body == body_name and joint.parent_offset_frame:
                    frame = joint.parent_offset_frame
                    offset_frames[frame.unique_name] = frame
                if joint.child_body == body_name and joint.child_offset_frame:
                    frame = joint.child_offset_frame
                    offset_frames[frame.unique_name] = frame
            
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
        for joint in self.joint_objects:
            parent_body = self.body_objects.get(joint.parent_body)
            child_body = self.body_objects.get(joint.child_body)
            
            if parent_body and child_body:
                # Set joint references in Body objects
                joint.parent_body_obj = parent_body
                joint.child_body_obj = child_body
        
        print(f"Created {len(self.body_objects)} Body objects and {len(self.joint_objects)} Joint objects")

    def _create_bones_from_body_hierarchy(self):
        """
        Create Blender bones with new approach:
        - JOINT-<joint_name>: from parent socket to child socket
        - BODY-<body_name>-<joint_name>: for each body, from connection point to body coordinate frame
        """
        print("Creating bones with new socket-based approach...")
        
        # Step 1: Create all joint bones (JOINT-<joint_name>)
        print("Creating joint bones...")
        for joint in self.joint_objects:
            self._create_joint_bone(joint)
        
        # Step 2: Create body bones for all bodies (including leaf bodies)
        print("Creating body bones...")
        self._create_all_body_bones()
        
        # Step 3: Setup hierarchy relationships
        print("Setting up bone hierarchy...")
        self._setup_new_bone_hierarchy()

    def _create_joint_bone(self, joint):
        """Create a bone from parent socket to child socket for a joint"""
        joint_bone_name = f"JOINT-{joint.name}"
        
        # Get socket positions
        parent_socket_pos = self._get_joint_socket_position(joint, is_parent=True)
        child_socket_pos = self._get_joint_socket_position(joint, is_parent=False)
        
        # Create the bone
        bone = self.armature_data.edit_bones.new(joint_bone_name)
        bone.head = parent_socket_pos
        bone.tail = child_socket_pos
        
        # Ensure minimum bone length
        bone_length = (bone.tail - bone.head).length
        if bone_length < 0.01:
            # Add small offset in Z direction
            bone.tail = bone.head + Vector((0, 0, 0.05))
        
        print(f"Created joint bone: {joint_bone_name} from {parent_socket_pos} to {child_socket_pos}")

    def _create_all_body_bones(self):
        """Create bones for all bodies in the model, including leaf bodies"""
        # Get all bodies in the model
        all_bodies = set(self.body_objects.keys())
        
        # For each body, create a bone from its connection point to its coordinate frame origin
        for body_name in all_bodies:
            if body_name == "ground":
                continue  # Skip ground body
                
            self._create_body_bone(body_name)
    
    def _get_child_joints_for_body(self, body_name: str):
        """Get all joints that have this body as parent"""
        child_joints = []
        for joint in self.joint_objects:
            if joint.parent_body == body_name:
                child_joints.append(joint)
        return child_joints
    
    def _create_body_bone(self, body_name: str):
        """Create a bone for a specific body"""
        # Find the joint that connects to this body (creates this body)
        connecting_joint = None
        for joint in self.joint_objects:
            if joint.child_body == body_name:
                connecting_joint = joint
                break
        
        if connecting_joint is None:
            print(f"Warning: No connecting joint found for body {body_name}")
            return
        
        # Find child joints for this body
        child_joints = self._get_child_joints_for_body(body_name)
        
        # Start position: the connection point (child socket of the connecting joint)
        connection_pos = self._get_joint_socket_position(connecting_joint, is_parent=False)
        
        if child_joints:
            # Create bones to each child joint socket
            for child_joint in child_joints:
                # Create bone name with new format: BODY-<body_name>-<child_joint_name>
                body_bone_name = f"BODY-{body_name}-{child_joint.name}"
                
                # End position: parent socket of the child joint
                child_socket_pos = self._get_joint_socket_position(child_joint, is_parent=True)
                
                # Create the bone
                bone = self.armature_data.edit_bones.new(body_bone_name)
                bone.head = connection_pos
                bone.tail = child_socket_pos
                
                # Ensure minimum bone length
                bone_length = (bone.tail - bone.head).length
                if bone_length < 0.01:
                    # For very short bones, extend in a small offset
                    direction = (bone.tail - bone.head).normalized() if bone_length > 0 else Vector((0, 0, 1))
                    bone.tail = bone.head + direction * 0.05
                
                print(f"Created body bone: {body_bone_name}")
                print(f"  From {connection_pos} to {child_socket_pos} (length: {bone_length:.3f})")
        else:
            # This is a leaf body - create a bone to the body's mass center
            body_bone_name = f"BODY-{body_name}-{connecting_joint.name}"
            body_mass_center_pos = self._get_body_mass_center_global(body_name)
            
            # Create the bone
            bone = self.armature_data.edit_bones.new(body_bone_name)
            bone.head = connection_pos
            bone.tail = body_mass_center_pos
            
            # Ensure minimum bone length
            bone_length = (bone.tail - bone.head).length
            if bone_length < 0.01:
                # For very short bones, extend in a small offset
                direction = (bone.tail - bone.head).normalized() if bone_length > 0 else Vector((0, 0, 1))
                bone.tail = bone.head + direction * 0.05
            
            print(f"Created leaf body bone: {body_bone_name}")
            print(f"  From {connection_pos} to {body_mass_center_pos} (length: {bone_length:.3f})")
    
    def _get_body_coordinate_origin(self, body_name: str):
        """Get the origin of a body's coordinate frame in global space"""
        # The body's coordinate origin is at the global transform to that body
        global_transform = self._get_global_transform_to_body(body_name)
        
        # Extract just the translation component (coordinate origin)
        origin = global_transform.to_translation()
        
        # Convert from OpenSim coordinate system (Y-up) to Blender (Z-up)
        # OpenSim: X-right, Y-up, Z-forward → Blender: X-right, Y-forward, Z-up
        blender_origin = Vector((origin.x, -origin.z, origin.y))
        
        return blender_origin

    def _get_body_mass_center_global(self, body_name: str):
        """Get the global position of a body's mass center"""
        body = self.body_objects.get(body_name)
        if not body:
            print(f"Warning: Body {body_name} not found")
            return Vector((0, 0, 0))
        
        # Get the global transformation to the body's coordinate frame
        global_transform = self._get_global_transform_to_body(body_name)
        
        # Get the mass center in body's local coordinates
        local_mass_center = Vector(body.mass_center)
        
        # Transform mass center to global coordinates
        local_mass_center_4d = Vector((local_mass_center.x, local_mass_center.y, local_mass_center.z, 1.0))
        global_mass_center_4d = global_transform @ local_mass_center_4d
        global_mass_center = global_mass_center_4d.xyz
        
        # Convert from OpenSim coordinate system (Y-up) to Blender (Z-up)
        # OpenSim: X-right, Y-up, Z-forward → Blender: X-right, Y-forward, Z-up
        blender_mass_center = Vector((global_mass_center.x, -global_mass_center.z, global_mass_center.y))
        
        return blender_mass_center

    def _get_joint_socket_position(self, joint, is_parent: bool):
        """Get the global socket position for a joint (parent or child side)"""
        try:
            # Get the appropriate offset frame
            if is_parent:
                offset_frame = joint.parent_offset_frame
                body_name = joint.parent_body
            else:
                offset_frame = joint.child_offset_frame
                body_name = joint.child_body
            
            if offset_frame is None:
                # No offset frame - use body center or origin
                if body_name == "ground":
                    return Vector((0, 0, 0))
                else:
                    # For bodies without offset frames, use the global transform chain
                    return self._get_body_global_position(body_name)
            
            # Calculate global position by traversing hierarchy from root
            global_transform = self._get_global_transform_to_body(body_name)
            
            # Get local transform from offset frame
            local_transform = offset_frame.get_transform_matrix()
            
            # Combine global body transform with local offset frame transform
            final_transform = global_transform @ local_transform
            
            # Extract translation (socket position)
            translation = final_transform.to_translation()
            
            # Convert from OpenSim coordinate system (Y-up) to Blender (Z-up)
            # OpenSim: X-right, Y-up, Z-forward → Blender: X-right, Y-forward, Z-up
            blender_pos = Vector((translation.x, -translation.z, translation.y))
            
            return blender_pos
            
        except Exception as e:
            print(f"Error getting socket position for joint {joint.name} ({'parent' if is_parent else 'child'}): {e}")
            return Vector((0, 0, 0))

    def _get_body_global_position(self, body_name: str):
        """Get the global position of a body's center"""
        body = self.body_objects.get(body_name)
        if body:
            # Convert body mass center to Blender coordinates
            # OpenSim: X-right, Y-up, Z-forward → Blender: X-right, Y-forward, Z-up
            mc = body.mass_center
            return Vector((mc[0], -mc[2], mc[1]))
        return Vector((0, 0, 0))

    def _get_global_transform_to_body(self, target_body_name: str):
        """
        Calculate the global transformation matrix from root to the target body
        by traversing the joint hierarchy
        """
        if target_body_name == "ground":
            return Matrix.Identity(4)
        
        # Find the chain of joints from root to target body
        joint_chain = self._find_joint_chain_to_body(target_body_name)
        
        if not joint_chain:
            print(f"Warning: No joint chain found to body {target_body_name}")
            return Matrix.Identity(4)
        
        # Accumulate transformations along the chain
        global_transform = Matrix.Identity(4)
        
        for joint in joint_chain:
            # Get the joint's transformation
            joint_transform = self._get_joint_global_transform(joint)
            global_transform = global_transform @ joint_transform
        
        return global_transform

    def _find_joint_chain_to_body(self, target_body_name: str):
        """
        Find the chain of joints from root (ground) to the target body
        Returns list of joints in order from root to target
        """
        if target_body_name == "ground":
            return []
        
        # Find the joint that creates this body
        target_joint = None
        for joint in self.joint_objects:
            if joint.child_body == target_body_name:
                target_joint = joint
                break
        
        if not target_joint:
            print(f"Warning: No joint found that creates body {target_body_name}")
            return []
        
        # Recursively build the chain
        parent_chain = self._find_joint_chain_to_body(target_joint.parent_body)
        return parent_chain + [target_joint]

    def _get_joint_global_transform(self, joint):
        """
        Get the transformation matrix for a joint, combining:
        1. Parent offset frame transform (if exists)
        2. Joint spatial transform with default coordinate values
        3. Child offset frame transform (if exists)
        """
        # Start with identity
        transform = Matrix.Identity(4)
        
        # 1. Apply parent offset frame transformation
        if joint.parent_offset_frame:
            parent_offset_transform = joint.parent_offset_frame.get_transform_matrix()
            transform = transform @ parent_offset_transform
        
        # 2. Apply joint's spatial transformation with default coordinate values
        if joint.spatial_transform and joint.coordinates:
            joint_spatial_transform = self._get_joint_spatial_transform(joint)
            transform = transform @ joint_spatial_transform
        
        # 3. Apply child offset frame transformation (inverse)
        if joint.child_offset_frame:
            child_offset_transform = joint.child_offset_frame.get_transform_matrix()
            # Note: For joint chain, we typically want the inverse of child offset
            # but this depends on OpenSim convention. May need adjustment.
            transform = transform @ child_offset_transform.inverted()
        
        return transform

    def _get_joint_spatial_transform(self, joint):
        """Get the spatial transformation matrix for a joint using coordinate default values"""
        if not joint.spatial_transform or not joint.coordinates:
            return Matrix.Identity(4)
        
        # Build coordinate name to value mapping
        coord_values = {}
        for coord in joint.coordinates:
            coord_values[coord.name] = coord.default_value
        
        # Apply transformations based on spatial transform axes
        transform = Matrix.Identity(4)
        
        axes = joint.spatial_transform.get('axes', [])
        for axis_data in axes:
            axis_name = axis_data.get('name', '')
            coordinates = axis_data.get('coordinates', '')
            axis_vector = axis_data.get('axis', (1, 0, 0))
            
            # Find the coordinate value for this axis
            coord_value = coord_values.get(coordinates, 0.0)
            
            if coord_value == 0.0:
                continue  # No transformation needed
            
            # Create transformation based on axis type
            if 'rotation' in axis_name.lower() or any(coord.coordinate_type == 'rotational' 
                                                     for coord in joint.coordinates 
                                                     if coord.name == coordinates):
                # Rotational transformation
                axis_vec = Vector(axis_vector).normalized()
                rotation_matrix = Matrix.Rotation(coord_value, 4, axis_vec)
                transform = transform @ rotation_matrix
            else:
                # Translational transformation
                translation_vec = Vector(axis_vector) * coord_value
                translation_matrix = Matrix.Translation(translation_vec)
                transform = transform @ translation_matrix
        
        return transform

    def _get_coordinate_transform(self, coordinate):
        """Get the transformation matrix for a coordinate with its default value"""
        # This is a simplified version - the proper implementation is in _get_joint_spatial_transform
        if coordinate.coordinate_type == 'rotational':
            # Create rotation matrix based on default angle
            angle = coordinate.default_value
            # Assume rotation around Z-axis for now (this should use spatial transform info)
            return Matrix.Rotation(angle, 4, 'Z')
        elif coordinate.coordinate_type == 'translational':
            # Create translation matrix
            translation = coordinate.default_value
            # Assume translation along Z-axis for now (this should use spatial transform info)
            return Matrix.Translation(Vector((0, 0, translation)))
        
        return Matrix.Identity(4)

    def _setup_new_bone_hierarchy(self):
        """Setup parent-child relationships for the new bone structure"""
        edit_bones = self.armature_data.edit_bones
        
        print("Setting up bone hierarchy...")
        
        # Step 1: Setup JOINT bone hierarchy (JOINT bones connect to parent BODY bones)
        for joint in self.joint_objects:
            joint_bone_name = f"JOINT-{joint.name}"
            joint_bone = edit_bones.get(joint_bone_name)
            
            if not joint_bone:
                continue
            
            # Find parent body bone(s) - joints connect to body bones of the parent body
            parent_body_name = joint.parent_body
            
            if parent_body_name == "ground":
                # Root joint - no parent
                print(f"JOINT bone {joint_bone_name} is root (parent: {parent_body_name})")
                continue
            
            # Find any body bone of the parent body to use as parent
            parent_body_bone = None
            for bone_name in edit_bones.keys():
                if bone_name.startswith(f"BODY-{parent_body_name}-"):
                    parent_body_bone = edit_bones[bone_name]
                    break
            
            if parent_body_bone:
                joint_bone.parent = parent_body_bone
                print(f"Set hierarchy: {joint_bone_name}.parent = {parent_body_bone.name}")
            else:
                print(f"Warning: No parent body bone found for joint {joint_bone_name} "
                      f"(parent body: {parent_body_name})")
        
        # Step 2: Setup BODY bone hierarchy (BODY bones are children of their creating JOINT)
        for joint in self.joint_objects:
            joint_bone_name = f"JOINT-{joint.name}"
            joint_bone = edit_bones.get(joint_bone_name)
            
            if not joint_bone:
                continue
            
            child_body_name = joint.child_body
            
            # Find all body bones for this child body and set them as children of the joint
            for bone_name in edit_bones.keys():
                if bone_name.startswith(f"BODY-{child_body_name}-"):
                    body_bone = edit_bones[bone_name]
                    body_bone.parent = joint_bone
                    print(f"Set hierarchy: {body_bone.name}.parent = {joint_bone_name}")
        
        print("Bone hierarchy setup complete")

    def _apply_joint_transformations(self):
        """Apply coordinate transformations using joint spatial transforms"""
        print("Applying joint transformations using spatial transforms...")
        
        # Ensure we're in pose mode and have the right armature active
        bpy.context.view_layer.objects.active = self.armature_obj
        bpy.ops.object.mode_set(mode='POSE')
        
        for joint in self.joint_objects:
            print(f"  Processing joint: {joint.name}")
            if not joint.coordinates or not joint.spatial_transform:
                continue
            
            # Try to find corresponding bone by joint name instead of body name
            joint_bone_name = f"JOINT-{joint.name}"
            body_bone_name = f"BODY-{joint.child_body}-{joint.name}"
            
            # Try joint bone first, then body bone
            pose_bone = None
            for bone_name in [joint_bone_name, body_bone_name, joint.child_body]:
                if bone_name in self.armature_obj.pose.bones:
                    pose_bone = self.armature_obj.pose.bones[bone_name]
                    print(f"    Found pose bone: {bone_name}")
                    break
            
            if not pose_bone:
                print(f"    Warning: No pose bone found for joint {joint.name}")
                continue
            
            # Calculate coordinate default rotation safely
            try:
                coord_rotation = self._calculate_coordinate_default_rotation_for_joint(joint)
                print(f"    Applying coordinate rotation: {coord_rotation}")
                
                # Apply the rotation to the pose bone
                pose_bone.rotation_mode = 'QUATERNION'
                pose_bone.rotation_quaternion = coord_rotation
                
                print(f"Applied coordinate rotation to {pose_bone.name}: {[c.name for c in joint.coordinates]}")
            except Exception as e:
                print(f"    Error applying rotation to {pose_bone.name}: {e}")
                continue

    def _setup_animation_system(self):
        """Setup animation system for PinJoints and CustomJoints"""
        print("Setting up animation system...")
        
        # First, create the coordinates bone in edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        self._create_coordinates_bone()
        
        # Switch back to pose mode and add custom properties and drivers
        bpy.ops.object.mode_set(mode='POSE')
        self._add_pin_joint_custom_properties()
        self._add_pin_joint_drivers()
        
        # Add CustomJoint support
        self._add_custom_joint_custom_properties()
        self._add_custom_joint_drivers()
    
    def _create_coordinates_bone(self):
        """Create a special bone to hold coordinate custom properties"""
        print("Creating coordinates bone...")
        
        # Create the coordinates bone
        coords_bone = self.armature_data.edit_bones.new("COORDINATES")
        
        # Position it at the origin, small size
        coords_bone.head = Vector((0, 0, 0))
        coords_bone.tail = Vector((0, 0, 0.1))
        
        # Make it independent (no parent)
        coords_bone.parent = None
        
        print("Created COORDINATES bone")
    
    def _add_pin_joint_custom_properties(self):
        """Add custom properties for each PinJoint coordinate"""
        print("Adding custom properties for PinJoint coordinates...")
        
        # Ensure we have the right armature active
        bpy.context.view_layer.objects.active = self.armature_obj
        
        # Get the COORDINATES pose bone
        coords_pose_bone = self.armature_obj.pose.bones.get("COORDINATES")
        if not coords_pose_bone:
            print("Error: COORDINATES bone not found in pose mode")
            return
        
        pin_joint_count = 0
        
        for joint in self.joint_objects:
            if joint.joint_type.lower() != 'pinjoint':
                continue
            
            pin_joint_count += 1
            print(f"  Processing PinJoint: {joint.name}")
            
            # PinJoints should have exactly one rotational coordinate
            rotational_coords = [c for c in joint.coordinates if c.coordinate_type == 'rotational']
            
            if not rotational_coords:
                print(f"    Warning: PinJoint {joint.name} has no rotational coordinates")
                continue
            
            coord = rotational_coords[0]  # Take the first (should be only) rotational coordinate
            
            # Create custom property name
            prop_name = f"{joint.name}_{coord.name}"
            
            # Set the property with default value and range
            coords_pose_bone[prop_name] = coord.default_value
            
            # Set property UI range and description
            if hasattr(coords_pose_bone, 'id_properties_ui'):
                ui = coords_pose_bone.id_properties_ui(prop_name)
                ui.update(
                    min=coord.range_min,
                    max=coord.range_max,
                    description=f"Rotation angle for {joint.name} ({coord.name})"
                )
            
            print(f"    Added property: {prop_name} = {coord.default_value:.3f} "
                  f"(range: [{coord.range_min:.1f}, {coord.range_max:.1f}])")
        
        print(f"Added custom properties for {pin_joint_count} PinJoints")
    
    def _add_pin_joint_drivers(self):
        """Add drivers to PinJoint bones that read from custom properties"""
        print("Adding drivers for PinJoint coordinates...")
        
        # Ensure we have the right armature active
        bpy.context.view_layer.objects.active = self.armature_obj
        
        pin_joint_count = 0
        
        for joint in self.joint_objects:
            if joint.joint_type.lower() != 'pinjoint':
                continue
            
            pin_joint_count += 1
            
            # Find the joint bone
            joint_bone_name = f"JOINT-{joint.name}"
            joint_pose_bone = self.armature_obj.pose.bones.get(joint_bone_name)
            
            if not joint_pose_bone:
                print(f"    Warning: Joint bone {joint_bone_name} not found")
                continue
            
            print(f"  Adding driver for PinJoint: {joint.name}")
            
            # Get the rotational coordinate
            rotational_coords = [c for c in joint.coordinates if c.coordinate_type == 'rotational']
            if not rotational_coords:
                continue
            
            coord = rotational_coords[0]
            prop_name = f"{joint.name}_{coord.name}"
            
            # Set rotation mode to XYZ Euler for easier driver setup
            joint_pose_bone.rotation_mode = 'XYZ'
            
            # Add driver to X rotation (PinJoint rotates around X axis)
            driver = joint_pose_bone.driver_add("rotation_euler", 0)  # 0 = X axis
            
            # Set driver type to scripted expression
            driver.driver.type = 'SCRIPTED'
            
            # Add variable for the custom property
            var = driver.driver.variables.new()
            var.name = "prop_value"
            var.type = 'SINGLE_PROP'
            
            # Set the variable to read from the COORDINATES bone custom property
            target = var.targets[0]
            target.id = self.armature_obj
            target.data_path = f'pose.bones["COORDINATES"]["{prop_name}"]'
            
            # Set the driver expression (subtract default value since it's baked into rest pose)
            default_value = coord.default_value
            driver.driver.expression = f"prop_value - ({default_value})"
            
            print(f"    Added X rotation driver: {prop_name} - {default_value:.3f}")
        
        print(f"Added drivers for {pin_joint_count} PinJoints")

    def _add_custom_joint_custom_properties(self):
        """Add custom properties for each CustomJoint coordinate"""
        print("Adding custom properties for CustomJoint coordinates...")
        
        # Ensure we have the right armature active
        bpy.context.view_layer.objects.active = self.armature_obj
        
        # Get the COORDINATES pose bone
        coords_pose_bone = self.armature_obj.pose.bones.get("COORDINATES")
        if not coords_pose_bone:
            print("Error: COORDINATES bone not found in pose mode")
            return
        
        custom_joint_count = 0
        
        for joint in self.joint_objects:
            if joint.joint_type.lower() != 'customjoint':
                continue
            
            if not joint.spatial_transform or not joint.coordinates:
                continue
            
            custom_joint_count += 1
            print(f"  Processing CustomJoint: {joint.name}")
            
            # Process each coordinate
            for coord in joint.coordinates:
                # Create custom property name
                prop_name = f"{joint.name}_{coord.name}"
                
                # Set the property with default value and range
                coords_pose_bone[prop_name] = coord.default_value
                
                # Set property UI range and description
                if hasattr(coords_pose_bone, 'id_properties_ui'):
                    ui = coords_pose_bone.id_properties_ui(prop_name)
                    ui.update(
                        min=coord.range_min,
                        max=coord.range_max,
                        description=f"Coordinate {coord.name} for CustomJoint {joint.name}"
                    )
                
                print(f"    Added property: {prop_name} = {coord.default_value:.3f} "
                      f"(range: [{coord.range_min:.1f}, {coord.range_max:.1f}])")
        
        print(f"Added custom properties for {custom_joint_count} CustomJoints")

    def _add_custom_joint_drivers(self):
        """Add drivers to CustomJoint bones based on SpatialTransform"""
        print("Adding drivers for CustomJoint coordinates...")
        
        # Ensure we have the right armature active
        bpy.context.view_layer.objects.active = self.armature_obj
        
        custom_joint_count = 0
        
        for joint in self.joint_objects:
            if joint.joint_type.lower() != 'customjoint':
                continue
            
            if not joint.spatial_transform or not joint.coordinates:
                continue
            
            custom_joint_count += 1
            
            # Find the joint bone
            joint_bone_name = f"JOINT-{joint.name}"
            joint_pose_bone = self.armature_obj.pose.bones.get(joint_bone_name)
            
            if not joint_pose_bone:
                print(f"    Warning: Joint bone {joint_bone_name} not found")
                continue
            
            print(f"  Adding drivers for CustomJoint: {joint.name}")
            
            # Set rotation mode to XYZ Euler for easier driver setup
            joint_pose_bone.rotation_mode = 'XYZ'
            
            # Process each transform axis
            axes = joint.spatial_transform.get('axes', [])
            for axis_data in axes:
                axis_name = axis_data.get('name', '')
                coordinate_name = axis_data.get('coordinates', '')
                axis_vector = axis_data.get('axis', (0, 0, 0))
                function_data = axis_data.get('function', {'type': 'none'})
                
                # Skip axes with no coordinate (constant transforms)
                if not coordinate_name:
                    print(f"    Skipping {axis_name} - no coordinate")
                    continue
                
                # Find corresponding coordinate object for default value
                coord = None
                for c in joint.coordinates:
                    if c.name == coordinate_name:
                        coord = c
                        break
                
                if not coord:
                    print(f"    Warning: Coordinate {coordinate_name} not found")
                    continue
                
                # Determine which rotation/translation axis to drive
                driver_info = self._get_driver_info_for_axis(axis_name, axis_vector)
                if not driver_info:
                    print(f"    Skipping {axis_name} - unsupported axis type")
                    continue
                
                property_name = f"{joint.name}_{coordinate_name}"
                
                # Add the driver
                try:
                    self._add_spatial_transform_driver(
                        joint_pose_bone, 
                        driver_info, 
                        property_name, 
                        function_data, 
                        coord.default_value
                    )
                    print(f"    Added driver for {axis_name}: {property_name}")
                except Exception as e:
                    print(f"    Error adding driver for {axis_name}: {e}")
        
        print(f"Added drivers for {custom_joint_count} CustomJoints")

    def _get_driver_info_for_axis(self, axis_name: str, axis_vector: tuple) -> dict | None:
        """Determine which bone property to drive based on axis name and vector"""
        # Convert axis vector to determine the dominant direction
        x, y, z = axis_vector
        
        if 'rotation' in axis_name.lower():
            # For rotations, map to rotation_euler axes
            # OpenSim uses different conventions, so we need to map carefully
            if abs(x) > abs(y) and abs(x) > abs(z):
                return {'property': 'rotation_euler', 'index': 0, 'type': 'rotation'}  # X rotation
            elif abs(y) > abs(z):
                return {'property': 'rotation_euler', 'index': 1, 'type': 'rotation'}  # Y rotation  
            else:
                return {'property': 'rotation_euler', 'index': 2, 'type': 'rotation'}  # Z rotation
        
        elif 'translation' in axis_name.lower():
            # For translations, map to location axes
            if abs(x) > abs(y) and abs(x) > abs(z):
                return {'property': 'location', 'index': 0, 'type': 'translation'}  # X translation
            elif abs(y) > abs(z):
                return {'property': 'location', 'index': 1, 'type': 'translation'}  # Y translation
            else:
                return {'property': 'location', 'index': 2, 'type': 'translation'}  # Z translation
        
        return None

    def _add_spatial_transform_driver(self, pose_bone, driver_info: dict, property_name: str, function_data: dict, default_value: float):
        """Add a driver for a specific spatial transform axis"""
        property_path = driver_info['property']
        index = driver_info['index']
        
        # Add driver to the specific property
        driver = pose_bone.driver_add(property_path, index)
        
        # Set driver type to scripted expression
        driver.driver.type = 'SCRIPTED'
        
        # Add variable for the custom property
        var = driver.driver.variables.new()
        var.name = "coord_value"
        var.type = 'SINGLE_PROP'
        
        # Set the variable to read from the COORDINATES bone custom property
        target = var.targets[0]
        target.id = self.armature_obj
        target.data_path = f'pose.bones["COORDINATES"]["{property_name}"]'
        
        # Create driver expression based on function type
        expression = self._create_driver_expression(function_data, default_value)
        driver.driver.expression = expression
        
        print(f"      Driver expression: {expression}")

    def _create_driver_expression(self, function_data: dict, default_value: float) -> str:
        """Create driver expression based on transform function type"""
        function_type = function_data.get('type', 'none')
        
        if function_type == 'linear':
            # LinearFunction: output = coeff1 * input + coeff2
            coeffs = function_data.get('coefficients', [1, 0])
            coeff1 = coeffs[0] if len(coeffs) > 0 else 1
            coeff2 = coeffs[1] if len(coeffs) > 1 else 0
            
            # Subtract default value since it's baked into rest pose
            return f"({coeff1}) * (coord_value - ({default_value})) + ({coeff2})"
        
        elif function_type == 'multiplier':
            # MultiplierFunction: output = scale * constant_value
            # Since coordinates is empty for these, they're typically constant
            scale = function_data.get('scale', 1.0)
            constant = function_data.get('constant_value', 0.0)
            return f"{scale * constant}"
        
        elif function_type == 'spline':
            # SimmSpline: For now, use linear interpolation approximation
            # TODO: Implement proper spline using keyframes
            x_values = function_data.get('x_values', [])
            y_values = function_data.get('y_values', [])
            
            if len(x_values) >= 2 and len(y_values) >= 2:
                # Simple linear approximation between first and last points
                x1, x2 = x_values[0], x_values[-1]
                y1, y2 = y_values[0], y_values[-1]
                
                if x2 != x1:
                    slope = (y2 - y1) / (x2 - x1)
                    intercept = y1 - slope * x1
                    # Subtract default value since it's baked into rest pose
                    return f"({slope}) * (coord_value - ({default_value})) + ({intercept})"
            
            # Fallback to simple linear
            return f"coord_value - ({default_value})"
        
        else:
            # Default: simple 1:1 mapping
            return f"coord_value - ({default_value})"


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
# print_body_joint_hierarchy(converter)

print(f"Created armature: {armature.name}")
print(f"Total bones: {len(armature.data.bones)}")
 