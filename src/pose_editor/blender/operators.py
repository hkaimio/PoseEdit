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
from ..core.calibration import Calibration, load_calibration_from_file
from ..core.marker_data import MarkerData
from ..core.person_data_view import PersonDataView
from ..core.person_facade import (
    IS_REAL_PERSON_INSTANCE,
    PERSON_DEFINITION_ID,
    RealPersonInstanceFacade,
)
from ..core.skeleton import COCO133Skeleton
from . import dal, scene_builder


class PE_OT_CreateProject(bpy.types.Operator):
    """Creates the basic scene structure for the project."""

    bl_idname = "pose_editor.create_project"
    bl_label = "Create New Project"

    def execute(self, context):
        scene_builder.create_project_structure()
        return {"FINISHED"}


class PE_OT_LoadCalibration(bpy.types.Operator):
    """Loads camera calibration data from a TOML file."""

    bl_idname = "pose_editor.load_calibration"
    bl_label = "Load Calibration File"
    bl_description = "Select the camera calibration TOML file"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        try:
            load_calibration_from_file(self.filepath)
            self.report({"INFO"}, f"Loaded calibration from {self.filepath}")
        except Exception as e:
            self.report({"ERROR"}, f"Failed to load calibration: {e}")
            return {"CANCELLED"}
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


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

        # Get calibration data to find matching names
        calibration = Calibration()
        calib_cam_names = calibration.get_camera_names()

        camera_views = []
        for video_file in video_files:
            camera_name_short = Path(video_file).stem
            json_dir = pose_dir / f"{camera_name_short}_json"

            # Find the corresponding full name in calibration data
            calib_cam_name_full = None
            for name in calib_cam_names:
                # A bit fuzzy matching, but should work for "int_cam1_img" vs "cam1"
                if f"_{camera_name_short}_" in name or name == f"int_{camera_name_short}_img":
                    calib_cam_name_full = name
                    break

            if not calib_cam_name_full:
                self.report({"WARNING"}, f"No matching calibration data found for camera '{camera_name_short}'")
                continue

            if json_dir.is_dir():
                # For now, we'll hardcode the COCO-133 skeleton.
                # This should be a user choice later.
                skeleton = COCO133Skeleton()

                view = create_camera_view(
                    name=camera_name_short,
                    video_file=videos_dir / video_file,
                    pose_data_dir=json_dir,
                    skeleton_obj=skeleton,
                )
                # Store the full calibration name on the view object
                dal.set_custom_property(view._obj, dal.CALIBRATION_CAMERA_NAME, calib_cam_name_full)
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
        existing_persons = RealPersonInstanceFacade.get_all()
        for person in existing_persons:
            if person.name == self.person_name:
                self.report({"ERROR"}, f"A Real Person named '{self.person_name}' already exists.")
                return {"CANCELLED"}

        # Create the master Empty object for the RealPersonInstance using the facade
        person_facade = RealPersonInstanceFacade.create_new(self.person_name)
        person_obj_ref = person_facade.obj

        # Add this person to the UI state collection
        self._update_ui_state(context)

        # --- Create MarkerData and PersonDataView for the Real Person in each CameraView ---
        # Find all existing CameraView root objects
        camera_views = CameraView.get_all()

        # For now, hardcode skeleton. In future, this should be from PersonDefinition.
        skeleton = COCO133Skeleton()

        for i, cam_view in enumerate(camera_views):
            cam_view_name = dal.get_custom_property(cam_view._obj, dal.SERIES_NAME)

            # Determine color for this Real Person's view
            color = BRIGHT_COLORS[i % len(BRIGHT_COLORS)]

            # Create MarkerData for the Real Person in this view
            real_person_md_name = f"{person_obj_ref.name}.{cam_view_name}"
            real_person_md = MarkerData.create_new(real_person_md_name, skeleton.name, cam_view, person_facade)

            # Create PersonDataView for the Real Person in this view
            real_person_pv_name = f"PV.{person_obj_ref.name}.{cam_view_name}"
            real_person_pv = PersonDataView.create_new(
                view_name=real_person_pv_name,
                skeleton=skeleton,
                color=color,
                camera_view=cam_view,
                collection=None,
                person=person_facade,
            )

            # Link PersonDataView to MarkerData
            real_person_pv.connect_to_series(real_person_md)

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
        from ..core.person_data_view import PersonDataView

        start_frame = context.scene.frame_current
        stitching_ui_state = context.scene.pose_editor_stitching_ui

        # Get active view
        active_camera = context.space_data.camera
        if not active_camera or not active_camera.name.startswith("Cam_"):
            self.report({"ERROR"}, "No active camera view found.")
            return {"CANCELLED"}
        view_name = "View_" + active_camera.name.replace("Cam_", "")

        persons = {person.name: person for person in RealPersonInstanceFacade.get_all()}
        all_pdvs = PersonDataView.get_all()
        pdvs_by_person_and_view = {}
        for pdv in all_pdvs:
            person = pdv.get_person()
            cam_view = pdv.get_camera_view()
            if person and cam_view and cam_view._obj.name == view_name:
                pdvs_by_person_and_view[person.name] = pdv

        for item in stitching_ui_state.items:
            facade = persons.get(item.person_name)
            if not facade:
                continue

            pdv = pdvs_by_person_and_view.get(facade.name)
            if not pdv:
                continue

            selected_track_index = int(item.selected_track)

            # Get current requested id to avoid redundant updates
            marker_data = pdv.get_data_series()
            if not marker_data:
                continue

            req_fcurve = dal.get_fcurve_on_object(marker_data._obj, '["requested_source_id"]')
            current_requested_id = int(req_fcurve.evaluate(start_frame)) if req_fcurve else -1

            if selected_track_index != current_requested_id:
                pdv.set_requested_source_id(selected_track_index, start_frame)
                # Trigger immediate update for better UX while scrubbing
                pdv.update_frame_if_needed(start_frame - 1)
                pdv.update_frame_if_needed(start_frame)
                pdv.update_frame_if_needed(start_frame + 1)

        self.report({"INFO"}, f"Stitching request applied at frame {start_frame}.")
        return {"FINISHED"}


