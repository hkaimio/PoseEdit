#!/usr/bin/env python3
"""
OpenSim Skeleton Analyzer

This script analyzes OpenSim model files (.osim) and extracts the joint hierarchy,
including joint coordinates, offset frames, and generalized coordinates.

Author: AI Assistant
Date: October 2025
"""

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

@dataclass
class Joint:
    """Represents an OpenSim joint with all its properties"""
    name: str
    joint_type: str  # CustomJoint, PinJoint, WeldJoint, etc.
    parent_frame: str
    child_frame: str
    parent_body: str
    child_body: str
    coordinates: List[Coordinate]
    parent_offset_frame: Optional[OffsetFrame]
    child_offset_frame: Optional[OffsetFrame]
    
    # For CustomJoint, store the spatial transform details
    spatial_transform: Optional[Dict[str, Any]] = None

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
    
    def _parse_joint(self, joint_elem) -> Joint | None:
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
    
    def _extract_offset_frames(self, joint_elem) -> tuple[OffsetFrame | None, OffsetFrame | None]:
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

def main():
    parser = argparse.ArgumentParser(description='Analyze OpenSim model skeleton structure')
    parser.add_argument('osim_file', help='Path to the .osim model file')
    parser.add_argument('--output', '-o', help='Output YAML file (optional)')
    parser.add_argument('--detailed', '-d', action='store_true', help='Print detailed joint information')
    parser.add_argument('--hierarchy-only', action='store_true', help='Print only the hierarchy tree')
    
    args = parser.parse_args()
    
    try:
        # Analyze the model
        analyzer = OpenSimSkeletonAnalyzer(args.osim_file)
        results = analyzer.analyze()
        
        # Print model info
        model_info = results.get("model_info", {})
        print(f"=== MODEL: {model_info.get('name', 'Unknown')} ===")
        print(f"Units: {model_info.get('length_units', 'unknown')} (length), {model_info.get('force_units', 'unknown')} (force)")
        gravity = model_info.get('gravity', (0, 0, 0))
        print(f"Gravity: [{gravity[0]:.2f}, {gravity[1]:.2f}, {gravity[2]:.2f}] m/s²")
        
        if not args.hierarchy_only:
            print_coordinate_summary(results)
        
        print_joint_hierarchy(results)
        
        if args.detailed and not args.hierarchy_only:
            print_detailed_joint_info(results)
        
        # Save to YAML if requested
        if args.output:
            with open(args.output, 'w') as f:
                yaml.dump(results, f, default_flow_style=False, sort_keys=False)
            print(f"\nResults saved to: {args.output}")
    
    except Exception as e:
        print(f"Error analyzing model: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()