# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for creating and managing the 3D visual representation of a person."""

from typing import TYPE_CHECKING, Optional

from anytree import PreOrderIter

from ..blender import dal, dal3d
from .calibration import Calibration
from .marker_data import MarkerData
from .skeleton import SkeletonBase, get_skeleton

if TYPE_CHECKING:
    from .person_facade import RealPersonInstanceFacade


class Person3DView:
    """A facade for a person's 3D data view.

    Manages a 'Person 3D View' root Empty and its hierarchy of marker objects
    (Spheres for real markers, Empties for virtual ones) and a connecting armature.
    """

    def __init__(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the Person3DView as a wrapper around an existing Blender object."""
        self._init_from_blender_ref(view_root_obj_ref)

    def _init_from_blender_ref(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the instance from an existing Blender object reference."""
        self.view_root_object = view_root_obj_ref
        self.skeleton: Optional[SkeletonBase] = None
        self.color: Optional[tuple[float, float, float, float]] = None
        self._marker_objects_by_role: dict[str, dal.BlenderObjRef] = {}

        skeleton_name = dal.get_custom_property(view_root_obj_ref, dal.SKELETON)
        if skeleton_name:
            self.skeleton = get_skeleton(skeleton_name)
        self.color = dal.get_custom_property(view_root_obj_ref, dal.COLOR)
        self._populate_marker_objects_by_role()

    def _populate_marker_objects_by_role(self):
        """Populates the marker dictionary by finding child objects with a MARKER_ROLE."""
        self._marker_objects_by_role = {}
        children = dal.get_children_of_object(self.view_root_object, recursive=False)
        for child_ref in children:
            role = dal.get_custom_property(child_ref, dal.MARKER_ROLE)
            if role:
                self._marker_objects_by_role[role] = child_ref

    @classmethod
    def from_blender_object(cls, view_root_obj_ref: dal.BlenderObjRef) -> Optional["Person3DView"]:
        """Builds a Person3DView from an existing Blender object."""
        if not view_root_obj_ref or not view_root_obj_ref._get_obj():
            return None
        obj_type = dal.get_custom_property(view_root_obj_ref, dal.POSE_EDITOR_OBJECT_TYPE)
        if obj_type != "Person3DView":
            return None
        return cls(view_root_obj_ref)

    @classmethod
    def get_for_person(cls, person: "RealPersonInstanceFacade") -> Optional["Person3DView"]:
        """Finds the Person3DView for a given RealPersonInstanceFacade."""
        from .person_facade import PERSON_DEFINITION_REF

        all_3d_views = dal.find_all_objects_by_property(dal.POSE_EDITOR_OBJECT_TYPE, "Person3DView")
        for view_ref in all_3d_views:
            person_id = dal.get_custom_property(view_ref, PERSON_DEFINITION_REF)
            if person_id == person.obj._id:
                return cls.from_blender_object(view_ref)
        return None

    def get_person(self) -> Optional["RealPersonInstanceFacade"]:
        """Returns the RealPersonInstanceFacade associated with this view."""
        from .person_facade import PERSON_DEFINITION_REF, RealPersonInstanceFacade

        person_id = dal.get_custom_property(self.view_root_object, PERSON_DEFINITION_REF)
        if not person_id:
            return None
        person_obj_ref = dal.get_object_by_name(person_id)
        if not person_obj_ref:
            return None
        return RealPersonInstanceFacade.from_blender_obj(person_obj_ref)

    @classmethod
    def create_new(
        cls,
        view_name: str,
        skeleton: SkeletonBase,
        color: tuple[float, float, float, float],
        parent_ref: dal.BlenderObjRef,
        person: Optional["RealPersonInstanceFacade"] = None,
    ) -> "Person3DView":
        """Creates a new Person3DView, including its Blender objects."""
        from .person_facade import PERSON_DEFINITION_REF

        view_root_object = dal.get_or_create_object(
            name=view_name,
            obj_type="EMPTY",
            collection_name="PersonViews",
            parent=parent_ref,
        )

        dal.set_custom_property(view_root_object, dal.POSE_EDITOR_OBJECT_TYPE, "Person3DView")
        dal.set_custom_property(view_root_object, dal.SKELETON, skeleton.name)
        dal.set_custom_property(view_root_object, dal.COLOR, color)
        dal.set_custom_property(view_root_object, PERSON_DEFINITION_REF, person.obj._id if person and person.obj else "")

        instance = cls(view_root_object)
        instance.skeleton = skeleton
        instance.color = color
        instance._marker_objects_by_role = {}

        instance._create_marker_objects()
        instance._create_armature()
        instance._create_drivers()

        return instance

    def get_marker_objects(self) -> dict[str, dal.BlenderObjRef]:
        """Returns a dictionary of marker objects in this view, keyed by their role."""
        return self._marker_objects_by_role

    def connect_to_series(self, marker_data: MarkerData):
        """Connects the marker objects in this view to a MarkerData action.

        Args:
            marker_data: The MarkerData instance containing the animation action.
        """
        if not marker_data or not marker_data.action:
            print(f"Warning: Cannot connect Person3DView to an invalid MarkerData series.")
            return

        # Store the ID of the MarkerData this view is connected to
        dal.set_custom_property(self.view_root_object, dal.MARKER_DATA_ID, marker_data._obj._id)

        # Assign the action to each marker object, targeting the correct slot
        for role, marker_obj_ref in self._marker_objects_by_role.items():
            dal.assign_action_to_object(marker_obj_ref, marker_data.action, slot_name=role)

        print(f"Connected 3D view '{self.view_root_object.name}' to action '{marker_data.action.name}'.")

    def _create_marker_objects(self):
        """Creates a marker object for each joint in the skeleton."""
        collection = self.view_root_object._get_obj().users_collection[0]
        calibration = Calibration()
        all_camera_names = calibration.get_camera_names() if calibration._data else []

        for node in PreOrderIter(self.skeleton._skeleton):
            marker_name = node.name
            marker_ref = None
            if hasattr(node, "id") and node.id is not None:
                marker_ref = dal3d.create_sphere_marker(
                    parent=self.view_root_object,
                    name=marker_name,
                    color=self.color,
                    collection=collection,
                )
            else:
                marker_ref = dal.create_empty(
                    name=f"{self.view_root_object.name}_{marker_name}",
                    collection=collection,
                    parent_obj=self.view_root_object,
                )

            # Initialize all custom properties that will be driven by F-Curves
            dal.set_custom_property(marker_ref, dal.MARKER_ROLE, marker_name)
            marker_obj = marker_ref._get_obj()
            marker_obj["reprojection_error"] = 0.0
            marker_obj["contributing_cam_count"] = 0
            for cam_name in all_camera_names:
                marker_obj[f"contrib_{cam_name}"] = False

            self._marker_objects_by_role[marker_name] = marker_ref

    def _create_armature(self):
        """Creates an armature with bones connecting the markers."""
        armature_name = f"{self.view_root_object.name}_Armature"
        armature_object = dal.get_or_create_object(
            name=armature_name, obj_type="ARMATURE", collection_name="PersonViews", parent=self.view_root_object
        )
        armature_object._get_obj().color = self.color
        dal.set_armature_display_stick(armature_object)

        bones_to_add = []
        for node in PreOrderIter(self.skeleton._skeleton):
            if node.parent:
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                if parent_marker_role in self._marker_objects_by_role and child_marker_role in self._marker_objects_by_role:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    bones_to_add.append((bone_name, (0, 0, 0), (0, 1, 0)))

        if bones_to_add:
            dal.add_bones_in_bulk(armature_object, bones_to_add)

        for node in PreOrderIter(self.skeleton._skeleton):
            if node.parent:
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                parent_marker = self._marker_objects_by_role.get(parent_marker_role)
                child_marker = self._marker_objects_by_role.get(child_marker_role)

                if parent_marker and child_marker:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    dal.add_bone_constraint(armature_object, bone_name, "COPY_LOCATION", parent_marker)
                    dal.add_bone_constraint(armature_object, bone_name, "STRETCH_TO", child_marker)

    def _create_drivers(self):
        """Creates drivers for the virtual markers based on hardcoded rules."""
        virtual_definitions = {
            "Hip": ("LHip", "RHip"),
            "Neck": ("LShoulder", "RShoulder"),
        }

        for virtual_name, (source1_name, source2_name) in virtual_definitions.items():
            virtual_marker = self._marker_objects_by_role.get(virtual_name)
            source1 = self._marker_objects_by_role.get(source1_name)
            source2 = self._marker_objects_by_role.get(source2_name)

            if not (virtual_marker and source1 and source2):
                continue

            dal3d.add_midpoint_driver(
                target_obj_ref=virtual_marker, source_a_ref=source1, source_b_ref=source2
            )
