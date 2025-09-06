# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
from . import scene_builder

class PE_OT_CreateProject(bpy.types.Operator):
    """Creates the basic scene structure for the project."""
    bl_idname = "pose_editor.create_project"
    bl_label = "Create New Project"

    def execute(self, context):
        scene_builder.create_project_structure()
        return {'FINISHED'}