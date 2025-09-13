# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause


from ..blender import dal
from .marker_data import MarkerData
from .person_data_view import PersonDataView

PERSON_DEFINITION_ID = dal.CustomProperty[str]("person_definition_id")
IS_REAL_PERSON_INSTANCE = dal.CustomProperty[bool]("is_real_person_instance")
ACTIVE_TRACK_INDEX = dal.CustomProperty[int]("active_track_index")


class RealPersonInstanceFacade:
    """A facade for a Real Person Instance.

    Manages the master Empty object for a person and provides methods for
    stitching and managing their data across multiple camera views.
    """

    def __init__(self, person_instance_obj: dal.BlenderObjRef):
        self.obj = person_instance_obj
        # A more robust implementation would not rely on name parsing
        self.person_id = person_instance_obj.name

    def _get_dataseries_for_view(self, view_name: str) -> dal.BlenderObjRef | None:
        """Finds the data series object for this person in a specific view."""
        # This facade assumes a specific naming convention established by the UI/operators
        ds_name = f"DS.{self.person_id}.{view_name}"
        return dal.get_object_by_name(ds_name)

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

        end_frame = self.find_next_stitch_frame(view_name, start_frame)
        if end_frame < start_frame:
            print(f"End frame {end_frame} is before start frame {start_frame}, aborting stitch.")
            return

        print(f"Stitching segment for {self.person_id} in view {view_name} from frame {start_frame} to {end_frame}.")
        print(f"Source track index: {source_track_index}")

        # 1. Get Target and Source MarkerData objects
        target_ds_name = f"{self.person_id}.{view_name}"
        target_md = MarkerData(target_ds_name, skeleton._skeleton.name)

        source_ds_name = f"{view_name}_person{source_track_index}"
        source_md = MarkerData(source_ds_name, skeleton._skeleton.name)

        # 2. Define the columns of data to be copied
        columns_to_copy: List[Tuple[str, str, int]] = []
        for joint_node in skeleton._skeleton.descendants:
            if not hasattr(joint_node, "id") or joint_node.id is None:
                continue
            joint_name = joint_node.name
            columns_to_copy.append((joint_name, "location", 0))  # X
            columns_to_copy.append((joint_name, "location", 1))  # Y
            columns_to_copy.append((joint_name, '["quality"]', -1))  # Quality

        # 3. Read data from the source action
        print(f"Reading data from {source_md.action.name}...")
        source_data_np = dal.get_animation_data_as_numpy(
            source_md.action,
            columns_to_copy,
            start_frame,
            end_frame,
        )
        print(f"Read {source_data_np.shape} data array from source.")

        # 4. Write data to the target action
        print(f"Writing data to {target_md.action.name}...")
        dal.replace_fcurve_segment_from_numpy(target_md.action, columns_to_copy, start_frame, end_frame, source_data_np)
        print("Write complete.")

        # 5. Set the keyframe for the active_track_index
        target_ds_obj = self._get_dataseries_for_view(view_name)
        if target_ds_obj:
            print(
                f"Setting active_track_index keyframe on {target_ds_obj.name} at frame {start_frame} to {source_track_index}"
            )
            dal.set_custom_property(target_ds_obj, ACTIVE_TRACK_INDEX, source_track_index)
            dal.add_keyframe(target_ds_obj, start_frame, {'["active_track_index"]': [source_track_index]})

        # 6. Re-connect the PersonDataView to the now-populated MarkerData
        # This ensures the markers animate with the new data
        real_person_pv_name = f"PV.{self.person_id}.{view_name}"
        real_person_pv_obj_ref = dal.get_object_by_name(real_person_pv_name)

        # 6. Re-connect the PersonDataView to the now-populated MarkerData
        # This ensures the markers animate with the new data
        real_person_pv_name = f"PV.{self.person_id}.{view_name}"
        real_person_pv_obj_ref = dal.get_object_by_name(real_person_pv_name)

        real_person_pv = PersonDataView.from_blender_object(real_person_pv_obj_ref) if real_person_pv_obj_ref else None
        if real_person_pv is None:
            # Fallback: If for some reason the root object doesn't exist or is not valid, create a new one.
            # This case should ideally not happen if PE_OT_AddPersonInstance worked correctly.
            print(
                f"Warning: PersonDataView root object {real_person_pv_name} not found or invalid. Creating a new one."
            )
            # We need to get the collection for the PersonDataView constructor
            person_views_collection = dal.get_or_create_collection("PersonViews")
            # We need the camera_view_obj_ref to create a new PersonDataView
            camera_view_obj_ref = dal.get_object_by_name(f"View_{view_name}")
            if camera_view_obj_ref is None:
                print(f"Error: CameraView {view_name} not found. Cannot create new PersonDataView.")
                return  # Or raise an error

            real_person_pv = PersonDataView.create_new(
                view_name=real_person_pv_name,
                skeleton=skeleton,  # Skeleton is still needed for new creation
                color=(1.0, 1.0, 1.0, 1.0),  # Default color for new creation
                camera_view_obj_ref=camera_view_obj_ref,
                collection=person_views_collection,
            )
            if real_person_pv is None:  # Should not happen if create_new works
                print(f"Error: Failed to create new PersonDataView {real_person_pv_name}.")
                return  # Or raise an error

        target_md.apply_to_view(real_person_pv)
        print(f"Re-connected PersonDataView {real_person_pv_name} to action.")
