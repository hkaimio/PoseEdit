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

    layout = self.layout
        layout.operator("pose_editor.create_project")
        layout.operator("pose_editor.load_camera_views")


class PE_PT_StitchingPanel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport sidebar for 2D Stitching."""

    bl_label = "2D Identity Stitching"
    bl_idname = "PE_PT_StitchingPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pose Editor"
    bl_parent_id = "PE_PT_ProjectPanel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        # Only show the panel if we are in a 3D view with a camera
        return context.space_data.camera

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        stitching_ui_state = scene.pose_editor_stitching_ui

        # Get the active camera view
        active_camera = context.space_data.camera
        # TODO: Find the associated CameraView object from the camera
        # For now, we assume a naming convention
        if not active_camera.name.startswith("Cam_"):
            layout.label(text="Active camera is not a Camera View")
            return
        
        view_name = active_camera.name.replace("Cam_", "")
        layout.label(text=f"Active View: {view_name}")

        # --- Find Real Persons and Raw Tracks ---
        from ..core import person_facade
        from ..blender import dal

        real_person_refs = dal.find_all_objects_by_property(person_facade.IS_REAL_PERSON_INSTANCE, True)
        
        # TODO: Find raw tracks for the current view
        # This is a placeholder
        raw_tracks = [("-1", "-- Select --", ""), ("0", "Person 0", ""), ("1", "Person 1", "")]

        # --- Synchronize UI state with scene data ---
        # Get current persons in the UI
        ui_person_names = {item.person_name for item in stitching_ui_state.items}
        # Get current persons in the scene
        scene_person_names = {ref.name for ref in real_person_refs}

        # Remove persons from UI that are no longer in the scene
        if ui_person_names - scene_person_names:
            for i in range(len(stitching_ui_state.items) - 1, -1, -1):
                if stitching_ui_state.items[i].person_name not in scene_person_names:
                    stitching_ui_state.items.remove(i)
        
        # Add new persons from the scene to the UI
        for name in scene_person_names - ui_person_names:
            item = stitching_ui_state.items.add()
            item.person_name = name

        # --- Draw UI --- 
        if not stitching_ui_state.items:
            layout.label(text="No Real Persons created yet.")
            # TODO: Add an "Add Real Person" button here
            return

        box = layout.box()
        for item in stitching_ui_state.items:
            row = box.row()
            row.label(text=item.person_name)
            # This is where the dynamic EnumProperty would be updated and drawn
            # For now, we just show a placeholder
            row.prop(item, "selected_track", text="")

        layout.operator("pose_editor.assign_track", text="Assign Source at Current Frame")
        layout.operator("pose_editor.load_camera_views")
