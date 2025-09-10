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

    def __init__(self, view_name: str, skeleton: SkeletonBase):
        """Initializes the PersonDataView.

        This finds or creates the necessary Blender objects for the view
        hierarchy (a root Empty and child Empties for each marker in the
        skeleton) via the Data Access Layer.

        Args:
            view_name: A unique name for this person view (e.g., "PV.Alice.cam1").
            skeleton: The skeleton definition to use for creating marker objects.
        """
        self.view_name = view_name
        self.skeleton = skeleton

        # Find or create the root Empty for this view
        self.view_root_object = dal.get_or_create_object(
            name=self.view_name,
            obj_type='EMPTY',
            collection_name='PersonViews'
        )
        dal.set_custom_property(self.view_root_object, dal.SKELETON, skeleton._skeleton.name)

        # Create marker objects based on the skeleton definition
        self._create_marker_objects()

    def _create_marker_objects(self):
        """Creates an Empty object for each joint in the skeleton."""
        if self.skeleton is None or self.skeleton._skeleton is None:
            return

        for node in self.skeleton._skeleton.descendants:
            marker_name = node.name
            dal.get_or_create_object(
                name=marker_name,
                obj_type='EMPTY',
                parent=self.view_root_object
            )

    def connect_to_series(self, marker_data: MarkerData):
        """Connects this view to a MarkerData series.

        This applies the animation data from the series to the marker objects
        in this view.

        Args:
            marker_data: The MarkerData series to connect to.
        """
        marker_data.apply_to_view(self.view_name)

    def get_marker_objects(self) -> List[any]:
        """Returns a list of all marker objects in this view."""
        return dal.get_children_of_object(self.view_root_object)
