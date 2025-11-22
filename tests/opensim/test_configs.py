"""Unit tests for example OpenSim configurations."""

from pose_editor.opensim.configs import create_humanoid_config


class TestHumanoidConfig:
    """Test cases for humanoid configuration."""

    def test_create_config(self):
        """Test that humanoid config can be created."""
        config = create_humanoid_config()
        assert config is not None
        assert config.model_name == "HumanoidModel"

    def test_has_required_bones(self):
        """Test that humanoid config has required bones."""
        config = create_humanoid_config()

        # Check core bones exist
        required_bones = [
            "pelvis",
            "spine",
            "chest",
            "neck",
            "head",
            "upper_arm.R",
            "forearm.R",
            "hand.R",
            "upper_arm.L",
            "forearm.L",
            "hand.L",
            "thigh.R",
            "shin.R",
            "foot.R",
            "thigh.L",
            "shin.L",
            "foot.L",
        ]

        for bone_name in required_bones:
            assert config.is_exported(bone_name), f"Missing bone: {bone_name}"

    def test_bone_count(self):
        """Test that humanoid config has expected number of bones."""
        config = create_humanoid_config()
        # 5 torso + 6 upper limbs + 6 lower limbs
        assert config.get_bone_count() == 17

    def test_root_is_free_joint(self):
        """Test that pelvis (root) uses FREE joint."""
        config = create_humanoid_config()
        pelvis = config.get_bone_config("pelvis")
        assert pelvis is not None
        assert pelvis.constraints.joint_type.value == "free"
        assert pelvis.constraints.get_dof_count() == 6

    def test_elbow_is_hinge(self):
        """Test that elbows use hinge joints (1 DOF)."""
        config = create_humanoid_config()

        for side in ["R", "L"]:
            elbow = config.get_bone_config(f"forearm.{side}")
            assert elbow is not None
            assert elbow.constraints.joint_type.value == "custom"
            assert elbow.constraints.get_dof_count() == 1
            # Should only have Y axis unlocked
            unlocked = elbow.constraints.get_unlocked_axes()
            assert unlocked == ["y"]

    def test_knee_is_hinge(self):
        """Test that knees use hinge joints (1 DOF)."""
        config = create_humanoid_config()

        for side in ["R", "L"]:
            knee = config.get_bone_config(f"shin.{side}")
            assert knee is not None
            assert knee.constraints.joint_type.value == "custom"
            assert knee.constraints.get_dof_count() == 1
            # Should only have Y axis unlocked
            unlocked = knee.constraints.get_unlocked_axes()
            assert unlocked == ["y"]

    def test_shoulder_is_ball_joint(self):
        """Test that shoulders use ball joints (3 DOF)."""
        config = create_humanoid_config()

        for side in ["R", "L"]:
            shoulder = config.get_bone_config(f"upper_arm.{side}")
            assert shoulder is not None
            assert shoulder.constraints.joint_type.value == "custom"
            assert shoulder.constraints.get_dof_count() == 3
            # Should have all axes unlocked
            unlocked = shoulder.constraints.get_unlocked_axes()
            assert unlocked == ["x", "y", "z"]

    def test_hip_is_ball_joint(self):
        """Test that hips use ball joints (3 DOF)."""
        config = create_humanoid_config()

        for side in ["R", "L"]:
            hip = config.get_bone_config(f"thigh.{side}")
            assert hip is not None
            assert hip.constraints.joint_type.value == "custom"
            assert hip.constraints.get_dof_count() == 3
            # Should have all axes unlocked
            unlocked = hip.constraints.get_unlocked_axes()
            assert unlocked == ["x", "y", "z"]

    def test_wrist_has_2dof(self):
        """Test that wrists have 2 DOF."""
        config = create_humanoid_config()

        for side in ["R", "L"]:
            wrist = config.get_bone_config(f"hand.{side}")
            assert wrist is not None
            assert wrist.constraints.joint_type.value == "custom"
            assert wrist.constraints.get_dof_count() == 2
            # Should have X and Z unlocked, Y locked
            unlocked = wrist.constraints.get_unlocked_axes()
            assert "x" in unlocked
            assert "z" in unlocked
            assert "y" not in unlocked

    def test_ankle_has_2dof(self):
        """Test that ankles have 2 DOF."""
        config = create_humanoid_config()

        for side in ["R", "L"]:
            ankle = config.get_bone_config(f"foot.{side}")
            assert ankle is not None
            assert ankle.constraints.joint_type.value == "custom"
            assert ankle.constraints.get_dof_count() == 2
            # Should have X and Z unlocked, Y locked
            unlocked = ankle.constraints.get_unlocked_axes()
            assert "x" in unlocked
            assert "z" in unlocked
            assert "y" not in unlocked

    def test_total_dof(self):
        """Test total degrees of freedom in humanoid config."""
        config = create_humanoid_config()
        total_dof = config.get_total_dof()

        # Expected DOF:
        # 1 FREE joint (pelvis): 6
        # 4 spine/torso joints: 3+3+3+3 = 12
        # 2 shoulders: 3+3 = 6
        # 2 elbows: 1+1 = 2
        # 2 wrists: 2+2 = 4
        # 2 hips: 3+3 = 6
        # 2 knees: 1+1 = 2
        # 2 ankles: 2+2 = 4
        # Total: 6+12+6+2+4+6+2+4 = 42
        assert total_dof == 42

    def test_symmetric_limbs(self):
        """Test that left and right limbs have symmetric configurations."""
        config = create_humanoid_config()

        limb_pairs = [
            ("upper_arm.R", "upper_arm.L"),
            ("forearm.R", "forearm.L"),
            ("hand.R", "hand.L"),
            ("thigh.R", "thigh.L"),
            ("shin.R", "shin.L"),
            ("foot.R", "foot.L"),
        ]

        for right_bone, left_bone in limb_pairs:
            right_config = config.get_bone_config(right_bone)
            left_config = config.get_bone_config(left_bone)

            assert right_config is not None
            assert left_config is not None

            # Check same DOF
            assert right_config.constraints.get_dof_count() == left_config.constraints.get_dof_count()

            # Check same unlocked axes
            assert right_config.constraints.get_unlocked_axes() == left_config.constraints.get_unlocked_axes()

            # Check same mass
            assert right_config.body_mass == left_config.body_mass

    def test_opensim_names_unique(self):
        """Test that all OpenSim names are unique."""
        config = create_humanoid_config()
        opensim_names = [bone.opensim_name for bone in config.bones.values()]
        assert len(opensim_names) == len(set(opensim_names))

    def test_opensim_names_have_side_suffix(self):
        """Test that bilateral bones have _r or _l suffix."""
        config = create_humanoid_config()

        bilateral_bones = [
            "upper_arm.R",
            "upper_arm.L",
            "forearm.R",
            "forearm.L",
            "hand.R",
            "hand.L",
            "thigh.R",
            "thigh.L",
            "shin.R",
            "shin.L",
            "foot.R",
            "foot.L",
        ]

        for bone_name in bilateral_bones:
            bone_config = config.get_bone_config(bone_name)
            assert bone_config is not None

            if ".R" in bone_name:
                assert bone_config.opensim_name.endswith("_r")
            elif ".L" in bone_name:
                assert bone_config.opensim_name.endswith("_l")

    def test_all_masses_positive(self):
        """Test that all body masses are positive."""
        config = create_humanoid_config()

        for bone_name, bone_config in config.bones.items():
            assert bone_config.body_mass > 0, f"Bone {bone_name} has non-positive mass"

    def test_all_inertia_valid(self):
        """Test that all inertia tensors are valid."""
        config = create_humanoid_config()

        for bone_name, bone_config in config.bones.items():
            assert len(bone_config.body_inertia) == 6, f"Bone {bone_name} has wrong inertia length"
            # Check diagonal elements are positive
            assert bone_config.body_inertia[0] > 0, f"Bone {bone_name} has non-positive Ixx"
            assert bone_config.body_inertia[1] > 0, f"Bone {bone_name} has non-positive Iyy"
            assert bone_config.body_inertia[2] > 0, f"Bone {bone_name} has non-positive Izz"

    def test_marker_overrides_exist(self):
        """Test that marker overrides are configured."""
        config = create_humanoid_config()
        assert len(config.marker_config.overrides) > 0

    def test_marker_overrides_format(self):
        """Test that marker overrides follow naming convention."""
        config = create_humanoid_config()

        for blender_name, opensim_name in config.marker_config.overrides.items():
            # OpenSim marker names should have L_ or R_ prefix for bilateral markers
            if ".R" in blender_name:
                assert opensim_name.startswith("R_"), f"Right marker {opensim_name} should start with R_"
            elif ".L" in blender_name:
                assert opensim_name.startswith("L_"), f"Left marker {opensim_name} should start with L_"

    def test_configuration_validates(self):
        """Test that the humanoid configuration is valid."""
        config = create_humanoid_config()
        errors = config.validate()
        assert len(errors) == 0, f"Configuration has validation errors: {errors}"

    def test_reasonable_joint_limits(self):
        """Test that joint angle limits are reasonable."""
        config = create_humanoid_config()

        for bone_name, bone_config in config.bones.items():
            if bone_config.constraints.joint_type.value == "custom":
                for axis_name in ["x_axis", "y_axis", "z_axis"]:
                    axis = getattr(bone_config.constraints, axis_name)
                    if axis and not axis.locked:
                        # Joint limits should be within [-180, 180] range
                        assert -180 <= axis.min_angle <= 180, f"Bone {bone_name} {axis_name} min out of range"
                        assert -180 <= axis.max_angle <= 180, f"Bone {bone_name} {axis_name} max out of range"
                        # Range should be positive
                        assert axis.max_angle > axis.min_angle, f"Bone {bone_name} {axis_name} has invalid range"
