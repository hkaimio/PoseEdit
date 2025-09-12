# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy


class PE_PT_ProjectPanel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport sidebar."""

    bl_label = "Pose Editor"
    bl_idname = "PE_PT_ProjectPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pose Editor"

    def draw(self, context):
        layout = self.layout
        layout.operator("pose_editor.create_project")
        layout.operator("pose_editor.load_camera_views")
