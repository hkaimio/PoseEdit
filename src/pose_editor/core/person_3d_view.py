# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for creating and managing the 3D visual representation of a person."""

from typing import Optional

from ..blender import dal
from .skeleton import SkeletonBase


class Person3DView:
    """A facade for a person's 3D data view.

    Manages a 'Person 3D View' root Empty and its hierarchy of marker objects
    (Spheres for real markers, Empties for virtual ones) and a connecting armature.
    """

    def __init__(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the Person3DView as a wrapper around an existing Blender object."""
        self.view_root_object = view_root_obj_ref
        # In a full implementation, this would read properties from the object.

    @classmethod
    def create_new(
        cls,
        view_name: str,
        skeleton: SkeletonBase,
        color: tuple[float, float, float, float],
        parent_ref: dal.BlenderObjRef,
    ) -> "Person3DView":
        """Creates a new Person3DView, including its Blender objects."""
        # Create the root Empty for this view, parented to the RealPersonInstance
        view_root_object = dal.get_or_create_object(
            name=view_name,
            obj_type="EMPTY",
            collection_name="PersonViews",  # Or a new "Person3DViews" collection
            parent=parent_ref,
        )

        # Set custom properties to identify this object
        dal.set_custom_property(view_root_object, dal.POSE_EDITOR_OBJECT_TYPE, "Person3DView")
        dal.set_custom_property(view_root_object, dal.SKELETON, skeleton._skeleton.name)
        dal.set_custom_property(view_root_object, dal.COLOR, color)

        # Create a temporary instance to call internal creation methods
        temp_instance = cls.__new__(cls)
        temp_instance.view_root_object = view_root_object
        temp_instance.skeleton = skeleton
        temp_instance.color = color
        temp_instance._marker_objects_by_role = {}

        # Create marker objects based on the skeleton definition
        temp_instance._create_marker_objects()

        # Create armature and bones
        temp_instance._create_armature()

        # Create drivers for virtual markers
        temp_instance._create_drivers()

        # Return a properly initialized instance
        return cls(view_root_object)

    def _create_marker_objects(self):
        """Creates a marker object for each joint in the skeleton."""
        from anytree import PreOrderIter

        collection = self.view_root_object._get_obj().users_collection[0]

        for node in PreOrderIter(self.skeleton._skeleton):
            marker_name = node.name
            # Check if the joint is a real, tracked one or a virtual one
            if hasattr(node, "id") and node.id is not None:
                # TODO: Implement dal.create_sphere_marker
                # marker_ref = dal.create_sphere_marker(
                #     parent=self.view_root_object,
                #     name=marker_name,
                #     color=self.color,
                #     collection=collection,
                # )
                pass  # Placeholder
            else:
                # Virtual marker (e.g., Hip, Neck)
                marker_ref = dal.create_empty(
                    name=marker_name,
                    collection=collection,
                    parent_obj=self.view_root_object,
                )
            # self._marker_objects_by_role[marker_name] = marker_ref

    def _create_armature(self):
        """Creates an armature with bones connecting the markers."""
        # TODO: Implement armature creation, similar to PersonDataView
        # 1. Collect bone data (name, head_marker, tail_marker)
        # 2. Call dal.add_bones_in_bulk
        # 3. Loop again to add constraints (COPY_LOCATION, STRETCH_TO)
        pass

    def _create_drivers(self):
        """Creates drivers for the virtual markers."""
        # TODO: Implement driver creation
        # 1. Identify virtual markers (e.g., Hip, Neck)
        # 2. Get the source markers (e.g., RHip, LHip)
        # 3. Construct driver expression and variables
        # 4. Call a new dal.add_object_driver function
        pass