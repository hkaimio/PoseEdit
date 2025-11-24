"""
Configuration system for OpenSim armature export.

This module provides dataclasses and enums for defining how Blender armatures
should be exported to OpenSim models, including joint types, constraints,
and marker configurations.
"""

import math
from dataclasses import dataclass, field
from enum import Enum


class JointType(Enum):
    """Type of joint to create in OpenSim."""

    FREE = "free"  # 6 DOF (3 translation + 3 rotation)
    CUSTOM = "custom"  # 0-3 DOF rotation only


@dataclass
class AxisConstraint:
    """
    Constraint configuration for a single rotation axis.

    Attributes:
        locked: If True, axis is completely locked (no coordinate exposed to OpenSim)
        min_angle: Minimum angle in degrees
        max_angle: Maximum angle in degrees
    """

    locked: bool = False
    min_angle: float = -90.0
    max_angle: float = 90.0

    def to_radians(self) -> tuple[float, float]:
        """
        Convert angles to radians for OpenSim.

        Returns:
            Tuple of (min_angle_rad, max_angle_rad)
        """
        return (math.radians(self.min_angle), math.radians(self.max_angle))

    def validate(self) -> list[str]:
        """
        Validate constraint parameters.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if not self.locked:
            if self.min_angle >= self.max_angle:
                errors.append(
                    f"min_angle ({self.min_angle}) must be less than max_angle ({self.max_angle})"
                )
            if self.min_angle < -360 or self.min_angle > 360:
                errors.append(
                    f"min_angle ({self.min_angle}) should be between -360 and 360 degrees"
                )
            if self.max_angle < -360 or self.max_angle > 360:
                errors.append(
                    f"max_angle ({self.max_angle}) should be between -360 and 360 degrees"
                )

        return errors


@dataclass
class JointConstraints:
    """
    Joint constraint configuration.

    Attributes:
        joint_type: Type of joint (FREE or CUSTOM)
        x_axis: Rotation constraint around X axis (for CUSTOM joints)
        y_axis: Rotation constraint around Y axis (for CUSTOM joints)
        z_axis: Rotation constraint around Z axis (for CUSTOM joints)
    """

    joint_type: JointType = JointType.CUSTOM
    x_axis: AxisConstraint | None = None
    y_axis: AxisConstraint | None = None
    z_axis: AxisConstraint | None = None

    def __post_init__(self):
        """Set default constraints for CUSTOM joints if not provided."""
        if self.joint_type == JointType.CUSTOM:
            if self.x_axis is None:
                self.x_axis = AxisConstraint()
            if self.y_axis is None:
                self.y_axis = AxisConstraint()
            if self.z_axis is None:
                self.z_axis = AxisConstraint()

    def get_unlocked_axes(self) -> list[str]:
        """
        Get list of unlocked axis names.

        Returns:
            List of axis names ('x', 'y', 'z') that are not locked
        """
        unlocked = []
        if self.joint_type == JointType.FREE:
            return ["x", "y", "z"]

        if self.x_axis and not self.x_axis.locked:
            unlocked.append("x")
        if self.y_axis and not self.y_axis.locked:
            unlocked.append("y")
        if self.z_axis and not self.z_axis.locked:
            unlocked.append("z")

        return unlocked

    def get_dof_count(self) -> int:
        """
        Get the number of degrees of freedom.

        Returns:
            Number of DOF (6 for FREE joints, 0-3 for CUSTOM joints)
        """
        if self.joint_type == JointType.FREE:
            return 6
        return len(self.get_unlocked_axes())

    def validate(self) -> list[str]:
        """
        Validate joint constraints.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if self.joint_type == JointType.CUSTOM:
            if self.x_axis is None or self.y_axis is None or self.z_axis is None:
                errors.append("CUSTOM joints must have all three axis constraints defined")
            else:
                # Validate each axis
                for axis_name, axis in [("x", self.x_axis), ("y", self.y_axis), ("z", self.z_axis)]:
                    axis_errors = axis.validate()
                    for error in axis_errors:
                        errors.append(f"{axis_name}_axis: {error}")

        return errors


