# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
from . import scene_builder
import os
from pathlib import Path
import math

from ..core.camera_view import create_camera_view, BLENDER_TARGET_WIDTH
from ..core.skeleton import COCO133Skeleton
from ..pose2sim.skeletons import COCO_133


class PE_OT_CreateProject(bpy.types.Operator):
    """Creates the basic scene structure for the project."""

    bl_idname = "pose_editor.create_project"
    bl_label = "Create New Project"

    def execute(self, context):
        scene_builder.create_project_structure()
        return {"FINISHED"}


class PE_OT_LoadCameraViews(bpy.types.Operator):
    """Loads camera views from a selected directory."""

    bl_idname = "pose_editor.load_camera_views"
    bl_label = "Load Camera Views"
    bl_description = "Select a directory to load camera views from"

    directory: bpy.props.StringProperty(
        name="Path",
        subtype='DIR_PATH',
    )

    def execute(self, context):
        base_dir = Path(self.directory)
        videos_dir = base_dir / "videos"
        
        pose_dir = base_dir / "pose-associated"
        if not pose_dir.is_dir():
            pose_dir = base_dir / "pose"
        
        if not videos_dir.is_dir() or not pose_dir.is_dir():
            self.report({'ERROR'}, "Videos or pose directory not found.")
            return {'CANCELLED'}

        video_files = [f for f in os.listdir(videos_dir) if f.endswith((".mp4", ".avi", ".mov"))]
        
        camera_views = []
        for video_file in video_files:
            camera_name = Path(video_file).stem
            json_dir = pose_dir / f"{camera_name}_json"
            
            if json_dir.is_dir():
                # For now, we'll hardcode the COCO-133 skeleton.
                # This should be a user choice later.
                skeleton_def = COCO_133
                skeleton = COCO133Skeleton(skeleton_def)

                view = create_camera_view(
                    name=camera_name,
                    video_file=videos_dir / video_file,
                    pose_data_dir=json_dir,
                    skeleton_obj=skeleton
                )
                camera_views.append(view)
            else:
                print(f"Warning: No matching JSON folder found for video {video_file}")

        self._arrange_views_in_grid(camera_views)

        self.report({'INFO'}, f"Loaded {len(camera_views)} camera views.")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def _arrange_views_in_grid(self, views: list):
        """Arranges the camera view root objects in a grid."""
        if not views:
            return

        from ..blender import dal

        count = len(views)
        if count == 0:
            return
            
        cols = math.ceil(math.sqrt(count))
        
        # A bit of padding between views
        padding = 2.0
        view_width = dal.BLENDER_TARGET_WIDTH + padding

        for i, view in enumerate(views):
            row = i // cols
            col = i % cols
            
            x = col * view_width
            y = -row * view_width # Place rows downwards in Y
            
            view_obj = view._obj._get_obj()
            if view_obj:
                view_obj.location = (x, y, 0)


class PE_OT_AssignTrack(bpy.types.Operator):
    """Assigns a raw track as the source for a Real Person segment."""

    bl_idname = "pose_editor.assign_track"
    bl_label = "Assign Raw Track"
    bl_description = "Assign the selected raw track to the person instance from the current frame onwards"

    def execute(self, context):
        self.report({'INFO'}, "Stitching not yet implemented.")
        return {'CANCELLED'}
