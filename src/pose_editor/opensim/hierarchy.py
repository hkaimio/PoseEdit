"""
Hierarchy building for OpenSim armature export.

This module provides functionality to build an export hierarchy tree from a Blender
armature, including only bones that are configured for export.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import bpy

from .config import ArmatureExportConfig, BoneConfig


@dataclass
class BoneHierarchyNode:
    """
    Node in the export hierarchy tree.

    Attributes:
        blender_bone: Reference to Blender pose bone
        config: Configuration for this bone
        parent: Parent node in hierarchy (None for root)
        children: List of child nodes
    """

    blender_bone: "bpy.types.PoseBone"
    config: BoneConfig
    parent: "BoneHierarchyNode | None" = None
    children: list["BoneHierarchyNode"] = field(default_factory=list)

    @property
    def bone_name(self) -> str:
        """Get Blender bone name."""
        return self.blender_bone.name

    @property
    def opensim_name(self) -> str:
        """Get OpenSim name for this bone."""
        return self.config.opensim_name

    @property
    def bone_config(self) -> BoneConfig:
        """Get bone configuration (alias for .config)."""
        return self.config

    @property
    def is_root(self) -> bool:
        """Check if this is a root node."""
        return self.parent is None

    @property
    def is_leaf(self) -> bool:
        """Check if this is a leaf node."""
        return len(self.children) == 0

    def get_depth(self) -> int:
        """
        Get depth in hierarchy (root = 0).

        Returns:
            Depth level
        """
        if self.parent is None:
            return 0
        return self.parent.get_depth() + 1

    def get_all_descendants(self) -> list["BoneHierarchyNode"]:
        """
        Get all descendant nodes (children, grandchildren, etc.).

        Returns:
            List of all descendant nodes
        """
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants

    def find_child_by_name(self, blender_name: str) -> "BoneHierarchyNode | None":
        """
        Find direct child by Blender bone name.

        Args:
            blender_name: Name of bone to find

        Returns:
            Child node if found, None otherwise
        """
        for child in self.children:
            if child.bone_name == blender_name:
                return child
        return None

    def __repr__(self) -> str:
        """String representation of node."""
        return (
            f"BoneHierarchyNode(bone='{self.bone_name}', "
            f"opensim='{self.opensim_name}', children={len(self.children)})"
        )


def find_configured_parent(
    pose_bone: "bpy.types.PoseBone", config: ArmatureExportConfig
) -> "bpy.types.PoseBone | None":
    """
    Find the nearest parent bone that is in the configuration.

    This traverses up the hierarchy to find the first configured parent,
    skipping any intermediate bones that are not configured for export.

    Args:
        pose_bone: Starting bone
        config: Export configuration

    Returns:
        First configured parent bone, or None if no configured parent exists
    """
    current = pose_bone.parent
    while current:
        if config.is_exported(current.name):
            return current
        current = current.parent
    return None


def build_export_hierarchy(armature_obj: "bpy.types.Object", config: ArmatureExportConfig) -> BoneHierarchyNode:
    """
    Build hierarchy tree from Blender armature, including only configured bones.

    This function creates a tree structure representing the bones that should be
    exported to OpenSim, automatically determining parent-child relationships
    based on the Blender armature hierarchy.

    Args:
        armature_obj: Blender armature object
        config: Export configuration

    Returns:
        Root node of hierarchy tree

    Raises:
        ValueError: If armature is invalid or no root bone is found
    """
    if armature_obj.type != "ARMATURE":
        raise ValueError(f"Object '{armature_obj.name}' is not an armature")

    pose_bones = armature_obj.pose.bones

    # Validate that all configured bones exist in armature
    missing_bones = []
    for bone_name in config.bones.keys():
        if bone_name not in pose_bones:
            missing_bones.append(bone_name)

    if missing_bones:
        raise ValueError(f"Bones not found in armature: {', '.join(missing_bones)}")

    # Find root bone (configured bone with no configured parent)
    root_bone = None
    for bone_name in config.bones.keys():
        pose_bone = pose_bones[bone_name]

        # Check if this bone has a configured parent
        configured_parent = find_configured_parent(pose_bone, config)

        if configured_parent is None:
            if root_bone is not None:
                raise ValueError(
                    f"Multiple root bones found: '{root_bone.name}' and '{pose_bone.name}'. "
                    "Configuration must have exactly one root bone."
                )
            root_bone = pose_bone

    if root_bone is None:
        raise ValueError("No root bone found in configuration (bone with no configured parent)")

    # Build tree recursively
    def build_node(pose_bone: "bpy.types.PoseBone", parent_node: BoneHierarchyNode | None = None) -> BoneHierarchyNode:
        """Build a node and its children."""
        bone_config = config.get_bone_config(pose_bone.name)
        if not bone_config:
            raise ValueError(f"No configuration found for bone '{pose_bone.name}'")

        node = BoneHierarchyNode(blender_bone=pose_bone, config=bone_config, parent=parent_node)

        # Find all children that should be direct children in export hierarchy
        # A child is direct if it's configured, or if one of its descendants is configured
        # and there's no configured bone in between
        for child_bone in pose_bone.children:
            child_node = find_and_build_child(child_bone, node)
            if child_node:
                node.children.append(child_node)

        return node

    def find_and_build_child(
        pose_bone: "bpy.types.PoseBone", parent_node: BoneHierarchyNode
    ) -> BoneHierarchyNode | None:
        """
        Find next configured bone in hierarchy and build it as a child.

        This recursively searches down the hierarchy to find configured bones,
        skipping any unconfigured intermediate bones.
        """
        if config.is_exported(pose_bone.name):
            # This bone is configured, build it as a child
            return build_node(pose_bone, parent_node)
        else:
            # This bone is not configured, check its children
            # If multiple children are configured, they all become children of parent_node
            children = []
            for child in pose_bone.children:
                child_node = find_and_build_child(child, parent_node)
                if child_node:
                    children.append(child_node)

            # If exactly one configured child found, return it
            # If multiple found, they were already added to parent in recursive calls
            if len(children) == 1:
                return children[0]
            elif len(children) > 1:
                # Multiple branches - add them all to parent's children
                # (this shouldn't happen in this return path, but handle it)
                for child in children[1:]:
                    parent_node.children.append(child)
                return children[0]
            else:
                return None

    return build_node(root_bone)


def get_hierarchy_info(root: BoneHierarchyNode) -> dict[str, any]:
    """
    Get information about the hierarchy tree.

    Args:
        root: Root node of hierarchy

    Returns:
        Dictionary with hierarchy statistics
    """
    all_nodes = [root] + root.get_all_descendants()

    return {
        "total_bones": len(all_nodes),
        "max_depth": max(node.get_depth() for node in all_nodes),
        "leaf_bones": sum(1 for node in all_nodes if node.is_leaf),
        "total_dof": sum(node.config.constraints.get_dof_count() for node in all_nodes),
        "root_bone": root.bone_name,
    }


def print_hierarchy(root: BoneHierarchyNode, indent: int = 0):
    """
    Print hierarchy tree for debugging.

    Args:
        root: Root node to print from
        indent: Current indentation level
    """
    indent_str = "  " * indent
    dof = root.config.constraints.get_dof_count()
    print(f"{indent_str}{root.bone_name} ({root.opensim_name}) - {dof} DOF")

    for child in root.children:
        print_hierarchy(child, indent + 1)