@dataclass
class BoneConfig:
    """
    Configuration for a single bone export.

    Attributes:
        blender_name: Name of the bone in Blender armature
        opensim_name: Name to use in exported OpenSim model
        constraints: Joint constraints for this bone
        export_body: Whether to export as OpenSim Body
        body_mass: Mass for OpenSim Body in kilograms
        body_inertia: Inertia tensor (Ixx, Iyy, Izz, Ixy, Ixz, Iyz)
    """

    blender_name: str
    opensim_name: str
    constraints: JointConstraints
    export_body: bool = True
    body_mass: float = 1.0
    body_inertia: tuple[float, float, float, float, float, float] = (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)

    def validate(self) -> list[str]:
        """
        Validate bone configuration.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if not self.blender_name:
            errors.append("blender_name cannot be empty")
        if not self.opensim_name:
            errors.append("opensim_name cannot be empty")

        # Validate joint constraints
        constraint_errors = self.constraints.validate()
        for error in constraint_errors:
            errors.append(f"constraints: {error}")

        # Validate body properties
        if self.body_mass <= 0:
            errors.append(f"body_mass ({self.body_mass}) must be positive")

        if len(self.body_inertia) != 6:
            errors.append(f"body_inertia must have 6 elements, got {len(self.body_inertia)}")
        else:
            # Check that diagonal elements are positive
            if self.body_inertia[0] <= 0 or self.body_inertia[1] <= 0 or self.body_inertia[2] <= 0:
                errors.append("body_inertia diagonal elements (Ixx, Iyy, Izz) must be positive")

        return errors


@dataclass
class MarkerConfig:
    """
    Configuration for marker name overrides.

    Attributes:
        overrides: Dictionary mapping Blender bone names to OpenSim marker names
    """

    overrides: dict[str, str] = field(default_factory=dict)

    def get_marker_name(self, blender_bone_name: str) -> str:
        """
        Get the OpenSim marker name for a Blender bone.

        Args:
            blender_bone_name: Name of the bone in Blender

        Returns:
            OpenSim marker name (override if exists, otherwise formatted name)
        """
        if blender_bone_name in self.overrides:
            return self.overrides[blender_bone_name]

        # Default formatting: remove "MRK-" prefix, capitalize, handle .L/.R postfix
        name = blender_bone_name

        if name.startswith("MRK-"):
            name = name[4:]

        if name:
            name = name[0].upper() + name[1:]

        if name.endswith(".L"):
            name = "L" + name[:-2]
        elif name.endswith(".R"):
            name = "R" + name[:-2]

        return name

    def validate(self) -> list[str]:
        """
        Validate marker configuration.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        for blender_name, opensim_name in self.overrides.items():
            if not blender_name:
                errors.append("Marker override has empty Blender name")
            if not opensim_name:
                errors.append(f"Marker override for '{blender_name}' has empty OpenSim name")

        return errors


class ArmatureExportConfig:
    """
    Main configuration class for armature export.

    Attributes:
        model_name: Name for the exported OpenSim model
        bones: Dictionary mapping Blender bone names to BoneConfig
        marker_config: Configuration for marker name overrides
        marker_collection_name: Name of the Blender bone collection containing markers
    """

    def __init__(self):
        """Initialize empty configuration."""
        self.model_name: str = "ExportedModel"
        self.bones: dict[str, BoneConfig] = {}
        self.marker_config: MarkerConfig = MarkerConfig()
        self.marker_collection_name: str = "Markers"

    def add_bone(self, bone_config: BoneConfig):
        """
        Add a bone configuration.

        Args:
            bone_config: Configuration for the bone

        Raises:
            ValueError: If bone with same Blender name already exists
        """
        if bone_config.blender_name in self.bones:
            raise ValueError(f"Bone '{bone_config.blender_name}' already exists in configuration")
        self.bones[bone_config.blender_name] = bone_config

    def get_bone_config(self, blender_name: str) -> BoneConfig | None:
        """
        Get configuration for a bone by Blender name.

        Args:
            blender_name: Name of the bone in Blender

        Returns:
            BoneConfig if found, None otherwise
        """
        return self.bones.get(blender_name)

    def is_exported(self, blender_name: str) -> bool:
        """
        Check if a bone should be exported.

        Args:
            blender_name: Name of the bone in Blender

        Returns:
            True if bone is in configuration, False otherwise
        """
        return blender_name in self.bones

    def get_bone_count(self) -> int:
        """
        Get the number of bones in configuration.

        Returns:
            Number of configured bones
        """
        return len(self.bones)

    def get_total_dof(self) -> int:
        """
        Get the total degrees of freedom across all joints.

        Returns:
            Sum of DOF for all configured joints
        """
        return sum(bone.constraints.get_dof_count() for bone in self.bones.values())

    def find_root_bones(self) -> list[str]:
        """
        Find bones that have no configured parent.

        Note: This method doesn't check the actual Blender hierarchy,
        it only identifies bones that could be roots based on the configuration.

        Returns:
            List of bone names that could be roots
        """
        # This is a simplified version - actual implementation will need
        # to check against Blender armature hierarchy
        return list(self.bones.keys())

    def validate(self) -> list[str]:
        """
        Validate the entire configuration.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if not self.model_name:
            errors.append("model_name cannot be empty")

        if not self.bones:
            errors.append("Configuration must have at least one bone")

        # Validate each bone
        for bone_name, bone_config in self.bones.items():
            bone_errors = bone_config.validate()
            for error in bone_errors:
                errors.append(f"Bone '{bone_name}': {error}")

        # Validate marker config
        marker_errors = self.marker_config.validate()
        for error in marker_errors:
            errors.append(f"Marker config: {error}")

        # Check for duplicate OpenSim names
        opensim_names = [bone.opensim_name for bone in self.bones.values()]
        duplicates = [name for name in opensim_names if opensim_names.count(name) > 1]
        if duplicates:
            unique_dupes = list(set(duplicates))
            errors.append(f"Duplicate OpenSim names found: {', '.join(unique_dupes)}")

        return errors

    def __repr__(self) -> str:
        """String representation of configuration."""
        return (
            f"ArmatureExportConfig(model_name='{self.model_name}', "
            f"bones={self.get_bone_count()}, total_dof={self.get_total_dof()})"
        )
