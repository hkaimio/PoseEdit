# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import math
import os
from pathlib import Path

import bpy

from ..core.camera_view import (
    BLENDER_TARGET_WIDTH,
    BRIGHT_COLORS,
    CameraView,
    create_camera_view,
)
from ..core.marker_data import MarkerData
from ..core.person_data_view import PersonDataView
from ..core.person_facade import (
    IS_REAL_PERSON_INSTANCE,
    PERSON_DEFINITION_ID,
    RealPersonInstanceFacade,
)
from ..core.skeleton import COCO133Skeleton
from ..pose2sim.skeletons import COCO_133
from . import dal, scene_builder


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
        subtype="DIR_PATH",
    )

    def execute(self, context):
        base_dir = Path(self.directory)
        videos_dir = base_dir / "videos"

        pose_dir = base_dir / "pose-associated"
        if not pose_dir.is_dir():
            pose_dir = base_dir / "pose"

        if not videos_dir.is_dir() or not pose_dir.is_dir():
            self.report({"ERROR"}, "Videos or pose directory not found.")
            return {"CANCELLED"}

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
                    name=camera_name, video_file=videos_dir / video_file, pose_data_dir=json_dir, skeleton_obj=skeleton
                )
                camera_views.append(view)
            else:
                print(f"Warning: No matching JSON folder found for video {video_file}")

        self._arrange_views_in_grid(camera_views)

        self.report({"INFO"}, f"Loaded {len(camera_views)} camera views.")
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def _arrange_views_in_grid(self, views: list):
        """Arranges the camera view root objects in a grid."""
        if not views:
            return


        count = len(views)
        if count == 0:
            return

        cols = math.ceil(math.sqrt(count))

        # A bit of padding between views
        padding = 2.0
        view_width = BLENDER_TARGET_WIDTH + padding

        for i, view in enumerate(views):
            row = i // cols
            col = i % cols

            x = col * view_width
            y = -row * view_width  # Place rows downwards in Y

            view_obj = view._obj._get_obj()
            if view_obj:
                view_obj.location = (x, y, 0)


class PE_OT_AddPersonInstance(bpy.types.Operator):
    """Adds a new Real Person Instance to the scene."""

    bl_idname = "pose_editor.add_person_instance"
    bl_label = "Add Real Person"
    bl_description = "Adds a new Real Person Instance to the scene for stitching."

    person_name: bpy.props.StringProperty(
        name="Person Name", description="Name for the new Real Person Instance", default="New Person"
    )

    def execute(self, context):
        if not self.person_name:
            self.report({"ERROR"}, "Person name cannot be empty.")
            return {"CANCELLED"}

        # Check if a person with this name already exists
        existing_person = dal.get_object_by_name(self.person_name)
        if existing_person and dal.get_custom_property(
            existing_person, IS_REAL_PERSON_INSTANCE
        ):
            self.report({"ERROR"}, f"A Real Person named '{self.person_name}' already exists.")
            return {"CANCELLED"}

        # Create the master Empty object for the RealPersonInstance
        person_obj_ref = dal.get_or_create_object(
            name=self.person_name,
            obj_type="EMPTY",
            collection_name="RealPersons",  # Assuming a collection for RealPersons
        )

        # Set custom properties to identify it as a RealPersonInstance
        dal.set_custom_property(person_obj_ref, IS_REAL_PERSON_INSTANCE, True)
        dal.set_custom_property(
            person_obj_ref, PERSON_DEFINITION_ID, self.person_name
        )  # For now, name is also definition ID

        # Add this person to the UI state collection
        self._update_ui_state(context)

        # --- Create MarkerData and PersonDataView for the Real Person in each CameraView ---
        # Find all existing CameraView root objects
        camera_views = CameraView.get_all()

        # For now, hardcode skeleton. In future, this should be from PersonDefinition.
        skeleton_def = COCO_133
        skeleton = COCO133Skeleton(skeleton_def)

        for i, cam_view in enumerate(camera_views):
            cam_view_name = dal.get_custom_property(cam_view._obj, dal.SERIES_NAME)

            # Determine color for this Real Person's view
            color = BRIGHT_COLORS[i % len(BRIGHT_COLORS)]

            # Create MarkerData for the Real Person in this view
            real_person_md_name = f"{person_obj_ref.name}.{cam_view_name}"
            real_person_md = MarkerData.create_new(real_person_md_name, skeleton._skeleton.name)

            # Create PersonDataView for the Real Person in this view
            real_person_pv_name = f"PV.{person_obj_ref.name}.{cam_view_name}"
            real_person_pv = PersonDataView.create_new(
                view_name=real_person_pv_name,
                skeleton=skeleton,
                color=color,
                camera_view=cam_view,
                collection=None,
            )

            # Link PersonDataView to MarkerData
            real_person_pv.connect_to_series(real_person_md)

            # Position the Real Person's PersonDataView relative to the CameraView
            # Offset it to the right of the raw tracks
            offset_x = BLENDER_TARGET_WIDTH + 1.0  # Offset by width + some padding
            real_person_pv.view_root_object._get_obj().location.x += offset_x

        self.report({"INFO"}, f"Real Person '{self.person_name}' added.")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def _update_ui_state(self, context):
        """Adds the new person to the UI state collection."""
        stitching_ui_state = context.scene.pose_editor_stitching_ui
        item = stitching_ui_state.items.add()
        item.person_name = self.person_name


class PE_OT_AssignTrack(bpy.types.Operator):
    """Assigns a raw track as the source for a Real Person segment."""

    bl_idname = "pose_editor.assign_track"
    bl_label = "Assign Raw Track"
    bl_description = "Assign the selected raw track to the person instance from the current frame onwards"

    def execute(self, context):
        from ..blender import dal
        from ..core.person_facade import RealPersonInstanceFacade

        start_frame = context.scene.frame_current
        stitching_ui_state = context.scene.pose_editor_stitching_ui

        # Get active view
        active_camera = context.space_data.camera
        if not active_camera or not active_camera.name.startswith("Cam_"):
            self.report({"ERROR"}, "No active camera view found.")
            return {"CANCELLED"}
        view_name = active_camera.name.replace("Cam_", "")
        pvd_name = f"DS.{view_name}"


        # TODO: This is a temporary way to get a skeleton. This should
        # be retrieved from the RealPersonInstance in the future.
        skeleton_def = COCO_133
        skeleton = COCO133Skeleton(skeleton_def)

        for item in stitching_ui_state.items:
            person_ref = dal.get_object_by_name(item.person_name)
            if not person_ref:
                continue

            facade = RealPersonInstanceFacade(person_ref)

            current_track_index = facade.get_active_track_index_at_frame(view_name, start_frame)
            selected_track_index = int(item.selected_track)

            if selected_track_index != -1 and selected_track_index != current_track_index:
                print(f"Assigning track {selected_track_index} to {item.person_name} at frame {start_frame}")
                facade.assign_source_track_for_segment(
                    view_name=view_name,
                    source_track_index=selected_track_index,
                    start_frame=start_frame,
                    skeleton=skeleton,
                )

        self.report({"INFO"}, f"Stitching applied at frame {start_frame}.")
        return {"FINISHED"}
