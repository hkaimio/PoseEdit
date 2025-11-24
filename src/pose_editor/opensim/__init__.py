"""
OpenSim integration package for Blender armature export/import.

This package provides:
- Configuration system for defining armature-to-OpenSim mappings
- Export functionality to convert Blender armatures to OpenSim models
- Import functionality to apply OpenSim solutions back to Blender animations
"""

from .config import (
    ArmatureExportConfig,
    AxisConstraint,
    BoneConfig,
    JointConstraints,
    JointType,
    MarkerConfig,
)
from .export import export_armature_to_opensim_with_config
from .hierarchy import BoneHierarchyNode, build_export_hierarchy, get_hierarchy_info
from .opensim_xml import (
    create_joint_from_config,
    create_opensim_body,
    create_opensim_custom_joint_from_config,
    create_opensim_document,
    create_opensim_free_joint,
    create_opensim_marker,
    create_opensim_weld_joint,
    write_opensim_file,
)
from .solution_import import (
    OpenSimSolutionData,
    apply_solution_to_armature,
    build_coordinate_to_bone_map,
    import_opensim_solution,
    parse_opensim_solution,
)

__all__ = [
    # Configuration
    "JointType",
    "AxisConstraint",
    "JointConstraints",
    "BoneConfig",
    "MarkerConfig",
    "ArmatureExportConfig",
    # Export
    "export_armature_to_opensim_with_config",
    # Import
    "import_opensim_solution",
    "parse_opensim_solution",
    "OpenSimSolutionData",
    "build_coordinate_to_bone_map",
    "apply_solution_to_armature",
    # Hierarchy
    "BoneHierarchyNode",
    "build_export_hierarchy",
    "get_hierarchy_info",
    # XML Generation
    "create_opensim_document",
    "create_opensim_body",
    "create_opensim_free_joint",
    "create_opensim_weld_joint",
    "create_opensim_custom_joint_from_config",
    "create_joint_from_config",
    "create_opensim_marker",
    "write_opensim_file",
]
