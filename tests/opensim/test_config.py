"""Unit tests for OpenSim configuration system."""

import math

import pytest

from pose_editor.opensim.config import (
    ArmatureExportConfig,
    AxisConstraint,
    BoneConfig,
    JointConstraints,
    JointType,
    MarkerConfig,
)


class TestAxisConstraint:
    """Test cases for AxisConstraint dataclass."""

    def test_default_values(self):
        """Test default constraint values."""
        constraint = AxisConstraint()
        assert constraint.locked is False
        assert constraint.min_angle == -90.0
        assert constraint.max_angle == 90.0

    def test_custom_values(self):
        """Test custom constraint values."""
        constraint = AxisConstraint(locked=True, min_angle=-45.0, max_angle=45.0)
        assert constraint.locked is True
        assert constraint.min_angle == -45.0
        assert constraint.max_angle == 45.0

    def test_to_radians(self):
        """Test conversion from degrees to radians."""
        constraint = AxisConstraint(min_angle=-90.0, max_angle=90.0)
        min_rad, max_rad = constraint.to_radians()
        assert min_rad == pytest.approx(-math.pi / 2)
        assert max_rad == pytest.approx(math.pi / 2)

    def test_to_radians_custom(self):
        """Test conversion with custom angles."""
        constraint = AxisConstraint(min_angle=-45.0, max_angle=180.0)
        min_rad, max_rad = constraint.to_radians()
        assert min_rad == pytest.approx(-math.pi / 4)
        assert max_rad == pytest.approx(math.pi)

    def test_validate_unlocked_valid(self):
        """Test validation of valid unlocked constraint."""
        constraint = AxisConstraint(locked=False, min_angle=-90.0, max_angle=90.0)
        errors = constraint.validate()
        assert len(errors) == 0

    def test_validate_locked(self):
        """Test validation of locked constraint - should not check angles."""
        constraint = AxisConstraint(locked=True, min_angle=100.0, max_angle=50.0)
        errors = constraint.validate()
        assert len(errors) == 0  # Locked constraints skip angle validation

    def test_validate_min_greater_than_max(self):
        """Test validation with min_angle >= max_angle."""
        constraint = AxisConstraint(locked=False, min_angle=90.0, max_angle=45.0)
        errors = constraint.validate()
        assert len(errors) == 1
        assert "min_angle" in errors[0]
        assert "max_angle" in errors[0]

    def test_validate_angle_out_of_range(self):
        """Test validation with angles outside reasonable range."""
        constraint = AxisConstraint(locked=False, min_angle=-400.0, max_angle=500.0)
        errors = constraint.validate()
        assert len(errors) == 2
        assert any("min_angle" in e for e in errors)
        assert any("max_angle" in e for e in errors)


