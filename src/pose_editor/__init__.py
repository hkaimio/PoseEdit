# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
from .blender.operators import PE_OT_CreateProject
from .ui.panels import PE_PT_ProjectPanel

bl_info = {
    "name": "Pose Editor",
    "author": "Harri Kaimio",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Pose Editor",
    "description": "A collection of tools for editing motion capture data.",
    "warning": "",
    "doc_url": "",
    "category": "Animation",
}

class PE_OT_dummy(bpy.types.Operator):
    """A dummy operator to verify installation."""
    bl_idname = "pose_editor.dummy"
    bl_label = "Pose Editor Dummy Operator"

    def execute(self, context):
        print("Pose Editor dummy operator executed.")
        return {'FINISHED'}

_classes = [
    PE_OT_dummy,
    PE_OT_CreateProject,
    PE_PT_ProjectPanel,
]

def register():
    """Register the add-on."""
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    """Unregister the add-on."""
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()