class PE_OT_TriangulatePerson(bpy.types.Operator):
    """Triangulates 2D poses into a 3D animation for the selected persons."""

    bl_idname = "pose_editor.triangulate_person"
    bl_label = "Triangulate Person(s)"
    bl_options = {"REGISTER", "UNDO"}

    frame_range_options = [
        ("CURRENT_FRAME", "Current Frame", "Only triangulate the current frame"),
        ("SCENE_RANGE", "Scene Frame Range", "Triangulate the entire scene frame range"),
        ("CUSTOM_RANGE", "Custom Range", "Specify a custom frame range"),
    ]

    frame_range: bpy.props.EnumProperty(
        name="Frame Range",
        items=frame_range_options,
        default="SCENE_RANGE",
        description="Define which frames to triangulate",
    )

    start_frame: bpy.props.IntProperty(
        name="Start Frame",
        description="The first frame of the custom range to triangulate",
        default=1,
    )

    end_frame: bpy.props.IntProperty(
        name="End Frame",
        description="The last frame of the custom range to triangulate",
        default=250,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_range")
        if self.frame_range == "CUSTOM_RANGE":
            row = layout.row()
            row.prop(self, "start_frame")
            row.prop(self, "end_frame")

    def execute(self, context):
        start_frame, end_frame = self._get_frame_range(context)

        selected_person_facades = []
        for obj in context.selected_objects:
            facade = RealPersonInstanceFacade.from_blender_obj(dal.BlenderObjRef(obj.name))
            if facade:
                selected_person_facades.append(facade)

        if not selected_person_facades:
            self.report({"WARNING"}, "No Real Person Instances selected.")
            return {"CANCELLED"}

        for facade in selected_person_facades:
            try:
                self.report({"INFO"}, f"Baking stitching data for {facade.name}...")
                facade.bake_stitching_data()
                self.report({"INFO"}, f"Triangulating {facade.name}...")
                facade.triangulate(start_frame, end_frame)
            except Exception as e:
                import traceback
                self.report({"ERROR"}, f"Triangulation failed for {facade.name}: {e}")
                print(f"Error during triangulation for {facade.name}: {e}")
                print(traceback.format_exc())
                # Optionally, re-raise if debugging is needed
                # raise e

        self.report({"INFO"}, f"Triangulation finished for {len(selected_person_facades)} person(s).")

        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def _get_frame_range(self, context) -> tuple[int, int]:
        """Determines the start and end frame based on the operator's properties."""
        if self.frame_range == "CURRENT_FRAME":
            current = context.scene.frame_current
            return current, current
        elif self.frame_range == "SCENE_RANGE":
            return context.scene.frame_start, context.scene.frame_end
        elif self.frame_range == "CUSTOM_RANGE":
            return self.start_frame, self.end_frame
        return context.scene.frame_start, context.scene.frame_end
