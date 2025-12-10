"""Operators for enabling/disabling marker bones and body parts."""

import bpy
from bpy.props import IntProperty, BoolProperty
from bpy.types import Operator

from ..blender import dal


class POSE_EDITOR_OT_set_marker_enable(Operator):
    """Enable or disable a marker bone for a specified number of frames."""

    bl_idname = "pose_editor.set_marker_enable"
    bl_label = "Set Marker Enable"
    bl_description = "Enable or disable marker bone"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties
    bone_name: bpy.props.StringProperty(
        name="Bone Name",
        description="Name of the bone to modify",
        default=""
    )

    enable: BoolProperty(
        name="Enable",
        description="Enable or disable the marker",
        default=True
    )

    num_frames: IntProperty(
        name="Number of Frames",
        description="Number of frames to apply the setting",
        default=5,
        min=1
    )

    @classmethod
    def poll(cls, context):
        """Check if operator can be executed."""
        return (
            context.active_object and
            context.active_object.type == 'ARMATURE' and
            context.mode == 'POSE' and
            context.active_pose_bone
        )

    def execute(self, context):
        """Execute the enable/disable operation."""
        try:
            armature_obj = context.active_object
            bone_name = self.bone_name or context.active_pose_bone.name

            pose_bone = armature_obj.pose.bones.get(bone_name)
            if not pose_bone:
                self.report({'ERROR'}, f"Bone '{bone_name}' not found")
                return {'CANCELLED'}

            # Get current frame
            current_frame = context.scene.frame_current
            end_frame = current_frame + self.num_frames

            # Get or create armature action
            if not armature_obj.animation_data:
                armature_obj.animation_data_create()
            if not armature_obj.animation_data.action:
                action = bpy.data.actions.new(name=f"{armature_obj.name}Action")
                armature_obj.animation_data.action = action
            else:
                action = armature_obj.animation_data.action

            # Set value on the bone
            enable_value = 1.0 if self.enable else 0.0
            pose_bone["enable"] = enable_value

            # Create keyframes using Blender 5.0 action slot system
            data_path = f'pose.bones["{bone_name}"]["enable"]'
            fcurve = dal.get_or_create_fcurve(
                action, armature_obj.name, data_path, -1
            )

            # Ensure there's a keyframe at frame 1 if no earlier keyframes exist
            if current_frame > 1:
                has_earlier_keyframe = any(kp.co[0] < current_frame for kp in fcurve.keyframe_points)
                if not has_earlier_keyframe:
                    kp = fcurve.keyframe_points.insert(1.0, 1.0)  # Default to enabled at start
                    kp.interpolation = "CONSTANT"

            # Store current values at start and end of range (as booleans)
            start_value = 1.0 if fcurve.evaluate(float(current_frame)) > 0.5 else 0.0
            end_value = 1.0 if fcurve.evaluate(float(end_frame)) > 0.5 else 0.0

            # Remove any keyframes from start_frame to end_frame-1 (inclusive)
            for kp in reversed(fcurve.keyframe_points):
                if current_frame <= kp.co[0] <= end_frame - 1:
                    fcurve.keyframe_points.remove(kp)

            # If start_value != enable_value, set keyframe at start_frame
            if start_value != enable_value:
                kp = fcurve.keyframe_points.insert(float(current_frame), enable_value)
                kp.interpolation = "CONSTANT"

            # If end_value != enable_value, set keyframe at end_frame
            if end_value != enable_value:
                kp = fcurve.keyframe_points.insert(float(end_frame), end_value)
                kp.interpolation = "CONSTANT"

            fcurve.update()

            action_text = "Enabled" if self.enable else "Disabled"
            self.report(
                {'INFO'},
                f"{action_text} '{bone_name}' for {self.num_frames} frames"
            )
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to set marker enable: {str(e)}")
            return {'CANCELLED'}


