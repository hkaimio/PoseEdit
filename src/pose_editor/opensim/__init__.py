"""
OpenSim integration package for Blender armature export/import.

This package provides:
- Configuration system for defining armature-to-OpenSim mappings
- Export functionality to convert Blender armatures to OpenSim models
- Import functionality to apply OpenSim solutions back to Blender animations
"""

from .config import (
    JointType,
    AxisConstraint,
    JointConstraints,
    BoneConfig,
    MarkerConfig,
    ArmatureExportConfig,
)

__all__ = [
    "JointType",
    "AxisConstraint",
    "JointConstraints",
    "BoneConfig",
    "MarkerConfig",
    "ArmatureExportConfig",
]
