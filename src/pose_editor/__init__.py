# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy

from .blender.drivers import register_drivers, unregister_drivers
from .blender.operators import (
    PE_OT_AddPersonInstance,
    PE_OT_AssignTrack,
    PE_OT_CreateProject,
    PE_OT_LoadCameraViews,
    PE_OT_LoadCalibration,
    PE_OT_TriangulatePerson,
)
from .blender.properties import CameraViewSettings, StitchingUIItem, StitchingUIState
from .ui.panels import (
    PE_PT_3DPipelinePanel,
    PE_PT_ProjectPanel,
    PE_PT_StitchingPanel,
    PE_PT_ViewPanel,
)


class PE_OT_dummy(bpy.types.Operator):
    """A dummy operator to verify installation."""

    bl_idname = "pose_editor.dummy"
    bl_label = "Pose Editor Dummy Operator"

    def execute(self, context):
        print("Pose Editor dummy operator executed.")
        return {"FINISHED"}


_classes = [
    PE_OT_dummy,
    PE_OT_CreateProject,
    PE_OT_LoadCameraViews,
    PE_OT_LoadCalibration,
    PE_OT_AddPersonInstance,
    PE_OT_AssignTrack,
    PE_OT_TriangulatePerson,
    PE_PT_ProjectPanel,
    PE_PT_ViewPanel,
    PE_PT_StitchingPanel,
    PE_PT_3DPipelinePanel,
    StitchingUIItem,
    StitchingUIState,
    CameraViewSettings,
]


def on_load_post(dummy):
    """Handler for file load."""
    register_drivers()


def register():
    """Register the add-on."""
    for cls in _classes:
        bpy.utils.register_class(cls)

    # Register driver functions
    register_drivers()

    # Add handler for loading new files
    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)

    # Add the property groups to the scene type
    bpy.types.Scene.pose_editor_stitching_ui = bpy.props.PointerProperty(
        type=StitchingUIState
    )
    bpy.types.Scene.pose_editor_view_settings = bpy.props.PointerProperty(
        type=CameraViewSettings
    )


def unregister():
    """Unregister the add-on."""
    # Delete the scene properties
    del bpy.types.Scene.pose_editor_stitching_ui
    del bpy.types.Scene.pose_editor_view_settings

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    # Unregister driver functions
    unregister_drivers()

    # Remove the handler
    if on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load_post)


if __name__ == "__main__":
    register()