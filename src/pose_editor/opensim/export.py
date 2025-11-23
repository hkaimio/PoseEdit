"""
Main export functions for Blender armature to OpenSim model conversion.

This module provides the high-level orchestration functions that tie together
the configuration, hierarchy building, and XML generation to produce complete
OpenSim .osim files.
"""

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import bpy
from mathutils import Matrix

from .config import ArmatureExportConfig
from .hierarchy import BoneHierarchyNode, build_export_hierarchy
from .opensim_xml import (
    create_joint_from_config,
    create_opensim_body,
    create_opensim_document,
    create_opensim_marker,
    write_opensim_file,
)


def get_armature(armature_name: str) -> bpy.types.Object:
    """
    Get armature object by name.

    Args:
        armature_name: Name of armature object

    Returns:
        Armature object

    Raises:
        ValueError: If armature not found
    """
    if armature_name not in bpy.data.objects:
        raise ValueError(f"Armature '{armature_name}' not found")

    armature_obj = bpy.data.objects[armature_name]
    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object '{armature_name}' is not an armature")

    return armature_obj


def blender_to_opensim_transform(matrix: Matrix) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """
    Convert Blender transform matrix to OpenSim coordinate system.

    Blender uses Z-up, right-handed coordinates.
    OpenSim uses Y-up, right-handed coordinates.

    The transformation is: apply a -90° rotation around X-axis.
    This maps: Blender (X, Y, Z) -> OpenSim (X, Z, -Y)

    Args:
        matrix: Blender 4x4 transform matrix

    Returns:
        Tuple of (position, rotation_euler) in OpenSim coordinates
        - position: (x, y, z) in meters
        - rotation_euler: (rx, ry, rz) in radians (XYZ order)
    """
    # Coordinate system change: rotation of -90 degrees around X-axis
    # R_change = [1  0   0]
    #            [0  0   1]
    #            [0 -1   0]
    R_change = Matrix.Rotation(math.radians(-90), 4, 'X')

    # Apply coordinate change: T_opensim = R_change @ T_blender @ R_change^-1
    # For position this simplifies to: R_change @ position
    # For rotation: we transform the rotation matrix through the coordinate change
    transformed_matrix = R_change @ matrix @ R_change.inverted()

    # Extract position (already in OpenSim coords after transformation)
    position = transformed_matrix.translation
    position = (position.x, position.y, position.z)

    # Extract rotation as Euler angles (XYZ order) from the transformed matrix
    euler = transformed_matrix.to_euler('XYZ')
    rotation = (euler.x, euler.y, euler.z)

    return position, rotation


def get_bone_opensim_transform(
    pose_bone: bpy.types.PoseBone,
    parent_pose_bone: bpy.types.PoseBone | None,
) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
    """
    Get bone transform in OpenSim coordinate system relative to parent.

    This follows the same logic as the legacy exporter in opensim_export.py:
    - Root bone: Apply Z-up to Y-up rotation (-90° around X-axis) to bone matrix
    - Child bones: Compute local transform directly (NO coordinate conversion)
    - Use ZYX Euler order for rotation extraction

    Args:
        pose_bone: Blender pose bone
        parent_pose_bone: Parent pose bone (or None for root)

    Returns:
        Tuple of (position, rotation, length)
        - position: Local position (meters)
        - rotation: Local rotation (radians, ZYX Euler)
        - length: Bone length in meters
    """
    # Get bone matrix
    bone_matrix = pose_bone.matrix.copy()

    # Get parent matrix and apply coordinate conversion for root only
    if parent_pose_bone:
        # Child bone: use parent matrix as-is
        parent_matrix = parent_pose_bone.matrix
    else:
        # Root bone: apply Z-up to Y-up conversion
        parent_matrix = Matrix.Identity(4)
        rot_y_up_mat = Matrix.Rotation(math.radians(-90), 4, 'X')
        bone_matrix = rot_y_up_mat @ bone_matrix

    # Compute local transform
    local_matrix = parent_matrix.inverted() @ bone_matrix

    # Extract position and rotation
    position = local_matrix.translation
    position = (position.x, position.y, position.z)

    # Use ZYX Euler order (same as legacy exporter)
    euler = local_matrix.to_euler('ZYX')
    rotation = (euler.x, euler.y, euler.z)

    # Calculate bone length
    bone_length = pose_bone.bone.length

    if ("clavicle" in pose_bone.name.lower()) or ("foot" in pose_bone.name.lower()):
        print("Clavicle or foot detected:", pose_bone.name)
        print(f"  name: {pose_bone.name}")
        print(f"  global matrix:\n{bone_matrix}")
        print(f"     gobal postion: {bone_matrix.translation}")
        print(f"     global rotation (XYZ): {bone_matrix.to_euler('XYZ')}")
        print(f"  parent matrix:\n{parent_matrix}")
        print(f"     parent global position: {parent_matrix.translation}")
        print(f"     parent global rotation (XYZ): {parent_matrix.to_euler('XYZ')}")
        print(f"  local matrix:\n{local_matrix}")
        print(f"  local translation: {position}")
        print(f"  local rotation (ZYX): {rotation}")

    return position, rotation, bone_length


