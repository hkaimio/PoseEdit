# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
from .blender.operators import PE_OT_CreateProject, PE_OT_LoadCameraViews, PE_OT_AssignTrack
from .ui.panels import PE_PT_ProjectPanel, PE_PT_StitchingPanel
from .blender.drivers import get_quality_driven_color_component
from .blender.properties import StitchingUIItem, StitchingUIState


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
    PE_PT_ProjectPanel,
    PE_PT_StitchingPanel,
    StitchingUIItem,
    StitchingUIState,
    PE_OT_AssignTrack,
]


def register():
    """Register the add-on."""
    for cls in _classes:
        bpy.utils.register_class(cls)

    # Register driver functions
    bpy.app.driver_namespace["get_quality_driven_color_component"] = get_quality_driven_color_component

    # Add the stitching UI state to the scene type
    bpy.types.Scene.pose_editor_stitching_ui = bpy.props.PointerProperty(type=StitchingUIState)


def unregister():
    """Unregister the add-on."""
    # Delete the scene property
    del bpy.types.Scene.pose_editor_stitching_ui

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    # Unregister driver functions
    if "get_quality_driven_color_component" in bpy.app.driver_namespace:
        del bpy.app.driver_namespace["get_quality_driven_color_component"]


if __name__ == "__main__":
    register()
