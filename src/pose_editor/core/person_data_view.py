# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from typing import List

from .marker_data import MarkerData
from .skeleton import SkeletonBase
from ..blender import dal
from anytree import Node, RenderTree

class PersonDataView:
    """A facade for a person's 2D data view (View layer).

    Manages a 'Person View' root Empty and its hierarchy of marker Empties,
    which visually represent the animation data from a MarkerData series.
    """

    def __init__(self, view_name: str, skeleton: SkeletonBase, color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)):
        """Initializes the PersonDataView.

        This finds or creates the necessary Blender objects for the view
        hierarchy (a root Empty and child Empties for each marker in the
        skeleton) via the Data Access Layer.

        Args:
            view_name: A unique name for this person view (e.g., "PV.Alice.cam1").
            skeleton: The skeleton definition to use for creating marker objects.
            color: The color for the markers (RGBA tuple).
        """
        self.view_name = view_name
        self.skeleton = skeleton
        self.color = color
        self._marker_objects_by_role = {} # New dictionary to store markers by role

        # Find or create the root Empty for this view
        self.view_root_object = dal.get_or_create_object(
            name=self.view_name,
            obj_type='EMPTY',
            collection_name='PersonViews'
        )
        dal.set_custom_property(self.view_root_object, dal.SKELETON, skeleton._skeleton.name)

        # Create marker objects based on the skeleton definition
        print("Creating marker objects...")
        self._create_marker_objects()
        # Populate the dictionary after creating markers
        print("Populating marker objects by role...")
        self._populate_marker_objects_by_role()

        # Create armature and bones
        print("Creating armature...")
        self._create_armature()

    def _create_marker_objects(self):
        """Creates a marker object for each joint in the skeleton."""
        if self.skeleton is None or self.skeleton._skeleton is None:
            return

        from anytree import PreOrderIter
        for node in PreOrderIter(self.skeleton._skeleton):
            if not (hasattr(node, 'id') and node.id is not None):
                continue

            marker_name = node.name
            dal.create_marker(
                parent=self.view_root_object,
                name=marker_name,
                color=self.color
            )

    def _create_armature(self):
        """Creates an armature with bones connecting the markers."""
        armature_name = f"{self.view_name}_Armature"
        self.armature_object = dal.get_or_create_object(
            name=armature_name,
            obj_type='ARMATURE',
            collection_name='PersonViews',
            parent=self.view_root_object
        )
        self.armature_object._get_obj().color = self.color

        dal.set_armature_display_stick(self.armature_object)

        for node in self.skeleton._skeleton.descendants:
            if node.parent and hasattr(node, 'id') and node.id is not None and hasattr(node.parent, 'id') and node.parent.id is not None:
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                parent_marker = self._marker_objects_by_role.get(parent_marker_role)
                child_marker = self._marker_objects_by_role.get(child_marker_role)

                if parent_marker and child_marker:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    dal.add_bone(self.armature_object, bone_name, (0, 0, 0), (0, 1, 0))

                    dal.add_bone_constraint(self.armature_object, bone_name, 'COPY_LOCATION', parent_marker)
                    dal.add_bone_constraint(self.armature_object, bone_name, 'STRETCH_TO', child_marker)

                    # Add driver to hide bone
                    expression = "var1 or var2"
                    variables = [
                        ('var1', 'SINGLE_PROP', parent_marker.name, 'hide_viewport'),
                        ('var2', 'SINGLE_PROP', child_marker.name, 'hide_viewport')
                    ]
                    dal.add_bone_driver(self.armature_object, bone_name, 'hide', expression, variables)

    def _create_marker_objects(self):
        """Creates a marker object for each joint in the skeleton."""
        if self.skeleton is None or self.skeleton._skeleton is None:
            return

        from anytree import PreOrderIter
        for node in PreOrderIter(self.skeleton._skeleton):
            if not hasattr(node, 'id'):
                continue

            marker_name = node.name
            dal.create_marker(
                parent=self.view_root_object,
                name=marker_name,
                color=self.color
            )

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

    def get_marker_objects(self) -> dict[str, dal.BlenderObjRef]:
        """Returns a dictionary of marker objects in this view, keyed by their role."""
        return self._marker_objects_by_role
