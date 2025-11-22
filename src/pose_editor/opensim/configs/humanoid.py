"""
Humanoid armature configuration for OpenSim export.

This configuration defines a basic humanoid skeleton suitable for
biomechanical simulation in OpenSim.
"""

from ..config import (
    ArmatureExportConfig,
    AxisConstraint,
    BoneConfig,
    JointConstraints,
    JointType,
)


def create_humanoid_config() -> ArmatureExportConfig:
    """
    Create configuration for humanoid armature export.

    This configuration includes:
    - Root (pelvis) with 6 DOF free joint
    - Spine with limited 3 DOF rotation
    - Upper limbs (shoulder, elbow, wrist) for both sides
    - Lower limbs (hip, knee, ankle) for both sides

    Returns:
        Configured ArmatureExportConfig for humanoid armature
    """
    config = ArmatureExportConfig()
    config.model_name = "HumanoidModel"

    # Root bone - use FREE joint (6 DOF)
    config.add_bone(
        BoneConfig(
            blender_name="pelvis",
            opensim_name="pelvis",
            constraints=JointConstraints(joint_type=JointType.FREE),
            body_mass=10.0,
            body_inertia=(0.1, 0.1, 0.1, 0.0, 0.0, 0.0),
        )
    )

    # Spine - limited rotation on all axes
    config.add_bone(
        BoneConfig(
            blender_name="spine",
            opensim_name="lumbar",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=30),
                y_axis=AxisConstraint(locked=False, min_angle=-45, max_angle=45),
                z_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=20),
            ),
            body_mass=8.0,
            body_inertia=(0.08, 0.08, 0.08, 0.0, 0.0, 0.0),
        )
    )

    # Chest/thorax
    config.add_bone(
        BoneConfig(
            blender_name="chest",
            opensim_name="thorax",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=20),
                y_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=30),
                z_axis=AxisConstraint(locked=False, min_angle=-15, max_angle=15),
            ),
            body_mass=15.0,
            body_inertia=(0.15, 0.15, 0.15, 0.0, 0.0, 0.0),
        )
    )

    # Neck
    config.add_bone(
        BoneConfig(
            blender_name="neck",
            opensim_name="neck",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-45, max_angle=45),
                y_axis=AxisConstraint(locked=False, min_angle=-60, max_angle=60),
                z_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=30),
            ),
            body_mass=2.0,
            body_inertia=(0.02, 0.02, 0.02, 0.0, 0.0, 0.0),
        )
    )

    # Head
    config.add_bone(
        BoneConfig(
            blender_name="head",
            opensim_name="head",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=30),
                y_axis=AxisConstraint(locked=False, min_angle=-45, max_angle=45),
                z_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=20),
            ),
            body_mass=5.0,
            body_inertia=(0.05, 0.05, 0.05, 0.0, 0.0, 0.0),
        )
    )

    # Right upper limb
    # Shoulder - ball joint (3 DOF)
    config.add_bone(
        BoneConfig(
            blender_name="upper_arm.R",
            opensim_name="humerus_r",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-180, max_angle=180),
                y_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=180),
                z_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=90),
            ),
            body_mass=3.0,
            body_inertia=(0.03, 0.03, 0.03, 0.0, 0.0, 0.0),
        )
    )

    # Elbow - hinge joint (1 DOF)
    config.add_bone(
        BoneConfig(
            blender_name="forearm.R",
            opensim_name="ulna_r",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=True),
                y_axis=AxisConstraint(locked=False, min_angle=0, max_angle=140),
                z_axis=AxisConstraint(locked=True),
            ),
            body_mass=1.5,
            body_inertia=(0.015, 0.015, 0.015, 0.0, 0.0, 0.0),
        )
    )

    # Wrist - limited 2 DOF
    config.add_bone(
        BoneConfig(
            blender_name="hand.R",
            opensim_name="hand_r",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-70, max_angle=70),
                y_axis=AxisConstraint(locked=True),
                z_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=30),
            ),
            body_mass=0.5,
            body_inertia=(0.005, 0.005, 0.005, 0.0, 0.0, 0.0),
        )
    )

    # Left upper limb (mirror of right)
    config.add_bone(
        BoneConfig(
            blender_name="upper_arm.L",
            opensim_name="humerus_l",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-180, max_angle=180),
                y_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=180),
                z_axis=AxisConstraint(locked=False, min_angle=-90, max_angle=90),
            ),
            body_mass=3.0,
            body_inertia=(0.03, 0.03, 0.03, 0.0, 0.0, 0.0),
        )
    )

    config.add_bone(
        BoneConfig(
            blender_name="forearm.L",
            opensim_name="ulna_l",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=True),
                y_axis=AxisConstraint(locked=False, min_angle=0, max_angle=140),
                z_axis=AxisConstraint(locked=True),
            ),
            body_mass=1.5,
            body_inertia=(0.015, 0.015, 0.015, 0.0, 0.0, 0.0),
        )
    )

    config.add_bone(
        BoneConfig(
            blender_name="hand.L",
            opensim_name="hand_l",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-70, max_angle=70),
                y_axis=AxisConstraint(locked=True),
                z_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=30),
            ),
            body_mass=0.5,
            body_inertia=(0.005, 0.005, 0.005, 0.0, 0.0, 0.0),
        )
    )

    # Right lower limb
    # Hip - ball joint (3 DOF)
    config.add_bone(
        BoneConfig(
            blender_name="thigh.R",
            opensim_name="femur_r",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-120, max_angle=120),
                y_axis=AxisConstraint(locked=False, min_angle=-45, max_angle=45),
                z_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=90),
            ),
            body_mass=10.0,
            body_inertia=(0.1, 0.1, 0.1, 0.0, 0.0, 0.0),
        )
    )

    # Knee - hinge joint (1 DOF)
    config.add_bone(
        BoneConfig(
            blender_name="shin.R",
            opensim_name="tibia_r",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=True),
                y_axis=AxisConstraint(locked=False, min_angle=-140, max_angle=0),
                z_axis=AxisConstraint(locked=True),
            ),
            body_mass=4.0,
            body_inertia=(0.04, 0.04, 0.04, 0.0, 0.0, 0.0),
        )
    )

    # Ankle - 2 DOF
    config.add_bone(
        BoneConfig(
            blender_name="foot.R",
            opensim_name="foot_r",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=50),
                y_axis=AxisConstraint(locked=True),
                z_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=20),
            ),
            body_mass=1.0,
            body_inertia=(0.01, 0.01, 0.01, 0.0, 0.0, 0.0),
        )
    )

    # Left lower limb (mirror of right)
    config.add_bone(
        BoneConfig(
            blender_name="thigh.L",
            opensim_name="femur_l",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-120, max_angle=120),
                y_axis=AxisConstraint(locked=False, min_angle=-45, max_angle=45),
                z_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=90),
            ),
            body_mass=10.0,
            body_inertia=(0.1, 0.1, 0.1, 0.0, 0.0, 0.0),
        )
    )

    config.add_bone(
        BoneConfig(
            blender_name="shin.L",
            opensim_name="tibia_l",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=True),
                y_axis=AxisConstraint(locked=False, min_angle=-140, max_angle=0),
                z_axis=AxisConstraint(locked=True),
            ),
            body_mass=4.0,
            body_inertia=(0.04, 0.04, 0.04, 0.0, 0.0, 0.0),
        )
    )

    config.add_bone(
        BoneConfig(
            blender_name="foot.L",
            opensim_name="foot_l",
            constraints=JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(locked=False, min_angle=-30, max_angle=50),
                y_axis=AxisConstraint(locked=True),
                z_axis=AxisConstraint(locked=False, min_angle=-20, max_angle=20),
            ),
            body_mass=1.0,
            body_inertia=(0.01, 0.01, 0.01, 0.0, 0.0, 0.0),
        )
    )

    # Marker name overrides
    config.marker_config.overrides = {
        "MRK-shoulder.R": "R_Shoulder",
        "MRK-shoulder.L": "L_Shoulder",
        "MRK-elbow.R": "R_Elbow",
        "MRK-elbow.L": "L_Elbow",
        "MRK-wrist.R": "R_Wrist",
        "MRK-wrist.L": "L_Wrist",
        "MRK-hip.R": "R_Hip",
        "MRK-hip.L": "L_Hip",
        "MRK-knee.R": "R_Knee",
        "MRK-knee.L": "L_Knee",
        "MRK-ankle.R": "R_Ankle",
        "MRK-ankle.L": "L_Ankle",
    }

    return config
