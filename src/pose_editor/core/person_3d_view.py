# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for creating and managing the 3D visual representation of a person."""

from typing import Optional

from anytree import PreOrderIter

from ..blender import dal, dal3d
from .skeleton import SkeletonBase


class Person3DView:
    """A facade for a person's 3D data view.

    Manages a 'Person 3D View' root Empty and its hierarchy of marker objects
    (Spheres for real markers, Empties for virtual ones) and a connecting armature.
    """

    def __init__(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the Person3DView as a wrapper around an existing Blender object."""
        self.view_root_object = view_root_obj_ref
        self.skeleton: Optional[SkeletonBase] = None
        self.color: Optional[tuple[float, float, float, float]] = None
        self._marker_objects_by_role: dict[str, dal.BlenderObjRef] = {}

        # In a full implementation, this would read all properties from the object
        # and populate the marker dictionary.

    @classmethod
    def create_new(
        cls,
        view_name: str,
        skeleton: SkeletonBase,
        color: tuple[float, float, float, float],
        parent_ref: dal.BlenderObjRef,
    ) -> "Person3DView":
        """Creates a new Person3DView, including its Blender objects."""
        view_root_object = dal.get_or_create_object(
            name=view_name,
            obj_type="EMPTY",
            collection_name="PersonViews",
            parent=parent_ref,
        )

        dal.set_custom_property(view_root_object, dal.POSE_EDITOR_OBJECT_TYPE, "Person3DView")
        dal.set_custom_property(view_root_object, dal.SKELETON, skeleton._skeleton.name)
        dal.set_custom_property(view_root_object, dal.COLOR, color)

        temp_instance = cls.__new__(cls)
        temp_instance.view_root_object = view_root_object
        temp_instance.skeleton = skeleton
        temp_instance.color = color
        temp_instance._marker_objects_by_role = {}

        temp_instance._create_marker_objects()
        temp_instance._create_armature()
        temp_instance._create_drivers()

        return cls(view_root_object)

    def _create_marker_objects(self):
        """Creates a marker object for each joint in the skeleton."""
        collection = self.view_root_object._get_obj().users_collection[0]

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
        # This implementation is based on the design for COCO133 skeleton.
        # A more generic solution would require a data-driven way to define these relationships.

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

            for i, axis in enumerate(["x", "y", "z"]):
                expression = f"(var1 + var2) / 2"
                variables = [
                    ("var1", "TRANSFORMS", source1.name, f'location.{axis}'),
                    ("var2", "TRANSFORMS", source2.name, f'location.{axis}'),
                ]
                dal3d.add_object_driver(virtual_marker, "location", expression, variables, index=i)