class TestJointConstraints:
    """Test cases for JointConstraints dataclass."""

    def test_default_custom_joint(self):
        """Test default CUSTOM joint initialization."""
        constraints = JointConstraints(joint_type=JointType.CUSTOM)
        assert constraints.joint_type == JointType.CUSTOM
        assert constraints.x_axis is not None
        assert constraints.y_axis is not None
        assert constraints.z_axis is not None
        assert isinstance(constraints.x_axis, AxisConstraint)

    def test_free_joint(self):
        """Test FREE joint initialization."""
        constraints = JointConstraints(joint_type=JointType.FREE)
        assert constraints.joint_type == JointType.FREE
        # FREE joints don't need axis constraints
        assert constraints.x_axis is None
        assert constraints.y_axis is None
        assert constraints.z_axis is None

    def test_custom_axis_constraints(self):
        """Test CUSTOM joint with specific axis constraints."""
        x_axis = AxisConstraint(locked=True)
        y_axis = AxisConstraint(locked=False, min_angle=0, max_angle=140)
        z_axis = AxisConstraint(locked=True)

        constraints = JointConstraints(
            joint_type=JointType.CUSTOM, x_axis=x_axis, y_axis=y_axis, z_axis=z_axis
        )

        assert constraints.x_axis.locked is True
        assert constraints.y_axis.locked is False
        assert constraints.y_axis.max_angle == 140
        assert constraints.z_axis.locked is True

    def test_get_unlocked_axes_all_unlocked(self):
        """Test getting unlocked axes when all are unlocked."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False),
            y_axis=AxisConstraint(locked=False),
            z_axis=AxisConstraint(locked=False),
        )
        unlocked = constraints.get_unlocked_axes()
        assert unlocked == ["x", "y", "z"]

    def test_get_unlocked_axes_partial(self):
        """Test getting unlocked axes with some locked."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=True),
            y_axis=AxisConstraint(locked=False),
            z_axis=AxisConstraint(locked=True),
        )
        unlocked = constraints.get_unlocked_axes()
        assert unlocked == ["y"]

    def test_get_unlocked_axes_all_locked(self):
        """Test getting unlocked axes when all are locked."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=True),
            y_axis=AxisConstraint(locked=True),
            z_axis=AxisConstraint(locked=True),
        )
        unlocked = constraints.get_unlocked_axes()
        assert unlocked == []

    def test_get_unlocked_axes_free_joint(self):
        """Test getting unlocked axes for FREE joint."""
        constraints = JointConstraints(joint_type=JointType.FREE)
        unlocked = constraints.get_unlocked_axes()
        assert unlocked == ["x", "y", "z"]

    def test_get_dof_count_free(self):
        """Test DOF count for FREE joint."""
        constraints = JointConstraints(joint_type=JointType.FREE)
        assert constraints.get_dof_count() == 6

    def test_get_dof_count_custom_3dof(self):
        """Test DOF count for CUSTOM joint with 3 DOF."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False),
            y_axis=AxisConstraint(locked=False),
            z_axis=AxisConstraint(locked=False),
        )
        assert constraints.get_dof_count() == 3

    def test_get_dof_count_custom_1dof(self):
        """Test DOF count for CUSTOM joint with 1 DOF (hinge)."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=True),
            y_axis=AxisConstraint(locked=False),
            z_axis=AxisConstraint(locked=True),
        )
        assert constraints.get_dof_count() == 1

    def test_get_dof_count_custom_0dof(self):
        """Test DOF count for CUSTOM joint with 0 DOF (fixed)."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=True),
            y_axis=AxisConstraint(locked=True),
            z_axis=AxisConstraint(locked=True),
        )
        assert constraints.get_dof_count() == 0

    def test_validate_custom_valid(self):
        """Test validation of valid CUSTOM joint."""
        constraints = JointConstraints(joint_type=JointType.CUSTOM)
        errors = constraints.validate()
        assert len(errors) == 0

    def test_validate_free_valid(self):
        """Test validation of valid FREE joint."""
        constraints = JointConstraints(joint_type=JointType.FREE)
        errors = constraints.validate()
        assert len(errors) == 0

    def test_validate_custom_invalid_axis(self):
        """Test validation with invalid axis constraint."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False, min_angle=90, max_angle=45),  # Invalid
            y_axis=AxisConstraint(locked=False),
            z_axis=AxisConstraint(locked=False),
        )
        errors = constraints.validate()
        assert len(errors) > 0
        assert any("x_axis" in e for e in errors)


class TestBoneConfig:
    """Test cases for BoneConfig dataclass."""

    def test_minimal_config(self):
        """Test minimal bone configuration."""
        config = BoneConfig(
            blender_name="test_bone",
            opensim_name="test",
            constraints=JointConstraints(joint_type=JointType.FREE),
        )
        assert config.blender_name == "test_bone"
        assert config.opensim_name == "test"
        assert config.export_body is True
        assert config.body_mass == 1.0
        assert len(config.body_inertia) == 6

    def test_full_config(self):
        """Test full bone configuration with all parameters."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=90),
            y_axis=AxisConstraint(locked=True),
            z_axis=AxisConstraint(locked=False, min_angle=-45, max_angle=45),
        )

        config = BoneConfig(
            blender_name="forearm.R",
            opensim_name="ulna_r",
            constraints=constraints,
            export_body=True,
            body_mass=1.5,
            body_inertia=(0.015, 0.015, 0.015, 0.0, 0.0, 0.0),
        )

        assert config.blender_name == "forearm.R"
        assert config.opensim_name == "ulna_r"
        assert config.body_mass == 1.5
        assert config.body_inertia == (0.015, 0.015, 0.015, 0.0, 0.0, 0.0)

    def test_validate_valid(self):
        """Test validation of valid bone config."""
        config = BoneConfig(
            blender_name="test",
            opensim_name="test",
            constraints=JointConstraints(joint_type=JointType.FREE),
        )
        errors = config.validate()
        assert len(errors) == 0

    def test_validate_empty_names(self):
        """Test validation with empty names."""
        config = BoneConfig(
            blender_name="",
            opensim_name="",
            constraints=JointConstraints(joint_type=JointType.FREE),
        )
        errors = config.validate()
        assert len(errors) >= 2
        assert any("blender_name" in e for e in errors)
        assert any("opensim_name" in e for e in errors)

    def test_validate_negative_mass(self):
        """Test validation with negative mass."""
        config = BoneConfig(
            blender_name="test",
            opensim_name="test",
            constraints=JointConstraints(joint_type=JointType.FREE),
            body_mass=-1.0,
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("body_mass" in e for e in errors)

    def test_validate_invalid_inertia_length(self):
        """Test validation with wrong inertia tensor length."""
        config = BoneConfig(
            blender_name="test",
            opensim_name="test",
            constraints=JointConstraints(joint_type=JointType.FREE),
            body_inertia=(1.0, 1.0, 1.0),  # Only 3 elements
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("body_inertia" in e and "6 elements" in e for e in errors)

    def test_validate_invalid_inertia_diagonal(self):
        """Test validation with non-positive diagonal inertia elements."""
        config = BoneConfig(
            blender_name="test",
            opensim_name="test",
            constraints=JointConstraints(joint_type=JointType.FREE),
            body_inertia=(0.0, -1.0, 1.0, 0.0, 0.0, 0.0),  # Invalid diagonal
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("diagonal" in e.lower() for e in errors)

    def test_validate_propagates_constraint_errors(self):
        """Test that validation propagates errors from constraints."""
        constraints = JointConstraints(
            joint_type=JointType.CUSTOM,
            x_axis=AxisConstraint(locked=False, min_angle=90, max_angle=45),  # Invalid
            y_axis=AxisConstraint(locked=False),
            z_axis=AxisConstraint(locked=False),
        )

        config = BoneConfig(
            blender_name="test", opensim_name="test", constraints=constraints
        )

        errors = config.validate()
        assert len(errors) > 0
        assert any("constraints" in e for e in errors)


class TestMarkerConfig:
    """Test cases for MarkerConfig dataclass."""

    def test_default_empty(self):
        """Test default empty marker config."""
        config = MarkerConfig()
        assert config.overrides == {}

    def test_with_overrides(self):
        """Test marker config with overrides."""
        overrides = {"MRK-shoulder.R": "R_Shoulder", "MRK-elbow.L": "L_Elbow"}
        config = MarkerConfig(overrides=overrides)
        assert config.overrides == overrides

    def test_get_marker_name_with_override(self):
        """Test getting marker name with override."""
        config = MarkerConfig(overrides={"MRK-shoulder.R": "R_Shoulder"})
        assert config.get_marker_name("MRK-shoulder.R") == "R_Shoulder"

    def test_get_marker_name_without_override(self):
        """Test getting marker name without override (default formatting)."""
        config = MarkerConfig()
        # Should remove MRK- prefix and capitalize
        assert config.get_marker_name("MRK-shoulder") == "Shoulder"

    def test_get_marker_name_right_suffix(self):
        """Test marker name formatting with .R suffix."""
        config = MarkerConfig()
        assert config.get_marker_name("MRK-shoulder.R") == "R_Shoulder"

    def test_get_marker_name_left_suffix(self):
        """Test marker name formatting with .L suffix."""
        config = MarkerConfig()
        assert config.get_marker_name("MRK-elbow.L") == "L_Elbow"

    def test_get_marker_name_no_prefix(self):
        """Test marker name formatting without MRK- prefix."""
        config = MarkerConfig()
        assert config.get_marker_name("shoulder.R") == "R_Shoulder"

    def test_validate_valid(self):
        """Test validation of valid marker config."""
        config = MarkerConfig(overrides={"bone1": "marker1", "bone2": "marker2"})
        errors = config.validate()
        assert len(errors) == 0

    def test_validate_empty_blender_name(self):
        """Test validation with empty Blender name in overrides."""
        config = MarkerConfig(overrides={"": "marker1"})
        errors = config.validate()
        assert len(errors) > 0
        assert any("empty Blender name" in e for e in errors)

    def test_validate_empty_opensim_name(self):
        """Test validation with empty OpenSim name in overrides."""
        config = MarkerConfig(overrides={"bone1": ""})
        errors = config.validate()
        assert len(errors) > 0
        assert any("bone1" in e and "empty OpenSim name" in e for e in errors)


class TestArmatureExportConfig:
    """Test cases for ArmatureExportConfig class."""

    def test_default_initialization(self):
        """Test default config initialization."""
        config = ArmatureExportConfig()
        assert config.model_name == "ExportedModel"
        assert config.bones == {}
        assert isinstance(config.marker_config, MarkerConfig)
        assert config.marker_collection_name == "Markers"

    def test_add_bone(self):
        """Test adding a bone to configuration."""
        config = ArmatureExportConfig()
        bone_config = BoneConfig(
            blender_name="pelvis",
            opensim_name="pelvis",
            constraints=JointConstraints(joint_type=JointType.FREE),
        )
        config.add_bone(bone_config)
        assert "pelvis" in config.bones
        assert config.bones["pelvis"] == bone_config

    def test_add_duplicate_bone_raises_error(self):
        """Test that adding duplicate bone raises ValueError."""
        config = ArmatureExportConfig()
        bone_config = BoneConfig(
            blender_name="pelvis",
            opensim_name="pelvis",
            constraints=JointConstraints(joint_type=JointType.FREE),
        )
        config.add_bone(bone_config)

        # Try to add again
        with pytest.raises(ValueError, match="already exists"):
            config.add_bone(bone_config)

    def test_get_bone_config_exists(self):
        """Test getting existing bone config."""
        config = ArmatureExportConfig()
        bone_config = BoneConfig(
            blender_name="pelvis",
            opensim_name="pelvis",
            constraints=JointConstraints(joint_type=JointType.FREE),
        )
        config.add_bone(bone_config)

        retrieved = config.get_bone_config("pelvis")
        assert retrieved == bone_config

    def test_get_bone_config_not_exists(self):
        """Test getting non-existent bone config returns None."""
        config = ArmatureExportConfig()
        assert config.get_bone_config("nonexistent") is None

    def test_is_exported_true(self):
        """Test is_exported returns True for configured bone."""
        config = ArmatureExportConfig()
        bone_config = BoneConfig(
            blender_name="pelvis",
            opensim_name="pelvis",
            constraints=JointConstraints(joint_type=JointType.FREE),
        )
        config.add_bone(bone_config)
        assert config.is_exported("pelvis") is True

    def test_is_exported_false(self):
        """Test is_exported returns False for unconfigured bone."""
        config = ArmatureExportConfig()
        assert config.is_exported("nonexistent") is False

    def test_get_bone_count(self):
        """Test getting bone count."""
        config = ArmatureExportConfig()
        assert config.get_bone_count() == 0

        for i in range(3):
            config.add_bone(
                BoneConfig(
                    blender_name=f"bone{i}",
                    opensim_name=f"bone{i}",
                    constraints=JointConstraints(joint_type=JointType.FREE),
                )
            )

        assert config.get_bone_count() == 3

    def test_get_total_dof(self):
        """Test getting total degrees of freedom."""
        config = ArmatureExportConfig()

        # Add FREE joint (6 DOF)
        config.add_bone(
            BoneConfig(
                blender_name="pelvis",
                opensim_name="pelvis",
                constraints=JointConstraints(joint_type=JointType.FREE),
            )
        )

        # Add hinge joint (1 DOF)
        config.add_bone(
            BoneConfig(
                blender_name="elbow",
                opensim_name="elbow",
                constraints=JointConstraints(
                    joint_type=JointType.CUSTOM,
                    x_axis=AxisConstraint(locked=True),
                    y_axis=AxisConstraint(locked=False),
                    z_axis=AxisConstraint(locked=True),
                ),
            )
        )

        # Add ball joint (3 DOF)
        config.add_bone(
            BoneConfig(
                blender_name="shoulder",
                opensim_name="shoulder",
                constraints=JointConstraints(
                    joint_type=JointType.CUSTOM,
                    x_axis=AxisConstraint(locked=False),
                    y_axis=AxisConstraint(locked=False),
                    z_axis=AxisConstraint(locked=False),
                ),
            )
        )

        assert config.get_total_dof() == 10  # 6 + 1 + 3

    def test_validate_valid_config(self):
        """Test validation of valid configuration."""
        config = ArmatureExportConfig()
        config.model_name = "TestModel"
        config.add_bone(
            BoneConfig(
                blender_name="pelvis",
                opensim_name="pelvis",
                constraints=JointConstraints(joint_type=JointType.FREE),
            )
        )

        errors = config.validate()
        assert len(errors) == 0

    def test_validate_empty_model_name(self):
        """Test validation with empty model name."""
        config = ArmatureExportConfig()
        config.model_name = ""
        config.add_bone(
            BoneConfig(
                blender_name="pelvis",
                opensim_name="pelvis",
                constraints=JointConstraints(joint_type=JointType.FREE),
            )
        )

        errors = config.validate()
        assert len(errors) > 0
        assert any("model_name" in e for e in errors)

    def test_validate_no_bones(self):
        """Test validation with no bones configured."""
        config = ArmatureExportConfig()
        errors = config.validate()
        assert len(errors) > 0
        assert any("at least one bone" in e for e in errors)

    def test_validate_duplicate_opensim_names(self):
        """Test validation detects duplicate OpenSim names."""
        config = ArmatureExportConfig()
        config.add_bone(
            BoneConfig(
                blender_name="bone1",
                opensim_name="duplicate",
                constraints=JointConstraints(joint_type=JointType.FREE),
            )
        )
        config.add_bone(
            BoneConfig(
                blender_name="bone2",
                opensim_name="duplicate",
                constraints=JointConstraints(joint_type=JointType.FREE),
            )
        )

        errors = config.validate()
        assert len(errors) > 0
        assert any("Duplicate OpenSim names" in e for e in errors)

    def test_validate_propagates_bone_errors(self):
        """Test that validation propagates errors from bone configs."""
        config = ArmatureExportConfig()
        config.add_bone(
            BoneConfig(
                blender_name="",  # Invalid empty name
                opensim_name="test",
                constraints=JointConstraints(joint_type=JointType.FREE),
            )
        )

        errors = config.validate()
        assert len(errors) > 0
        assert any("blender_name" in e for e in errors)

    def test_validate_propagates_marker_errors(self):
        """Test that validation propagates errors from marker config."""
        config = ArmatureExportConfig()
        config.add_bone(
            BoneConfig(
                blender_name="pelvis",
                opensim_name="pelvis",
                constraints=JointConstraints(joint_type=JointType.FREE),
            )
        )
        config.marker_config.overrides = {"bone1": ""}  # Invalid empty OpenSim name

        errors = config.validate()
        assert len(errors) > 0
        assert any("Marker config" in e for e in errors)

    def test_repr(self):
        """Test string representation."""
        config = ArmatureExportConfig()
        config.model_name = "TestModel"
        config.add_bone(
            BoneConfig(
                blender_name="pelvis",
                opensim_name="pelvis",
                constraints=JointConstraints(joint_type=JointType.FREE),
            )
        )

        repr_str = repr(config)
        assert "TestModel" in repr_str
        assert "bones=1" in repr_str
        assert "total_dof=6" in repr_str
