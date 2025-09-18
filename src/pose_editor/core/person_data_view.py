# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from typing import Optional, TYPE_CHECKING

import numpy as np

from ..blender import dal
from .frame_handler import frame_handler

if TYPE_CHECKING:
    from .camera_view import CameraView
from .marker_data import MarkerData
from .skeleton import SkeletonBase, get_skeleton
from .person_facade import RealPersonInstanceFacade, PERSON_DEFINITION_REF
from ..blender.dal import CAMERA_VIEW_ID

SKELETON_NAME = dal.CustomProperty[str]("skeleton_name")
REQUESTED_SOURCE_ID = dal.CustomProperty[int]("requested_source_id")
APPLIED_SOURCE_ID = dal.CustomProperty[int]("applied_source_id")


class PersonDataView:
    """A facade for a person's 2D data view (View layer).

    Manages a 'Person View' root Empty and its hierarchy of marker Empties,
    which visually represent the animation data from a MarkerData series.

    Blender Representation:
    -   **Root Object**: A main Empty object (e.g., `PV.cam1_person0_raw`) in the
        `PersonViews` collection. This object acts as the parent for all visual
        components of this person-view.
    -   **Marker Objects**: For each joint in the skeleton, a child Empty is
        created. These are the objects that are ultimately animated.
    -   **Armature Object**: A child Armature object is created with bones
        connecting the marker objects. The bones use `COPY_LOCATION` and
        `STRETCH_TO` constraints to follow the markers.

    Custom Properties on Root Object (`view_root_object`):
    -   `pose_editor_object_type` (str): Identifies this object as a "PersonDataView".
    -   `skeleton` (str): The name of the skeleton definition used (e.g., "COCO_133").
    -   `color` (tuple[float, float, float, float]): The RGBA color of the markers.
    -   `camera_view_id` (str): The name of the CameraView this PersonDataView belongs to.
    """

    def __init__(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the PersonDataView as a wrapper around an existing Blender object.

        Do not call this constructor directly; use the factory methods create_new() 
        or from_blender_object() instead.

        Args:
            view_root_obj_ref: A BlenderObjRef pointing to the root Empty of the
                               existing PersonDataView (e.g., PV.Alice.cam1).
        """
        self._obj = view_root_obj_ref
        self.skeleton: Optional[SkeletonBase] = None
        self._init_from_blender_ref(view_root_obj_ref)

        # If this is a "Real Person" view, register for frame changes.
        if self.get_person() is not None:
            frame_handler.add_callback(self._check_and_update_frame)

    def __del__(self):
        """Destructor to unregister the callback when the object is garbage collected."""
        if hasattr(self, "_check_and_update_frame") and self.get_person() is not None:
            frame_handler.remove_callback(self._check_and_update_frame)

    def _init_from_blender_ref(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the PersonDataView from an existing Blender object.

        This method assumes the Blender objects (root Empty, markers, armature)
        already exist in the scene and initializes the Python wrapper around them.
        It does NOT create any new Blender objects.

        Args:
            view_root_obj_ref: A BlenderObjRef pointing to the root Empty of the
                               existing PersonDataView (e.g., PV.Alice.cam1).
        """
        self.view_root_object = view_root_obj_ref

        # Populate marker objects and find armature from existing Blender objects
        self._marker_objects_by_role = {}
        self._populate_marker_objects_by_role()
        armature_name = f"{self.view_name}_Armature"
        self._armature_object = dal.get_object_by_name(armature_name)
        if not self._armature_object:
            print(f"Warning: Armature {armature_name} not found for existing PersonDataView {self.view_name}")

        skeleton_name = dal.get_custom_property(view_root_obj_ref, SKELETON_NAME)
        if skeleton_name:
            self.skeleton = get_skeleton(skeleton_name)

    @classmethod
    def create_new(
        cls,
        view_name: str,
        skeleton,
        color,
        camera_view,
        collection=None,
        person: Optional[RealPersonInstanceFacade] = None,
        marker_data: Optional[MarkerData] = None,
    ) -> "PersonDataView":
        """
        Creates a new PersonDataView object in Blender.

        Args:
            view_name: Name for the view.
            skeleton: Skeleton object.
            color: Color tuple.
            camera_view: CameraView object.
            collection: Blender collection to add to.
            person: Optional RealPersonInstanceFacade to associate.
            marker_data: Optional MarkerData to connect to.

        Returns:
            PersonDataView: The newly created instance.
        """
        from .camera_view import CameraView

        if collection is None:
            collection = dal.get_or_create_collection("PersonViews")

        obj = dal.get_or_create_object(
            name=view_name, obj_type="EMPTY", collection_name=collection.name if collection else None, parent=camera_view._obj
        )
        # Set custom properties
        dal.set_custom_property(obj, dal.SERIES_NAME, view_name)
        dal.set_custom_property(obj, SKELETON_NAME, skeleton.name)
        dal.set_custom_property(obj, dal.COLOR, color)
        dal.set_custom_property(obj, CAMERA_VIEW_ID, camera_view._obj.name if camera_view and camera_view._obj else "")
        dal.set_custom_property(obj, PERSON_DEFINITION_REF, person.obj._id if person and person.obj else "")
        dal.set_custom_property(obj, dal.POSE_EDITOR_OBJECT_TYPE, "PersonDataView")
        instance = cls(obj)

        instance._init_from_blender_ref(obj)
        instance._create_marker_objects(collection)
        instance._populate_marker_objects_by_role()
        instance._create_armature()
        instance._init_from_blender_ref(obj)

        obj._get_obj().location = camera_view.translation
        obj._get_obj().scale = camera_view.scale

        # If it's a real person, initialize the new animated properties
        if person:
            marker_data = instance.get_data_series()
            if marker_data:
                md_obj = marker_data.obj_ref
                scene_start, scene_end = dal.get_scene_frame_range()

                # Requested ID: Sparse, just one keyframe at the start
                dal.set_custom_property(md_obj, REQUESTED_SOURCE_ID, -1)
                dal.add_keyframe(md_obj, scene_start, {'["requested_source_id"]': [-1]})

                # Applied ID: Dense, one keyframe for every frame
                dal.set_custom_property(md_obj, APPLIED_SOURCE_ID, -1)
                keyframes = [(frame, [-1]) for frame in range(scene_start, scene_end + 1)]
                dal.set_fcurve_from_data(md_obj, '["applied_source_id"]', keyframes)

        if marker_data:
            instance.connect_to_series(marker_data)

        return instance

    def get_camera_view(self) -> Optional["CameraView"]:
        """
        Returns the CameraView object associated with this PersonDataView, or None if not assigned.
        """
        camera_view_id = dal.get_custom_property(self._obj, CAMERA_VIEW_ID)
        if not camera_view_id:
            return None
        from .camera_view import CameraView

        return CameraView.get_by_id(camera_view_id)

    def get_person(self) -> Optional[RealPersonInstanceFacade]:
        """Returns the RealPersonInstanceFacade associated with this view."""
        from .person_facade import RealPersonInstanceFacade, PERSON_DEFINITION_REF

        person_id = dal.get_custom_property(self._obj, PERSON_DEFINITION_REF)
        if not person_id:
            return None
        return RealPersonInstanceFacade.get_by_id(person_id)

    @property
    def view_name(self) -> str:
        """Returns the name of this PersonDataView."""
        return dal.get_custom_property(self._obj, dal.SERIES_NAME) or ""

    @property
    def color(self) -> tuple[float, float, float, float]:
        """Returns the RGBA color of this PersonDataView."""
        return dal.get_custom_property(self._obj, dal.COLOR) or (1.0, 1.0, 1.0, 1.0)

    def camera_view(self) -> Optional["CameraView"]:
        """Returns the CameraView this PersonDataView belongs to."""
        camera_view_id = dal.get_custom_property(self._obj, CAMERA_VIEW_ID)
        if not camera_view_id:
            return None
        from .camera_view import CameraView

        return CameraView.get_by_id(camera_view_id)

    @classmethod
    def get_by_id(cls, object_id: str) -> Optional["PersonDataView"]:
        """Finds a PersonDataView by its unique object ID.

        Args:
            object_id: The unique ID of the PersonDataView root object.

        Returns:
            A PersonDataView instance if found, otherwise None.
        """
        obj_ref = dal.find_object_by_property(dal.POSE_EDITOR_OBJECT_ID, object_id)
        if not obj_ref:
            return None
        return cls.from_blender_object(obj_ref)

    @classmethod
    def from_blender_object(cls, view_root_obj_ref: dal.BlenderObjRef) -> Optional["PersonDataView"]:
        """Builds a PersonDataView instance from an existing Blender object.

        This factory method assumes the Blender objects (root Empty, markers, armature)
        already exist in the scene and initializes the Python wrapper around them.
        It does NOT create any new Blender objects.

        Args:
            view_root_obj_ref: A BlenderObjRef pointing to the root Empty of the
                               existing PersonDataView (e.g., PV.Alice.cam1).

        Returns:
            A PersonDataView instance initialized from the existing Blender data,
            or None if the object is not found or is not a valid PersonDataView root.
        """
        if not view_root_obj_ref or not view_root_obj_ref._get_obj():
            return None

        obj_type = dal.get_custom_property(view_root_obj_ref, dal.POSE_EDITOR_OBJECT_TYPE)
        if obj_type != "PersonDataView":
            return None

        instance = cls(view_root_obj_ref)
        instance._init_from_blender_ref(view_root_obj_ref)
        return instance

    @classmethod
    def get_all(cls) -> list["PersonDataView"]:
        """Returns all PersonDataView objects in the Blender file."""
        objs = dal.find_all_objects_by_property(dal.POSE_EDITOR_OBJECT_TYPE, "PersonDataView")
        ret = []
        for o in objs:
            if o is None:
                continue
            pdv = cls.from_blender_object(o)
            if pdv is not None:
                ret.append(pdv)
        return ret

    @classmethod
    def get_all_for_camera_view(cls, camera_view: "CameraView") -> list["PersonDataView"]:
        """Returns all PersonDataViews that belong to the given camera view."""
        if camera_view._obj is None:
            return []
        camera_view_id = camera_view._obj._id
        objs = cls.get_all()
        ret = []
        for o in objs:
            if o is None:
                continue
            pdv = cls.from_blender_object(dal.BlenderObjRef(o.view_name))
            if pdv is not None and pdv.camera_view_id == camera_view_id:
                ret.append(pdv)
        return ret

    def _create_marker_objects(self, collection: "bpy.types.Collection"):
        """Creates a marker object for each joint in the skeleton."""
        if self.skeleton is None or self.skeleton._skeleton is None:
            return

        from anytree import PreOrderIter

        for node in PreOrderIter(self.skeleton._skeleton):
            if not (hasattr(node, "id") and node.id is not None):
                continue

            marker_name = node.name
            dal.create_marker(parent=self.view_root_object, name=marker_name, color=self.color, collection=collection)

    def _create_armature(self):
        """Creates an armature with bones connecting the markers."""
        armature_name = f"{self.view_name}_Armature"
        self._armature_object = dal.get_or_create_object(
            name=armature_name, obj_type="ARMATURE", collection_name="PersonViews", parent=self.view_root_object
        )
        self._armature_object._get_obj().color = self.color

        dal.set_armature_display_stick(self._armature_object)

        bones_to_add = []
        for node in self.skeleton._skeleton.descendants:
            if (
                node.parent
                and hasattr(node, "id")
                and node.id is not None
                and hasattr(node.parent, "id")
                and node.parent.id is not None
            ):
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                parent_marker = self._marker_objects_by_role.get(parent_marker_role)
                child_marker = self._marker_objects_by_role.get(child_marker_role)

                if parent_marker and child_marker:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    bones_to_add.append((bone_name, (0, 0, 0), (0, 1, 0)))

        if bones_to_add:
            dal.add_bones_in_bulk(self._armature_object, bones_to_add)

        for node in self.skeleton._skeleton.descendants:
            if (
                node.parent
                and hasattr(node, "id")
                and node.id is not None
                and hasattr(node.parent, "id")
                and node.parent.id is not None
            ):
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                parent_marker = self._marker_objects_by_role.get(parent_marker_role)
                child_marker = self._marker_objects_by_role.get(child_marker_role)

                if parent_marker and child_marker:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    dal.add_bone_constraint(self._armature_object, bone_name, "COPY_LOCATION", parent_marker)
                    dal.add_bone_constraint(self._armature_object, bone_name, "STRETCH_TO", child_marker)

                    expression = "var1 or var2"
                    variables = [
                        ("var1", "SINGLE_PROP", parent_marker.name, "hide_viewport"),
                        ("var2", "SINGLE_PROP", child_marker.name, "hide_viewport"),
                    ]
                    dal.add_bone_driver(self._armature_object, bone_name, "hide", expression, variables)

    def _populate_marker_objects_by_role(self):
        """Populates the _marker_objects_by_role dictionary by reading custom properties."""
        self._marker_objects_by_role = {}
        for marker_obj_ref in dal.get_children_of_object(self.view_root_object):
            marker_role = dal.get_custom_property(marker_obj_ref, dal.MARKER_ROLE)
            if marker_role:
                self._marker_objects_by_role[marker_role] = marker_obj_ref

    def connect_to_series(self, marker_data: MarkerData):
        """Connects this view to a MarkerData series.

        This applies the animation data from the series to the marker objects
        in this view.

        Args:
            marker_data: The MarkerData series to connect to.
        """
        marker_data.apply_to_view(self)
        dal.set_custom_property(
            self.view_root_object,
            dal.MARKER_DATA_ID,
            marker_data.data_series_object_name
        )

    def get_data_series(self) -> Optional["MarkerData"]:
        """Returns the MarkerData series connected to this view."""
        marker_data_id = dal.get_custom_property(self.view_root_object, dal.MARKER_DATA_ID)
        if not marker_data_id:
            return None
        md_obj = dal.get_object_by_name(marker_data_id)
        if not md_obj:
            return None
        return MarkerData.from_blender_object(md_obj)

    def get_marker_objects(self) -> dict[str, dal.BlenderObjRef]:
        """Returns a dictionary of marker objects in this view, keyed by their role."""
        return self._marker_objects_by_role

    def shift(self, delta_frames: int):
        """Shifts all marker data by the given number of frames.

        Args:
            delta_frames: The number of frames to shift. Positive values shift
                          forward in time, negative values shift backward.
        """
        if delta_frames == 0:
            return

        marker_data = self.get_data_series()
        if not marker_data:
            print(f"PersonDataView {self.view_name} is not connected to any MarkerData series.")
            return
        marker_data.shift(delta_frames)

    def _check_and_update_frame(self, scene, depsgraph):
        """Placeholder for the frame change callback logic."""
        # This method will be implemented in Phase 2
        pass