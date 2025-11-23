"""
Generate OpenSim export configuration from a Blender armature calibration animation.

This script analyzes an armature's animation (rotation quaternions) over a frame
range and computes per-bone maximum and minimum rotations around local axes.
It produces a Python configuration file (importable) that builds an
ArmatureExportConfig with per-axis constraints derived from the observed ranges.

Usage (inside Blender's Python environment / Text Editor):

from pose_editor.opensim.generate_config_from_animation import (
    generate_config_from_animation_file
)

generate_config_from_animation_file(
    armature_name="Armature",
    action_name=None,            # use object's active action if None
    frame_start=None,            # default from action or scene
    frame_end=None,
    euler_order='XYZ',
    output_path=None,            # path to write generated python config
    threshold_locked_deg=1.0,    # threshold to mark axis as locked
)

"""

import math
from math import degrees
from pathlib import Path

import bpy

from pose_editor.opensim.config import (
    ArmatureExportConfig,
    BoneConfig,
    JointConstraints,
    AxisConstraint,
    JointType,
)


def _unwrap_angles(prev, curr):
    """Unwrap angle list `curr` (degrees) relative to `prev` to avoid jumps over 360 deg.

    Both are lists of length 3. Returns adjusted curr list.
    """
    if prev is None:
        return curr
    out = curr.copy()
    for i in range(3):
        delta = out[i] - prev[i]
        while delta > 180:
            out[i] -= 360
            delta = out[i] - prev[i]
        while delta < -180:
            out[i] += 360
            delta = out[i] - prev[i]
    return out


def analyze_armature_rotation_ranges(
    armature_obj,
    action=None,
    frame_start=None,
    frame_end=None,
    euler_order='XYZ',
):
    """
    Analyze per-bone rotation ranges for an armature over the specified frame range.

    Returns a dict mapping bone_name -> dict with 'min', 'max' (lists of 3 deg),
    'translation_min', 'translation_max' (lists of 3 meters), and 'frames_sampled'.
    """
    scene = bpy.context.scene

    # choose action and frames
    if action is None and armature_obj.animation_data and armature_obj.animation_data.action:
        action = armature_obj.animation_data.action

    if action is not None:
        # If action provided as name
        if isinstance(action, str):
            action = bpy.data.actions.get(action)
        if action is None:
            raise ValueError("Action not found")

    if frame_start is None or frame_end is None:
        if action is not None and hasattr(action, 'frame_range'):
            af0, af1 = action.frame_range
            if frame_start is None:
                frame_start = int(math.floor(af0))
            if frame_end is None:
                frame_end = int(math.ceil(af1))
        else:
            if frame_start is None:
                frame_start = scene.frame_start
            if frame_end is None:
                frame_end = scene.frame_end

    pose_bones = armature_obj.pose.bones

    # Prepare storage
    data = {}
    for pb in pose_bones:
        data[pb.name] = {
            'min': [math.inf, math.inf, math.inf],
            'max': [-math.inf, -math.inf, -math.inf],
            'tmin': [math.inf, math.inf, math.inf],
            'tmax': [-math.inf, -math.inf, -math.inf],
            'prev_angles': None,
        }

    # Evaluate frames
    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        # sample each bone
        for pb in pose_bones:
            # compute local matrix relative to exported parent (immediate parent)
            if pb.parent:
                parent_mat = pb.parent.matrix
            else:
                parent_mat = armature_obj.matrix_world  # use armature origin for root

            local = parent_mat.inverted() @ pb.matrix

            # translation (meters)
            t = local.translation
            t_list = [t.x, t.y, t.z]
            for i in range(3):
                data[pb.name]['tmin'][i] = min(data[pb.name]['tmin'][i], t_list[i])
                data[pb.name]['tmax'][i] = max(data[pb.name]['tmax'][i], t_list[i])

            # rotation: take quaternion -> euler
            q = local.to_quaternion()
            e = q.to_euler(euler_order)
            angs = [degrees(e.x), degrees(e.y), degrees(e.z)]

            # unwrap relative to previous sample for this bone
            prev = data[pb.name]['prev_angles']
            angs_unwrapped = _unwrap_angles(prev, angs)
            data[pb.name]['prev_angles'] = angs_unwrapped

            for i in range(3):
                data[pb.name]['min'][i] = min(data[pb.name]['min'][i], angs_unwrapped[i])
                data[pb.name]['max'][i] = max(data[pb.name]['max'][i], angs_unwrapped[i])

    # Clean up prev_angles before returning
    for pb in pose_bones:
        data[pb.name].pop('prev_angles', None)

    return data, frame_start, frame_end


