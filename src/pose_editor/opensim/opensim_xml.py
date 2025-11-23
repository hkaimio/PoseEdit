"""
OpenSim XML generation utilities.

This module provides functions to create OpenSim XML elements for bodies, joints,
and markers based on configuration.
"""

import xml.etree.ElementTree as ET

from .config import BoneConfig, JointConstraints, JointType


def create_opensim_document(model_name: str) -> ET.Element:
    """
    Create base OpenSim document structure.

    Args:
        model_name: Name for the OpenSim model

    Returns:
        Root XML element
    """
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
    ET.SubElement(bodyset, "objects")
    ET.SubElement(bodyset, "groups")

    # JointSet
    jointset = ET.SubElement(model, "JointSet", name="jointset")
    ET.SubElement(jointset, "objects")
    ET.SubElement(jointset, "groups")

    # ControllerSet
    controller_set = ET.SubElement(model, "ControllerSet", name="controllerset")
    ET.SubElement(controller_set, "objects")
    ET.SubElement(controller_set, "groups")

    # ForceSet
    force_set = ET.SubElement(model, "ForceSet", name="forceset")
    ET.SubElement(force_set, "objects")
    ET.SubElement(force_set, "groups")

    # MarkerSet
    marker_set = ET.SubElement(model, "MarkerSet", name="markers")
    ET.SubElement(marker_set, "objects")
    ET.SubElement(marker_set, "groups")

    return doc


def get_bone_radius(bone_name: str) -> float:
    """
    Calculate bone radius for visualization based on bone name.

    Args:
        bone_name: Name of the bone

    Returns:
        Radius for the bone cylinder visualization
    """
    bone_name_lower = bone_name.lower()

    # Small radius for finger bones, thumb bones, and palm bones
    if bone_name_lower.startswith("f_") or bone_name_lower.startswith("thumb") or bone_name_lower.startswith("palm"):
        return 0.005

    # Default radius for other bones
    return 0.02


def create_opensim_body(name: str, bone_length: float, mass: float, inertia: tuple[float, ...]) -> ET.Element:
    """
    Create OpenSim Body XML element.

    Args:
        name: Body name
        bone_length: Length of bone for visualization
        mass: Body mass in kg
        inertia: Inertia tensor (Ixx, Iyy, Izz, Ixy, Ixz, Iyz)

    Returns:
        Body XML element
    """
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

    # Body properties
    ET.SubElement(body, "mass").text = str(mass)
    ET.SubElement(body, "mass_center").text = "0 0 0"
    inertia_str = " ".join(str(val) for val in inertia)
    ET.SubElement(body, "inertia").text = inertia_str

    return body


def create_opensim_free_joint(
    name: str,
    parent_body: str,
    child_body: str,
    parent_pos: tuple[float, float, float],
    parent_rot: tuple[float, float, float],
    child_pos: tuple[float, float, float],
    child_rot: tuple[float, float, float],
) -> ET.Element:
    """
    Create OpenSim FreeJoint XML element for root bone.

    Args:
        name: Joint name
        parent_body: Parent body name
        child_body: Child body name
        parent_pos: Parent frame position (x, y, z)
        parent_rot: Parent frame rotation (rx, ry, rz) in radians
        child_pos: Child frame position (x, y, z)
        child_rot: Child frame rotation (rx, ry, rz) in radians

    Returns:
        FreeJoint XML element
    """
    joint = ET.Element("FreeJoint", name=name)

    # Socket connections
    ET.SubElement(joint, "socket_parent_frame").text = f"{name}_parent_offset"
    ET.SubElement(joint, "socket_child_frame").text = f"{name}_child_offset"

    # Coordinates (6 DOF for free joint) - minimal format like OpenSim default
    coordinates = ET.SubElement(joint, "coordinates")
    for i in range(6):
        ET.SubElement(coordinates, "Coordinate", name=f"coord_{i}")

    # Physical offset frames
    frames = ET.SubElement(joint, "frames")

    # Parent frame
    parent_frame = ET.SubElement(frames, "PhysicalOffsetFrame", name=f"{name}_parent_offset")
    parent_geom = ET.SubElement(parent_frame, "FrameGeometry", name="frame_geometry")
    ET.SubElement(parent_geom, "socket_frame").text = ".."
    parent_scale = ET.SubElement(parent_geom, "scale_factors")
    parent_scale.text = "0.20000000000000001 0.20000000000000001 0.20000000000000001"
    parent_socket = "/bodyset/" + parent_body if parent_body != "ground" else "/ground"
    ET.SubElement(parent_frame, "socket_parent").text = parent_socket
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