def export_bodies_and_joints(
    doc: ET.Element,
    hierarchy: BoneHierarchyNode,
    config: ArmatureExportConfig,
) -> None:
    """
    Export bodies and joints from hierarchy tree to OpenSim document.

    Recursively walks the hierarchy and creates Body and Joint XML elements.

    Args:
        doc: OpenSim XML document root
        hierarchy: Root of bone hierarchy tree
        config: Export configuration
    """
    model = doc.find("Model")
    bodyset_objects = model.find(".//BodySet/objects")
    jointset_objects = model.find(".//JointSet/objects")

    def export_node(node: BoneHierarchyNode, parent_body_name: str = "ground") -> None:
        """Recursively export node and children."""
        bone = node.blender_bone
        bone_config = node.bone_config

        # Get bone transform in OpenSim coordinate system
        parent_bone = node.parent.blender_bone if node.parent else None
        position, rotation, length = get_bone_opensim_transform(bone, parent_bone)

        # Create body
        if bone_config.export_body:
            body = create_opensim_body(
                bone_config.opensim_name,
                length,
                bone_config.body_mass,
                bone_config.body_inertia,
            )
            bodyset_objects.append(body)

        # Create joint
        # Use default child offsets (0, 0, 0) for both position and rotation
        joint = create_joint_from_config(
            bone_config,
            parent_body_name,
            position,
            rotation,
        )
        jointset_objects.append(joint)

        # Process children
        for child_node in node.children:
            export_node(child_node, bone_config.opensim_name)

    # Start export from root
    export_node(hierarchy)


def find_marker_parent_body(
    marker_bone: bpy.types.PoseBone,
    config: ArmatureExportConfig,
) -> tuple[bpy.types.PoseBone | None, str]:
    """
    Find the parent body for a marker bone.

    Walks up the bone hierarchy to find the first exported bone.

    Args:
        marker_bone: Marker pose bone
        config: Export configuration

    Returns:
        Tuple of (parent_pose_bone, parent_body_name)
        If no exported parent found, returns (None, "ground")
    """
    current = marker_bone.parent
    while current:
        if config.is_exported(current.name):
            bone_config = config.get_bone_config(current.name)
            return current, bone_config.opensim_name
        current = current.parent

    # No exported parent found, attach to ground
    return None, "ground"