class POSE_EDITOR_OT_set_body_part_enable(Operator):
    """Enable or disable an entire body part for a specified number of frames."""

    bl_idname = "pose_editor.set_body_part_enable"
    bl_label = "Set Body Part Enable"
    bl_description = "Enable or disable entire body part"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties
    body_part_name: bpy.props.StringProperty(
        name="Body Part Name",
        description="Name of the body part to modify",
        default=""
    )

    enable: BoolProperty(
        name="Enable",
        description="Enable or disable the body part",
        default=True
    )

    num_frames: IntProperty(
        name="Number of Frames",
        description="Number of frames to apply the setting",
        default=5,
        min=1
    )

    @classmethod
    def poll(cls, context):
        """Check if operator can be executed."""
        return (
            context.active_object and
            context.active_object.type == 'ARMATURE' and
            context.mode == 'POSE' and
            context.active_pose_bone
        )

    def execute(self, context):
        """Execute the enable/disable operation."""
        try:
            armature_obj = context.active_object

            # Get body part name from active bone if not specified
            if not self.body_part_name:
                active_bone = context.active_pose_bone
                body_part = active_bone.bone.get(dal.BODY_PART._prop_name)
                if not body_part:
                    self.report({'ERROR'}, "Active bone has no body part defined")
                    return {'CANCELLED'}
                self.body_part_name = body_part

            # Find control bone for this body part
            # Control bones have body part enable properties (usually "CTRL-enable")
            ctrl_bone = None
            body_part_prop = f"enable_{self.body_part_name.lower().replace(' ', '_')}"

            for pose_bone in armature_obj.pose.bones:
                if body_part_prop in pose_bone:
                    ctrl_bone = pose_bone
                    break

            if not ctrl_bone:
                self.report(
                    {'ERROR'},
                    f"Control bone with property '{body_part_prop}' not found"
                )
                return {'CANCELLED'}

            # Get current frame
            current_frame = context.scene.frame_current
            end_frame = current_frame + self.num_frames

            # Get or create armature action
            if not armature_obj.animation_data:
                armature_obj.animation_data_create()
            if not armature_obj.animation_data.action:
                action = bpy.data.actions.new(name=f"{armature_obj.name}Action")
                armature_obj.animation_data.action = action
            else:
                action = armature_obj.animation_data.action

            # Set value on the control bone
            enable_value = 1.0 if self.enable else 0.0
            ctrl_bone[body_part_prop] = enable_value

            # Create keyframes using Blender 5.0 action slot system
            data_path = f'pose.bones["{ctrl_bone.name}"]["{body_part_prop}"]'
            fcurve = dal.get_or_create_fcurve(
                action, armature_obj.name, data_path, -1
            )

            # Ensure there's a keyframe at frame 1 if no earlier keyframes exist
            if current_frame > 1:
                has_earlier_keyframe = any(kp.co[0] < current_frame for kp in fcurve.keyframe_points)
                if not has_earlier_keyframe:
                    kp = fcurve.keyframe_points.insert(1.0, 1.0)  # Default to enabled at start
                    kp.interpolation = "CONSTANT"

            # Store current values at start and end of range (as booleans)
            start_value = 1.0 if fcurve.evaluate(float(current_frame)) > 0.5 else 0.0
            end_value = 1.0 if fcurve.evaluate(float(end_frame)) > 0.5 else 0.0

            # Remove any keyframes from start_frame to end_frame-1 (inclusive)
            for kp in reversed(fcurve.keyframe_points):
                if current_frame <= kp.co[0] <= end_frame - 1:
                    fcurve.keyframe_points.remove(kp)

            # If start_value != enable_value, set keyframe at start_frame
            if start_value != enable_value:
                kp = fcurve.keyframe_points.insert(float(current_frame), enable_value)
                kp.interpolation = "CONSTANT"

            # If end_value != enable_value, set keyframe at end_frame
            if end_value != enable_value:
                kp = fcurve.keyframe_points.insert(float(end_frame), end_value)
                kp.interpolation = "CONSTANT"

            fcurve.update()

            action_text = "Enabled" if self.enable else "Disabled"
            self.report(
                {'INFO'},
                f"{action_text} body part '{self.body_part_name}' for {self.num_frames} frames"
            )
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to set body part enable: {str(e)}")
            return {'CANCELLED'}