def generate_config_from_analysis(
    armature_name,
    analysis_data,
    frame_range,
    euler_order='XYZ',
    threshold_locked_deg=1.0,
    root_free_translation_threshold=1e-4,
):
    """
    Produce an ArmatureExportConfig object from analysis data.

    - If root bone translation range exceeds threshold, mark joint type FREE.
    - Otherwise produce CUSTOM joints with per-axis AxisConstraint based on min/max angles.
    """
    armature_obj = bpy.data.objects[armature_name]
    pose_bones = armature_obj.pose.bones

    config = ArmatureExportConfig()
    config.model_name = f"{armature_name}_generated"

    # choose root as bone with no parent in pose bones (first such)
    # better: find bones with no parent among all pose_bones
    root_candidates = [pb for pb in pose_bones if pb.parent is None]
    root_name = root_candidates[0].name if root_candidates else None

    for pb in pose_bones:
        d = analysis_data[pb.name]
        mins = d['min']
        maxs = d['max']

        # determine locked per axis
        axes = []
        for i in range(3):
            span = maxs[i] - mins[i]
            locked = abs(span) <= threshold_locked_deg
            # clamp min/max to reasonable range [-360,360]
            min_angle = max(-360.0, mins[i])
            max_angle = min(360.0, maxs[i])
            axes.append((locked, min_angle, max_angle))

        if pb.name == root_name:
            # check for translation activity
            tmin = d['tmin']
            tmax = d['tmax']
            tspan = [abs(tmax[i] - tmin[i]) for i in range(3)]
            if any(tv > root_free_translation_threshold for tv in tspan):
                constraints = JointConstraints(joint_type=JointType.FREE)
            else:
                constraints = JointConstraints(
                    joint_type=JointType.CUSTOM,
                    x_axis=AxisConstraint(
                        locked=axes[0][0],
                        min_angle=axes[0][1],
                        max_angle=axes[0][2],
                    ),
                    y_axis=AxisConstraint(
                        locked=axes[1][0],
                        min_angle=axes[1][1],
                        max_angle=axes[1][2],
                    ),
                    z_axis=AxisConstraint(
                        locked=axes[2][0],
                        min_angle=axes[2][1],
                        max_angle=axes[2][2],
                    ),
                )
        else:
            constraints = JointConstraints(
                joint_type=JointType.CUSTOM,
                x_axis=AxisConstraint(
                    locked=axes[0][0],
                    min_angle=axes[0][1],
                    max_angle=axes[0][2],
                ),
                y_axis=AxisConstraint(
                    locked=axes[1][0],
                    min_angle=axes[1][1],
                    max_angle=axes[1][2],
                ),
                z_axis=AxisConstraint(
                    locked=axes[2][0],
                    min_angle=axes[2][1],
                    max_angle=axes[2][2],
                ),
            )

        bone_cfg = BoneConfig(
            blender_name=pb.name,
            opensim_name=pb.name,
            constraints=constraints,
            export_body=True,
        )
        config.add_bone(bone_cfg)

    return config


