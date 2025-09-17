# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause


from typing import Optional

import numpy as np
from anytree import PreOrderIter

from ..blender import dal
from ..blender.dal import CAMERA_VIEW_ID, BlenderObjRef
from .calibration import Calibration
from .marker_data import MarkerData
from .skeleton import get_skeleton
from .triangulation import TriangulationOutput, triangulate_point


PERSON_DEFINITION_ID = dal.CustomProperty[str]("person_definition_id")
PERSON_DEFINITION_REF = dal.CustomProperty[str]("person_definition_ref")
IS_REAL_PERSON_INSTANCE = dal.CustomProperty[bool]("is_real_person_instance")
ACTIVE_TRACK_INDEX = dal.CustomProperty[int]("active_track_index")
PERSON_NAME = dal.CustomProperty[str]("person_name")
POSE_EDITOR_OBJECT_TYPE = dal.CustomProperty[str]("pose_editor_object_type")

class RealPersonInstanceFacade:
    """A facade for a Real Person Instance.

    Manages the master Empty object for a person and provides methods for
    stitching and managing their data across multiple camera views.
    """

    def __init__(self, person_instance_obj: dal.BlenderObjRef):
        """Do not instantiate directly; use create_new or from_blender_obj.
        """        
        self.obj = person_instance_obj
        self.person_id = dal.get_custom_property(person_instance_obj, PERSON_NAME) or person_instance_obj.name
        self.name = dal.get_custom_property(person_instance_obj, PERSON_NAME) 

    @classmethod
    def create_new(cls, person_name: str) -> "RealPersonInstanceFacade":
        """
        Creates a new persistent RealPersonInstance object in Blender.

        Args:
            person_name: Unique name for this person.

        Returns:
            RealPersonInstanceFacade: The newly created instance.
        """
        obj_name = f"PI.{person_name}"
        person_obj = dal.get_or_create_object(
            name=obj_name, obj_type="EMPTY", collection_name="Persons"
        )
        dal.set_custom_property(person_obj, PERSON_NAME, person_name)
        dal.set_custom_property(person_obj, PERSON_DEFINITION_ID, person_obj._id)
        dal.set_custom_property(person_obj, POSE_EDITOR_OBJECT_TYPE, "Person")
        return cls(person_obj)

    @classmethod
    def from_blender_obj(cls, obj_ref: dal.BlenderObjRef) -> "RealPersonInstanceFacade | None":
        """
        Initializes RealPersonInstanceFacade from an existing Blender object.

        Args:
            obj_ref: BlenderObjRef pointing to the person Empty.

        Returns:
            RealPersonInstanceFacade | None: The initialized instance, or None if not valid.
        """
        if not obj_ref or not obj_ref._get_obj():
            return None
        obj_type = dal.get_custom_property(obj_ref, POSE_EDITOR_OBJECT_TYPE)
        if obj_type != "Person":
            return None
        return cls(obj_ref)
    
    @classmethod
    def get_by_id(cls, object_id: str) -> Optional["RealPersonInstanceFacade"]:
        """Finds a RealPersonInstanceFacade by its unique object ID.

        Args:
            object_id: The unique ID of the RealPersonInstanceFacade object.

        Returns:
            A RealPersonInstanceFacade instance if found, otherwise None.
        """
        obj_ref = dal.find_object_by_property(PERSON_DEFINITION_ID, object_id)
        if not obj_ref:
            return None
        return cls.from_blender_obj(obj_ref)

    @classmethod
    def get_all(cls) -> list["RealPersonInstanceFacade"]:
        """
        Returns all RealPersonInstanceFacade objects found in the Blender file.

        Returns:
            List of RealPersonInstanceFacade instances.
        """
        all_objs = dal.find_all_objects_by_property(POSE_EDITOR_OBJECT_TYPE, "Person")
        return [cls(obj) for obj in all_objs]
    
    def _get_dataseries_for_view(self, view_name: str) -> dal.BlenderObjRef | None:
        """Finds the data series object for this person in a specific view."""
        # This facade assumes a specific naming convention established by the UI/operators
        all_ds = dal.find_all_objects_by_property(POSE_EDITOR_OBJECT_TYPE, "MarkerData")
        for ds in all_ds:
            ds_person_id = dal.get_custom_property(ds, PERSON_DEFINITION_REF)
            ds_view_id = dal.get_custom_property(ds, CAMERA_VIEW_ID)
            if ds_person_id == self.person_id and ds_view_id == view_name:
                return ds
        return None

    def get_active_track_index_at_frame(self, view_name: str, frame: int) -> int:
        """Gets the value of the active_track_index at a specific frame."""
        ds_obj = self._get_dataseries_for_view(view_name)
        if not ds_obj:
            return -1

        fcurve = dal.get_fcurve_on_object(ds_obj, '["active_track_index"]', index=-1)
        if not fcurve:
            # If no fcurve, try to get the static value
            val = dal.get_custom_property(ds_obj, ACTIVE_TRACK_INDEX)
            return val if val is not None else -1

        return int(fcurve.evaluate(frame))

    def find_next_stitch_frame(self, view_name: str, start_frame: int) -> int:
        """Finds the frame of the next stitch point after the start_frame."""
        ds_obj = self._get_dataseries_for_view(view_name)
        scene_start, scene_end = dal.get_scene_frame_range()

        if not ds_obj:
            return scene_end

        fcurve = dal.get_fcurve_on_object(ds_obj, '["active_track_index"]', index=-1)
        if not fcurve:
            return scene_end

        keyframes = dal.get_fcurve_keyframes(fcurve)
        for frame, _ in keyframes:
            if frame > start_frame:
                return int(frame) - 1  # The segment ends the frame before the next stitch

        return scene_end

    def assign_source_track_for_segment(
        self,
        view_name: str,
        source_track_index: int,
        start_frame: int,
        skeleton: "SkeletonBase",
    ):
        """Assigns a new source track for a segment of the timeline."""

        from .person_data_view import PersonDataView

        end_frame = self.find_next_stitch_frame(view_name, start_frame)
        if end_frame < start_frame:
            print(f"End frame {end_frame} is before start frame {start_frame}, aborting stitch.")
            return

        print(f"Stitching segment for {self.person_id} in view {view_name} from frame {start_frame} to {end_frame}.")
        print(f"Source track index: {source_track_index}")


        source_md_ref: BlenderObjRef | None = None
        target_md_ref: BlenderObjRef | None = None
        all_md = dal.find_all_objects_by_property(POSE_EDITOR_OBJECT_TYPE, "MarkerData")
        for ds in all_md:
            if dal.get_custom_property(ds, CAMERA_VIEW_ID) == view_name:
                if dal.get_custom_property(ds, PERSON_DEFINITION_REF) == self.obj._id:
                    target_md_ref = ds
                else:
                    series_name = dal.get_custom_property(ds, dal.SERIES_NAME) or ""
                    if series_name.find(f"_person{source_track_index}")>=0:
                        source_md_ref = ds

        if not source_md_ref:
            print(f"Error: Source MarkerData for track index {source_track_index} in view {view_name} not found.")
            return
        if not target_md_ref:
            print(f"Error: Target MarkerData for person {self.person_id} in view {view_name} not found.")
            return
        source_md = MarkerData.from_blender_object(source_md_ref)
        target_md = MarkerData.from_blender_object(target_md_ref)

        if not source_md or not target_md:
            print("Error: Failed to initialize MarkerData from Blender objects.")
            return
        
        # Find the PersonDataView for this person and view
        all_pvs = PersonDataView.get_all()
        pv = None
        for person_view in all_pvs:
            pvp = person_view.get_person()
            pvcam = person_view.camera_view()
            if pvp and pvcam and pvcam._obj and pvp.person_id == self.person_id and pvcam._obj.name == view_name:
                pv = person_view
                break

        if not pv:
            print(f"Error: PersonDataView for person {self.person_id} in view {view_name} not found.")
            raise ValueError(f"PersonDataView for person {self.person_id} in view {view_name} not found.")
        
        # 2. Define the columns of data to be copied
        columns_to_copy: list[tuple[str, str, int]] = []
        for joint_node in skeleton._skeleton.descendants:
            if not hasattr(joint_node, "id") or joint_node.id is None:
                continue
            joint_name = joint_node.name
            columns_to_copy.append((joint_name, "location", 0))  # X
            columns_to_copy.append((joint_name, "location", 1))  # Y
            columns_to_copy.append((joint_name, '["quality"]', -1))  # Quality

        # 3. Read data from the source action
        print(f"Reading data from {source_md.action.name if source_md.action else 'Unknown'}...")
        source_data_np = dal.get_animation_data_as_numpy(
            source_md.action,
            columns_to_copy,
            start_frame,
            end_frame,
        )
        print(f"Read {source_data_np.shape} data array from source.")

        # 4. Write data to the target action
        print(f"Writing data to {target_md.action.name if target_md.action else 'Unknown'}...")
        dal.replace_fcurve_segment_from_numpy(target_md.action, columns_to_copy, start_frame, end_frame, source_data_np)
        print("Write complete.")

        # 5. Set the keyframe for the active_track_index
        print(
            f"Setting active_track_index keyframe on {target_md_ref.name} at frame {start_frame} to {source_track_index}"
        )
        dal.set_custom_property(target_md_ref, ACTIVE_TRACK_INDEX, source_track_index)
        dal.add_keyframe(target_md_ref, start_frame, {'["active_track_index"]': [source_track_index]})

        target_md.apply_to_view(pv)
        print(f"Re-connected PersonDataView {pv} to action.")

    def triangulate(self, frame_start: int, frame_end: int):
        """Performs 3D triangulation for this person over a frame range."""

        from .person_data_view import PersonDataView
        from .person_3d_view import Person3DView

        # 1. Get calibration data
        calibration = Calibration()
        if not calibration._data:
            print("Error: Calibration data not found in scene.")
            return

        all_camera_names = calibration.get_camera_names()

        # 2. Get all 2D data views for this person
        all_pdvs = PersonDataView.get_all()
        person_pdvs = [
            pdv
            for pdv in all_pdvs
            if pdv.get_person() and pdv.get_person().person_id == self.person_id
        ]

        if not person_pdvs:
            print(f"Error: No 2D data views found for person {self.name}")
            return

        # Assume all views share the same skeleton
        skeleton = person_pdvs[0].skeleton
        if not skeleton:
            print("Error: Skeleton not found for person data views.")
            return

        # 3. Find or create the 3D View and its MarkerData
        person_3d_view = Person3DView.get_for_person(self)
        if not person_3d_view:
            person_3d_view = Person3DView.create_new(
                view_name=f"P3D.{self.name}",
                skeleton=skeleton,
                color=(0.8, 0.8, 0.8, 1.0),
                parent_ref=self.obj,
                person=self,
            )

        marker_data_3d_name = f"{self.name}_3D"
        all_mds = dal.find_all_objects_by_property(dal.POSE_EDITOR_OBJECT_TYPE, "MarkerData")
        marker_data_3d_ref = None
        for md_ref in all_mds:
            md_person_id = dal.get_custom_property(md_ref, PERSON_DEFINITION_REF)
            md_view_id = dal.get_custom_property(md_ref, CAMERA_VIEW_ID)
            if md_person_id == self.obj._id and not md_view_id:
                marker_data_3d_ref = md_ref
                break

        if marker_data_3d_ref:
            marker_data_3d = MarkerData.from_blender_object(marker_data_3d_ref)
        else:
            marker_data_3d = MarkerData.create_new(
                series_name=marker_data_3d_name, skeleton_name=skeleton.name, person=self
            )

        if not marker_data_3d:
            print(f"Error: Could not find or create MarkerData for {marker_data_3d_name}")
            return

        # 4. Loop through frames and markers, collecting triangulation results
        num_frames = frame_end - frame_start + 1
        marker_nodes = [node for node in PreOrderIter(skeleton._skeleton) if hasattr(node, "id") and node.id is not None]
        num_markers = len(marker_nodes)

        # Prepare NumPy arrays to hold the final 3D data and metadata
        output_locations = np.full((num_frames, num_markers * 3), np.nan)
        output_reprojection_errors = np.full((num_frames, num_markers), np.nan)
        output_cam_counts = np.zeros((num_frames, num_markers), dtype=int)
        output_cam_bools = np.zeros((num_frames, num_markers * len(all_camera_names)), dtype=bool)

        calib_by_cam = calibration._data

        for frame_offset, frame in enumerate(range(frame_start, frame_end + 1)):
            for marker_idx, marker_node in enumerate(marker_nodes):
                marker_name = marker_node.name

                # 5. Gather 2D data for this marker at this frame from all views
                points_2d_by_camera = {}
                for pdv in person_pdvs:
                    cam_view = pdv.get_camera_view()
                    if not cam_view or not cam_view._obj:
                        continue

                    calib_cam_name = dal.get_custom_property(cam_view._obj, dal.CALIBRATION_CAMERA_NAME)
                    if not calib_cam_name:
                        continue

                    marker_data_2d = pdv.get_data_series()
                    if not marker_data_2d or not marker_data_2d.action:
                        continue

                    fcurve_x = dal.get_fcurve_from_action(marker_data_2d.action, marker_name, "location", 0)
                    fcurve_y = dal.get_fcurve_from_action(marker_data_2d.action, marker_name, "location", 1)
                    fcurve_quality = dal.get_fcurve_from_action(marker_data_2d.action, marker_name, '["quality"]', -1)

                    if fcurve_x and fcurve_y and fcurve_quality:
                        x = fcurve_x.evaluate(frame)
                        y = fcurve_y.evaluate(frame)
                        quality = fcurve_quality.evaluate(frame)
                        points_2d_by_camera[calib_cam_name] = np.array([x, y, quality])

                # 6. Triangulate the point
                if len(points_2d_by_camera) >= 2:
                    result: TriangulationOutput | None = triangulate_point(
                        points_2d_by_camera=points_2d_by_camera,
                        calibration_by_camera=calib_by_cam,
                    )
                    # 7. Collect results
                    if result:
                        loc_col_start = marker_idx * 3
                        output_locations[frame_offset, loc_col_start : loc_col_start + 3] = result.point_3d
                        output_reprojection_errors[frame_offset, marker_idx] = result.reprojection_error
                        output_cam_counts[frame_offset, marker_idx] = len(result.contributing_cameras)

                        # Set boolean flags for each camera
                        for cam_idx, cam_name in enumerate(all_camera_names):
                            bool_col_start = marker_idx * len(all_camera_names)
                            output_cam_bools[frame_offset, bool_col_start + cam_idx] = cam_name in result.contributing_cameras

        # 8. Define the columns for the NumPy array and write to F-Curves
        final_columns = []
        for marker_idx, marker_node in enumerate(marker_nodes):
            marker_name = marker_node.name
            # Location (X, Y, Z)
            final_columns.append((marker_name, "location", 0))
            final_columns.append((marker_name, "location", 1))
            final_columns.append((marker_name, "location", 2))

        for marker_idx, marker_node in enumerate(marker_nodes):
            marker_name = marker_node.name
            final_columns.append((marker_name, '["reprojection_error"]', -1))

        for marker_idx, marker_node in enumerate(marker_nodes):
            marker_name = marker_node.name
            final_columns.append((marker_name, '["contributing_cam_count"]', -1))

        for marker_idx, marker_node in enumerate(marker_nodes):
            marker_name = marker_node.name
            for cam_idx, cam_name in enumerate(all_camera_names):
                prop_name = f'["contrib_{cam_name}"]'
                final_columns.append((marker_name, prop_name, -1))

        # Reshape boolean array to be (num_frames, num_markers * num_cameras)
        output_cam_bools_reshaped = output_cam_bools.reshape((num_frames, -1))

        # Combine all data into one array for writing
        final_data_array = np.hstack((
            output_locations,
            output_reprojection_errors,
            output_cam_counts,
            output_cam_bools_reshaped
        ))

        print(f"Writing {final_data_array.shape} data array to action {marker_data_3d.action.name}...")

        dal.replace_fcurve_segment_from_numpy(
            action=marker_data_3d.action,
            columns=final_columns,
            start_frame=frame_start,
            end_frame=frame_end,
            data=final_data_array,
        )

        # 9. Connect the 3D view to the newly populated MarkerData
        person_3d_view.connect_to_series(marker_data_3d)

        print("Triangulation data successfully written to f-curves.")
