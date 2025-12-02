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
from ..core.skeleton import COCO133Skeleton, HALPE26Skeleton, get_skeleton
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

    skeleton_type: bpy.props.EnumProperty(
        name="Skeleton Type",
        description="Select the skeleton type for pose data",
        items=[
            ("COCO133", "COCO-133", "COCO-133 skeleton with 133 keypoints"),
            ("HALPE26", "HALPE-26", "HALPE-26 skeleton with 26 keypoints"),
        ],
        default="COCO133"
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
                # Create skeleton based on user selection
                if self.skeleton_type == "COCO133":
                    skeleton = COCO133Skeleton()
                elif self.skeleton_type == "HALPE26":
                    skeleton = HALPE26Skeleton()
                else:
                    # Fallback to COCO133 if something unexpected happens
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

        # Get skeleton from existing person data views, or use COCO133 as fallback
        skeleton = None
        if camera_views:
            # Try to get skeleton from an existing PersonDataView
            existing_pdvs = PersonDataView.get_all()
            if existing_pdvs:
                skeleton = existing_pdvs[0].skeleton

            # If no existing PDVs or skeleton, fallback to getting from camera view properties
            if not skeleton and camera_views:
                # Get skeleton from first camera view's associated person data if available
                cam_view_pdvs = PersonDataView.get_all_for_camera_view(camera_views[0])
                if cam_view_pdvs:
                    skeleton = cam_view_pdvs[0].skeleton

        # Final fallback to COCO133 if no skeleton found
        if not skeleton:
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

    algorithm: bpy.props.EnumProperty(
        name="Algorithm",
        description="Triangulation algorithm to use",
        items=[
            ("ransac", "RANSAC", "RANSAC-based algorithm (faster, robust to outliers)"),
            ("exhaustive", "Exhaustive", "Exhaustive search (slower, but more thorough)"),
        ],
        default="ransac",
    )

    reproj_error_threshold: bpy.props.FloatProperty(
        name="Reprojection Error Threshold",
        description="Maximum allowed reprojection error in pixels",
        default=10.0,
        min=0.1,
        max=100.0,
        soft_min=1.0,
        soft_max=50.0,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_range")
        if self.frame_range == "CUSTOM_RANGE":
            row = layout.row()
            row.prop(self, "start_frame")
            row.prop(self, "end_frame")
        layout.prop(self, "algorithm")
        layout.prop(self, "reproj_error_threshold")

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
                try:
                    self.report({"INFO"}, f"Baking stitching data for {facade.name}...")
                    facade.bake_stitching_data()
                except Exception as e:
                    self.report({"ERROR"}, f"Baking stitching data failed for {facade.name}: {e}")
                self.report({"INFO"}, f"Triangulating {facade.name}...")
                facade.triangulate(
                    start_frame, 
                    end_frame, 
                    algorithm=self.algorithm,
                    reproj_error_threshold=self.reproj_error_threshold
                )
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


class PE_OT_CopyStitching(bpy.types.Operator):
    """Copies the stitching (requested_source_id) f-curve from one camera view to another for the selected person(s)."""

    bl_idname = "pose_editor.copy_stitching"
    bl_label = "Copy Stitching Data"
    bl_description = "Copy stitching data from a source camera to the active camera for the selected person(s)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.pose_editor_copy_stitching

        # 1. Get person from properties
        person_name = props.person_to_copy
        if not person_name:
            self.report({"WARNING"}, "No person selected.")
            return {"CANCELLED"}

        all_persons = {p.name: p for p in RealPersonInstanceFacade.get_all()}
        facade = all_persons.get(person_name)

        if not facade:
            self.report({"ERROR"}, f"Person '{person_name}' not found.")
            return {"CANCELLED"}

        # 2. Get source and target camera views
        source_camera_name = props.source_camera

        active_camera = context.space_data.camera
        if not active_camera or not active_camera.name.startswith("Cam_"):
            self.report({"ERROR"}, "No active camera view. Select a view to copy stitching data TO.")
            return {"CANCELLED"}

        target_camera_short_name = active_camera.name.replace("Cam_", "")

        if source_camera_name == target_camera_short_name:
            self.report({"ERROR"}, "Source and target camera cannot be the same.")
            return {"CANCELLED"}

        all_camera_views = {view.name: view for view in CameraView.get_all()}
        source_camera_view = all_camera_views.get(source_camera_name)
        target_camera_view = all_camera_views.get(target_camera_short_name)

        if not source_camera_view:
            self.report({"ERROR"}, f"Source camera view '{source_camera_name}' not found.")
            return {"CANCELLED"}
        if not target_camera_view:
            self.report({"ERROR"}, f"Target camera view '{target_camera_short_name}' not found.")
            return {"CANCELLED"}

        # 3. Perform the copy for the selected person
        facade.copy_stitching_from_view(source_camera_view, target_camera_view)
        self.report({"INFO"}, f"Copied stitching for {facade.name} from {source_camera_name} to {target_camera_short_name}")

        return {"FINISHED"}

    def invoke(self, context, event):
        # Check if there are persons to copy
        if not RealPersonInstanceFacade.get_all():
            self.report({"ERROR"}, "No Real Persons exist in the scene.")
            return {"CANCELLED"}

        # Check if there's at least one other camera view to copy from
        if len(CameraView.get_all()) < 2:
            self.report({"ERROR"}, "At least two camera views are needed to copy stitching data.")
            return {"CANCELLED"}

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        props = context.scene.pose_editor_copy_stitching
        layout.prop(props, "person_to_copy")
        layout.prop(props, "source_camera")


class PE_OT_EditPerson(bpy.types.Operator):
    """Select all armatures for the selected person and switch to pose mode."""

    bl_idname = "pose_editor.edit_person"
    bl_label = "Edit Person"
    bl_description = "Select all 2D and 3D armatures for the person and switch to pose mode"

    def execute(self, context):
        person_id = context.scene.pose_editor_props.selected_person
        if not person_id:
            self.report({"ERROR"}, "No person selected")
            return {"CANCELLED"}

        # Get the person facade
        person = RealPersonInstanceFacade.get_by_id(person_id)
        if not person:
            self.report({"ERROR"}, f"Person with ID {person_id} not found")
            return {"CANCELLED"}

        # Switch to object mode first
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Deselect all objects
        bpy.ops.object.select_all(action='DESELECT')

        armatures_selected = 0

        # Get all PersonDataViews for this person and select their armatures
        all_person_views = PersonDataView.get_all()
        for view in all_person_views:
            if view.get_person() and view.get_person().obj._id == person_id:
                if view.armature_ref and view.armature_ref._get_obj():
                    armature_obj = view.armature_ref._get_obj()
                    armature_obj.select_set(True)
                    armatures_selected += 1
                    # Set the first armature as active
                    if armatures_selected == 1:
                        context.view_layer.objects.active = armature_obj

        # Get Person3DView for this person and select its armature
        from ..core.person_3d_view import Person3DView
        person_3d_view = Person3DView.get_for_person(person)
        if person_3d_view and person_3d_view.armature_ref:
            armature_obj = person_3d_view.armature_ref._get_obj()
            if armature_obj:
                armature_obj.select_set(True)
                armatures_selected += 1
                # Set as active if it's the only armature
                if armatures_selected == 1:
                    context.view_layer.objects.active = armature_obj

        if armatures_selected == 0:
            self.report({"WARNING"}, f"No armatures found for person {person.name}")
            return {"CANCELLED"}

        # Switch to pose mode
        bpy.ops.object.mode_set(mode='POSE')

        self.report({"INFO"}, f"Selected {armatures_selected} armature(s) for {person.name}")
        return {"FINISHED"}


class PE_OT_MarkFrame(bpy.types.Operator):
    """Mark current frame as reference for body part enable/disable operations"""

    bl_idname = "pose_editor.mark_frame"
    bl_label = "Mark Frame"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.pose_editor_props.marker_frame = context.scene.frame_current
        self.report({'INFO'}, f"Marked frame {context.scene.frame_current}")
        return {'FINISHED'}


class PE_OT_ToggleBodyPartEnable(bpy.types.Operator):
    """Toggle body part enable property for frame range"""

    bl_idname = "pose_editor.toggle_body_part_enable"
    bl_label = "Toggle Body Part Enable"
    bl_options = {'REGISTER', 'UNDO'}

    body_part_name: bpy.props.StringProperty(
        name="Body Part Name",
        description="Name of the body part to toggle",
        default=""
    )

    def execute(self, context):
        # Check we're in POSE mode
        if context.mode != 'POSE':
            self.report({'WARNING'}, "Must be in Pose Mode")
            return {'CANCELLED'}

        # Get current view's armature
        armature = self._get_current_view_armature(context)
        if not armature:
            self.report({'ERROR'}, "No armature found for current view")
            return {'CANCELLED'}

        # Get CTRL-enable bone
        ctrl_bone_name = "CTRL-enable"
        if ctrl_bone_name not in armature.pose.bones:
            self.report({'ERROR'}, f"Control bone '{ctrl_bone_name}' not found in armature")
            return {'CANCELLED'}

        pose_bone = armature.pose.bones[ctrl_bone_name]

        # Convert body part name to property name
        from ..core.person_data_view import _body_part_to_property_name
        prop_name = f"enable_{_body_part_to_property_name(self.body_part_name)}"

        # Get frames
        current_frame = context.scene.frame_current
        marker_frame = context.scene.pose_editor_props.marker_frame
        frame_start = min(current_frame, marker_frame)
        frame_end = max(current_frame, marker_frame)

        # Get current value and toggle
        current_value = pose_bone.get(prop_name, 1.0)
        new_value = 1.0 if current_value < 0.5 else 0.0

        # Store original frame
        original_frame = current_frame

        # Check values at boundaries (outside the range)
        value_before = new_value
        if frame_start > 1:
            context.scene.frame_set(frame_start - 1)
            value_before = pose_bone.get(prop_name, 1.0)

        context.scene.frame_set(frame_end + 1)
        value_after = pose_bone.get(prop_name, 1.0)

        # Set boundary keyframes if needed
        if value_before != new_value:
            context.scene.frame_set(frame_start)
            pose_bone[prop_name] = new_value
            pose_bone.keyframe_insert(data_path=f'["{prop_name}"]', frame=frame_start)

        if value_after != new_value:
            # Set frame_end + 1 back to value_after to preserve value outside range
            context.scene.frame_set(frame_end + 1)
            pose_bone[prop_name] = value_after
            pose_bone.keyframe_insert(data_path=f'["{prop_name}"]', frame=frame_end + 1)

        # Remove all keyframes inside the range (exclusive)
        armature_ref = dal.BlenderObjRef(armature.name)
        fcurve_path = f'pose.bones["{ctrl_bone_name}"]["{prop_name}"]'
        fcurve = dal.get_fcurve_on_object(armature_ref, fcurve_path)
        if fcurve:
            keyframes_to_remove = []
            for kf in fcurve.keyframe_points:
                if frame_start < kf.co[0] < frame_end:
                    keyframes_to_remove.append(kf)
            for kf in reversed(keyframes_to_remove):
                fcurve.keyframe_points.remove(kf)

        # Restore original frame
        context.scene.frame_set(original_frame)

        state = "enabled" if new_value > 0.5 else "disabled"
        self.report({'INFO'}, f"{self.body_part_name} {state} for frames {frame_start}-{frame_end}")
        return {'FINISHED'}

    def _get_current_view_armature(self, context):
        """Get the PersonDataView armature for the current camera view."""
        camera = context.space_data.camera
        if not camera or not camera.name.startswith("Cam_"):
            return None

        view_name = camera.name.replace("Cam_", "")

        # Find view object
        view_obj = dal.get_object_by_name(f"View_{view_name}")
        if not view_obj:
            return None

        # Get selected person
        person_id = context.scene.pose_editor_props.selected_person
        if not person_id:
            return None

        # Find PersonDataView for this person and camera
        for person_view in PersonDataView.get_all():
            view_person = person_view.get_person()
            if not view_person:
                continue

            camera_view_obj = person_view.camera_view()
            if not camera_view_obj or not camera_view_obj._obj:
                continue

            if (view_person.obj._id == person_id and
                camera_view_obj._obj.name == view_obj.name):
                if person_view.armature_ref:
                    return person_view.armature_ref._get_obj()

        return None