def create_opensim_weld_joint(
    name: str,
    parent_body: str,
    child_body: str,
    parent_pos: tuple[float, float, float],
    parent_rot: tuple[float, float, float],
    child_pos: tuple[float, float, float],
    child_rot: tuple[float, float, float],
) -> ET.Element:
    """
    Create OpenSim WeldJoint XML element for fully constrained (0-DOF) joints.

    Args:
        name: Joint name
        parent_body: Parent body name
        child_body: Child body name
        parent_pos: Parent frame position (x, y, z)
        parent_rot: Parent frame rotation (rx, ry, rz) in radians
        child_pos: Child frame position (x, y, z)
        child_rot: Child frame rotation (rx, ry, rz) in radians

    Returns:
        WeldJoint XML element
    """
    joint = ET.Element("WeldJoint", name=name)

    # Socket connections
    ET.SubElement(joint, "socket_parent_frame").text = f"{name}_parent_offset"
    ET.SubElement(joint, "socket_child_frame").text = f"{name}_child_offset"

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

    return joint


def create_opensim_custom_joint_from_config(
    name: str,
    parent_body: str,
    child_body: str,
    parent_pos: tuple[float, float, float],
    parent_rot: tuple[float, float, float],
    child_pos: tuple[float, float, float],
    child_rot: tuple[float, float, float],
    constraints: JointConstraints,
) -> ET.Element:
    """
    Create CustomJoint from configuration.

    Args:
        name: Joint name
        parent_body: Parent body name
        child_body: Child body name
        parent_pos: Parent frame position (x, y, z)
        parent_rot: Parent frame rotation (rx, ry, rz) in radians
        child_pos: Child frame position (x, y, z)
        child_rot: Child frame rotation (rx, ry, rz) in radians
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
        ("rot_z", constraints.z_axis, "0 0 1"),
    ]

    for coord_name, axis_constraint, axis_vec in axes:
        if axis_constraint and not axis_constraint.locked:
            min_val, max_val = axis_constraint.to_radians()
            coord_info.append(
                {"name": coord_name, "axis_vec": axis_vec, "min_val": min_val, "max_val": max_val, "is_locked": False}
            )

    # Create coordinates
    coordinates = ET.SubElement(joint, "coordinates")
    for info in coord_info:
        coord = ET.SubElement(coordinates, "Coordinate", name=f"{name}_coord_{info['name']}")

        # Always set default_value to 0
        ET.SubElement(coord, "default_value").text = "0"
        ET.SubElement(coord, "default_speed_value").text = "0"

        # Ensure the range includes 0. If it doesn't, extend min or max and warn.
        min_val = float(info['min_val'])
        max_val = float(info['max_val'])
        orig_min = min_val
        orig_max = max_val
        adjusted = False
        if min_val > 0.0:
            min_val = 0.0
            adjusted = True
        if max_val < 0.0:
            max_val = 0.0
            adjusted = True

        if adjusted:
            print(
                f"Warning: joint '{name}' coordinate '{info['name']}' range "
                f"[{orig_min:.10f}, {orig_max:.10f}] does not include 0 — extending to "
                f"[{min_val:.10f}, {max_val:.10f}] to allow default 0."
            )

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

    # SpatialTransform - configure based on constraints
    spatial_transform = ET.SubElement(joint, "SpatialTransform")

    # Rotational axes - map to coordinate info
    rotation_mapping = [
        ("rotation1", "rot_x", "1 0 0"),
        ("rotation2", "rot_z", "0 0 1"),
        ("rotation3", "rot_y", "0 1 0"),
    ]

    for axis_name, coord_type, axis_vec in rotation_mapping:
        transform_axis = ET.SubElement(spatial_transform, "TransformAxis", name=axis_name)
        # Find the corresponding coordinate info
        coord_info_item = next((info for info in coord_info if info["name"] == coord_type), None)

        if coord_info_item and not coord_info_item.get("is_locked", False):
            # Active rotational axis -> map to coordinate and use a LinearFunction
            ET.SubElement(transform_axis, "coordinates").text = f"{name}_coord_{coord_type}"
            ET.SubElement(transform_axis, "axis").text = axis_vec
            linear_func = ET.SubElement(transform_axis, "LinearFunction", name="function")
            # Coefficients map coordinate value to transform: value * 1 + 0
            ET.SubElement(linear_func, "coefficients").text = "1 0"
        else:
            # Locked axis -> no coordinate mapping, use constant zero
            ET.SubElement(transform_axis, "coordinates").text = ""
            ET.SubElement(transform_axis, "axis").text = axis_vec
            constant_func = ET.SubElement(transform_axis, "Constant", name="function")
            ET.SubElement(constant_func, "value").text = "0"

    # Translational axes (all locked)
    for i, axis_vec in enumerate(["1 0 0", "0 1 0", "0 0 1"], 1):
        transform_axis = ET.SubElement(spatial_transform, "TransformAxis", name=f"translation{i}")
        ET.SubElement(transform_axis, "coordinates").text = ""
        ET.SubElement(transform_axis, "axis").text = axis_vec
        constant_func = ET.SubElement(transform_axis, "Constant", name="function")
        ET.SubElement(constant_func, "value").text = "0"

    return joint


def create_joint_from_config(
    bone_config: BoneConfig,
    parent_body_name: str,
    parent_pos: tuple[float, float, float],
    parent_rot: tuple[float, float, float],
    child_pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
    child_rot: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> ET.Element:
    """
    Create OpenSim joint element based on configuration.

    Args:
        bone_config: Bone configuration
        parent_body_name: Name of parent body
        parent_pos: Parent frame position
        parent_rot: Parent frame rotation in radians
        child_pos: Child frame position
        child_rot: Child frame rotation in radians

    Returns:
        Joint XML element (FreeJoint, WeldJoint, or CustomJoint)
    """
    constraints = bone_config.constraints
    joint_name = f"{bone_config.opensim_name}_joint"

    if constraints.joint_type == JointType.FREE:
        return create_opensim_free_joint(
            joint_name, parent_body_name, bone_config.opensim_name, parent_pos, parent_rot, child_pos, child_rot
        )
    else:  # CUSTOM joint
        # Check if joint has any degrees of freedom
        has_dof = False
        for axis_constraint in [constraints.x_axis, constraints.y_axis, constraints.z_axis]:
            if axis_constraint and not axis_constraint.locked:
                has_dof = True
                break

        if not has_dof:
            # Use WeldJoint for 0-DOF (fully constrained) joints
            return create_opensim_weld_joint(
                joint_name, parent_body_name, bone_config.opensim_name, parent_pos, parent_rot, child_pos, child_rot
            )
        else:
            # Use CustomJoint for 1-3 DOF joints
            return create_opensim_custom_joint_from_config(
            joint_name,
            parent_body_name,
            bone_config.opensim_name,
            parent_pos,
            parent_rot,
            child_pos,
            child_rot,
            constraints,
        )


def create_opensim_marker(
    marker_name: str, parent_body_name: str, local_position: tuple[float, float, float]
) -> ET.Element:
    """
    Create OpenSim Marker XML element.

    Args:
        marker_name: Marker name
        parent_body_name: Parent body name ("ground" for ground-attached markers)
        local_position: Position in parent body's local coordinates (x, y, z)

    Returns:
        Marker XML element
    """
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


def write_opensim_file(doc: ET.Element, output_file: str):
    """
    Write OpenSim XML document to file.

    Args:
        doc: OpenSim document root element
        output_file: Output file path
    """
    tree = ET.ElementTree(doc)
    ET.indent(tree, space="  ", level=0)

    with open(output_file, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)
