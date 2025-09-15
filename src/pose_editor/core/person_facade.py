# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause


from typing import Optional
from ..blender import dal
from .marker_data import MarkerData
from ..blender.dal import CAMERA_VIEW_ID, BlenderObjRef

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