def get_marker_local_position(
    marker_bone: bpy.types.PoseBone,
    parent_bone: bpy.types.PoseBone | None,
) -> tuple[float, float, float]:
    """
    Get marker position in parent body's local coordinate system.

    This follows the same logic as the legacy exporter:
    - Compute local position relative to parent (or world if no parent)
    - NO coordinate conversion (position stays as-is)

    Args:
        marker_bone: Marker pose bone
        parent_bone: Parent body pose bone (or None for ground)

    Returns:
        Local position (x, y, z) in meters
    """
    if parent_bone:
        # Calculate position relative to parent body
        local_matrix = parent_bone.matrix.inverted() @ marker_bone.matrix
        position = local_matrix.translation
    else:
        # No parent body, use global position
        position = marker_bone.matrix.translation

    return (position.x, position.y, position.z)


def export_markers(
    doc: ET.Element,
    armature_obj: bpy.types.Object,
    config: ArmatureExportConfig,
) -> None:
    """
    Export markers from bone collection to OpenSim document.

    Args:
        doc: OpenSim XML document root
        armature_obj: Blender armature object
        config: Export configuration
    """
    marker_set = doc.find(".//MarkerSet/objects")

    # Store current mode
    current_mode = bpy.context.mode
    current_object = bpy.context.active_object

    # Set the armature as active object
    bpy.context.view_layer.objects.active = armature_obj

    if current_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    try:
        # Check if the marker collection exists
        collection_name = config.marker_collection_name
        if collection_name not in armature_obj.data.collections:
            print(f"Warning: Bone collection '{collection_name}' not found. No markers exported.")
            return

        collection = armature_obj.data.collections[collection_name]

        # Process each bone in the collection
        for bone in collection.bones:
            if bone.name not in armature_obj.pose.bones:
                continue

            marker_bone = armature_obj.pose.bones[bone.name]

            # Find parent body for this marker
            parent_bone, parent_body_name = find_marker_parent_body(marker_bone, config)

            # Get marker position in parent body's local coordinates
            local_position = get_marker_local_position(marker_bone, parent_bone)

            # Get marker name (apply overrides from config)
            marker_name = config.marker_config.get_marker_name(bone.name)

            # Create marker XML element
            marker_xml = create_opensim_marker(marker_name, parent_body_name, local_position)
            marker_set.append(marker_xml)

            print(f"Created marker '{marker_name}' on body '{parent_body_name}' at {local_position}")

    finally:
        # Restore original active object and mode
        if current_object:
            bpy.context.view_layer.objects.active = current_object

        if current_mode == 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        elif current_mode == 'POSE':
            bpy.ops.object.mode_set(mode='POSE')


def export_armature_to_opensim_with_config(
    armature_name: str,
    config: ArmatureExportConfig,
    output_file: str,
) -> None:
    """
    Export Blender armature to OpenSim model using configuration.

    This is the main entry point for the new configuration-based export system.

    Args:
        armature_name: Name of Blender armature object
        config: Export configuration defining bones, joints, and markers
        output_file: Output .osim file path

    Raises:
        ValueError: If armature not found or configuration invalid

    Example:
        >>> from pose_editor.opensim.configs.humanoid import create_humanoid_config
        >>> config = create_humanoid_config()
        >>> export_armature_to_opensim_with_config(
        ...     "Armature",
        ...     config,
        ...     "output/humanoid.osim"
        ... )
    """
    # Validate configuration
    config.validate()

    # Get armature
    armature_obj = get_armature(armature_name)

    # Build hierarchy from Blender armature using configuration
    print(f"Building export hierarchy for armature '{armature_name}'...")
    hierarchy = build_export_hierarchy(armature_obj, config)

    # Create OpenSim document
    print(f"Creating OpenSim document '{config.model_name}'...")
    doc = create_opensim_document(config.model_name)

    # Export bodies and joints
    print("Exporting bodies and joints...")
    export_bodies_and_joints(doc, hierarchy, config)

    # Export markers
    print("Exporting markers...")
    export_markers(doc, armature_obj, config)

    # Write file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing OpenSim file to '{output_file}'...")
    write_opensim_file(doc, str(output_path))

    print(f"Export complete! Model '{config.model_name}' written to '{output_file}'")