class VIEW3D_MT_pose_context_menu_marker(bpy.types.Menu):
    """Context menu for marker bones."""

    bl_label = "Marker"
    bl_idname = "VIEW3D_MT_pose_context_menu_marker"

    def draw(self, context):
        layout = self.layout
        active_bone = context.active_pose_bone

        if active_bone:
            bone_name = active_bone.name

            # Submenu for individual marker
            layout.label(text=f"Marker: {bone_name}")
            layout.separator()

            # Enable options
            op = layout.operator(
                "pose_editor.set_marker_enable",
                text="Enable for 5 Frames"
            )
            op.bone_name = bone_name
            op.enable = True
            op.num_frames = 5

            op = layout.operator(
                "pose_editor.set_marker_enable",
                text="Enable for 10 Frames"
            )
            op.bone_name = bone_name
            op.enable = True
            op.num_frames = 10

            layout.separator()

            # Disable options
            op = layout.operator(
                "pose_editor.set_marker_enable",
                text="Disable for 5 Frames"
            )
            op.bone_name = bone_name
            op.enable = False
            op.num_frames = 5

            op = layout.operator(
                "pose_editor.set_marker_enable",
                text="Disable for 10 Frames"
            )
            op.bone_name = bone_name
            op.enable = False
            op.num_frames = 10


class VIEW3D_MT_pose_context_menu_body_part(bpy.types.Menu):
    """Context menu for body part enable/disable."""

    bl_label = "Body Part"
    bl_idname = "VIEW3D_MT_pose_context_menu_body_part"

    def draw(self, context):
        layout = self.layout
        active_bone = context.active_pose_bone

        if active_bone:
            body_part = active_bone.bone.get(dal.BODY_PART._prop_name)
            if body_part:
                layout.label(text=f"Body Part: {body_part}")
                layout.separator()

                # Enable options
                op = layout.operator(
                    "pose_editor.set_body_part_enable",
                    text="Enable for 5 Frames"
                )
                op.body_part_name = body_part
                op.enable = True
                op.num_frames = 5

                op = layout.operator(
                    "pose_editor.set_body_part_enable",
                    text="Enable for 10 Frames"
                )
                op.body_part_name = body_part
                op.enable = True
                op.num_frames = 10

                layout.separator()

                # Disable options
                op = layout.operator(
                    "pose_editor.set_body_part_enable",
                    text="Disable for 5 Frames"
                )
                op.body_part_name = body_part
                op.enable = False
                op.num_frames = 5

                op = layout.operator(
                    "pose_editor.set_body_part_enable",
                    text="Disable for 10 Frames"
                )
                op.body_part_name = body_part
                op.enable = False
                op.num_frames = 10
            else:
                layout.label(text="No body part defined")


def draw_pose_context_menu(self, context):
    """Add custom menu entries to pose mode context menu."""
    layout = self.layout

    # Only show for marker bones (those with MARKER_ROLE property)
    if context.active_pose_bone:
        active_bone = context.active_pose_bone
        marker_role = active_bone.bone.get(dal.MARKER_ROLE._prop_name)

        if marker_role:
            layout.separator()
            layout.menu("VIEW3D_MT_pose_context_menu_marker")
            layout.menu("VIEW3D_MT_pose_context_menu_body_part")


# Registration
classes = (
    POSE_EDITOR_OT_set_marker_enable,
    POSE_EDITOR_OT_set_body_part_enable,
    VIEW3D_MT_pose_context_menu_marker,
    VIEW3D_MT_pose_context_menu_body_part,
)


def register():
    """Register operators and menus."""
    for cls in classes:
        bpy.utils.register_class(cls)

    # Add to pose mode context menu
    bpy.types.VIEW3D_MT_pose_context_menu.append(draw_pose_context_menu)


def unregister():
    """Unregister operators and menus."""
    # Remove from pose mode context menu
    bpy.types.VIEW3D_MT_pose_context_menu.remove(draw_pose_context_menu)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