def write_python_config_file(config: ArmatureExportConfig, output_path: str):
    """
    Write a Python file that constructs the given ArmatureExportConfig when imported.

    The generated file defines `create_generated_config()` which returns the config.
    """
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("from pose_editor.opensim.config import (\n")
    lines.append("    ArmatureExportConfig, BoneConfig, JointConstraints, AxisConstraint, JointType\n")
    lines.append(")\n\n\n")
    lines.append("def create_generated_config():\n")
    lines.append("    config = ArmatureExportConfig()\n")
    lines.append(f"    config.model_name = \"{config.model_name}\"\n\n")

    for bone_name, bone_cfg in config.bones.items():
        jc = bone_cfg.constraints
        if jc.joint_type == JointType.FREE:
            lines.append("    config.add_bone(BoneConfig(\n")
            lines.append(f"        blender_name=\"{bone_name}\", opensim_name=\"{bone_cfg.opensim_name}\",\n")
            lines.append("        constraints=JointConstraints(joint_type=JointType.FREE),\n")
            lines.append(f"        export_body={bone_cfg.export_body}\n")
            lines.append("    ))\n")
        else:
            xa = jc.x_axis
            ya = jc.y_axis
            za = jc.z_axis
            lines.append("    config.add_bone(BoneConfig(\n")
            lines.append(f"        blender_name=\"{bone_name}\",\n")
            lines.append(f"        opensim_name=\"{bone_cfg.opensim_name}\",\n")
            lines.append("        constraints=JointConstraints(\n")
            lines.append("            joint_type=JointType.CUSTOM,\n")

            # x axis
            lines.append("            x_axis=AxisConstraint(\n")
            lines.append(f"                locked={str(xa.locked)},\n")
            lines.append(f"                min_angle={xa.min_angle:.6f},\n")
            lines.append(f"                max_angle={xa.max_angle:.6f},\n")
            lines.append("            ),\n")

            # y axis
            lines.append("            y_axis=AxisConstraint(\n")
            lines.append(f"                locked={str(ya.locked)},\n")
            lines.append(f"                min_angle={ya.min_angle:.6f},\n")
            lines.append(f"                max_angle={ya.max_angle:.6f},\n")
            lines.append("            ),\n")

            # z axis
            lines.append("            z_axis=AxisConstraint(\n")
            lines.append(f"                locked={str(za.locked)},\n")
            lines.append(f"                min_angle={za.min_angle:.6f},\n")
            lines.append(f"                max_angle={za.max_angle:.6f},\n")
            lines.append("            ),\n")

            lines.append("        ),\n")
            lines.append(f"        export_body={bone_cfg.export_body}\n")
            lines.append("    ))\n\n")

    lines.append("    return config\n")

    p.write_text(''.join(lines))


def generate_config_from_animation_file(
    armature_name: str,
    action_name: str | None = None,
    frame_start: int | None = None,
    frame_end: int | None = None,
    euler_order: str = 'XYZ',
    output_path: str | None = None,
    threshold_locked_deg: float = 1.0,
    root_free_translation_threshold: float = 1e-4,
):
    """
    High-level entry point: analyze armature animation and write generated config file.
    """
    if armature_name not in bpy.data.objects:
        raise ValueError(f"Armature '{armature_name}' not found")

    armature_obj = bpy.data.objects[armature_name]

    action = action_name if action_name is None else bpy.data.actions.get(action_name)

    analysis, fs, fe = analyze_armature_rotation_ranges(
        armature_obj, action=action, frame_start=frame_start, frame_end=frame_end, euler_order=euler_order
    )

    config = generate_config_from_analysis(
        armature_name, analysis, (fs, fe), euler_order=euler_order, threshold_locked_deg=threshold_locked_deg,
        root_free_translation_threshold=root_free_translation_threshold,
    )

    if output_path is None:
        output_path = f"src/pose_editor/opensim/configs/generated_{armature_name}.py"

    write_python_config_file(config, output_path)
    print(f"Generated configuration written to: {output_path}")


# If run inside Blender's text editor as a script, you can call the function directly.
if __name__ == '__main__':
    # Example: adjust these names to your scene
    generate_config_from_animation_file(armature_name='Armature')
