# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import numpy as np
from typing import List, Optional, Tuple, Any

# No direct 'import bpy' here! All Blender interactions go through the DAL.
from ..blender import dal

class MarkerData:
    """A facade for a marker data series (model layer).

    Manages a DataSeries Empty and its associated slotted Action, providing
    methods to set and retrieve animation data without directly interacting
    with Blender's `bpy` module.
    """

    def __init__(self, series_name: str, skeleton_name: Optional[str] = None):
        """Initializes the MarkerData object.

        This finds or creates the necessary Blender data-blocks (a DataSeries
        Empty and an Action) via the Data Access Layer.

        Args:
            series_name: A unique name for this data series (e.g., "cam1_person0_raw").
            skeleton_name: The name of the skeleton definition used for this data 
                           series (e.g., "HALPE_26").
        """
        self.series_name = series_name
        self.action_name = f"AC.{series_name}"
        self.data_series_object_name = f"DS.{series_name}"
        self.skeleton_name = skeleton_name

        # Find or create the DataSeries Empty that holds metadata
        self.data_series_object = dal.get_or_create_object(
            name=self.data_series_object_name,
            obj_type='EMPTY',
            collection_name='DataSeries'
        )
        # Set metadata on the Empty
        dal.set_custom_property(self.data_series_object, dal.SERIES_NAME, series_name)
        dal.set_custom_property(self.data_series_object, dal.SKELETON, skeleton_name)
        dal.set_custom_property(self.data_series_object, dal.ACTION_NAME, self.action_name)

        # Find or create the Action that holds the animation data
        self.action = dal.get_or_create_action(self.action_name)

    def set_animation_data(
        self,
        data: np.ndarray,
        columns: List[Tuple[str, str, int]], # (marker_name, property, index)
        start_frame: int = 0
    ):
        """Writes animation data from a NumPy array into the Action's F-Curves.

        It creates/updates keyframes in the appropriate slot for each marker.

        Args:
            data: A NumPy array with shape (frames, columns).
            columns: A list of (marker_name, property, index) tuples describing each column.
            start_frame: The starting frame for writing the animation data.
        """
        if self.action is None or data.size == 0 or not columns:
            return

        num_frames = data.shape[0]

        for col_idx, (marker_name, prop, index) in enumerate(columns):
            # Get or create the F-Curve on the action, targeted at the correct slot
            fcurve = dal.get_or_create_fcurve(
                action=self.action,
                slot_name=marker_name,
                data_path=prop,
                index=index
            )

            # Prepare keyframe data for this column
            keyframes = []
            for frame_offset in range(num_frames):
                frame = start_frame + frame_offset
                value = data[frame_offset, col_idx]
                keyframes.append((float(frame), float(value)))

            # Set keyframes using DAL
            dal.set_fcurve_keyframes(fcurve, keyframes)

    def set_animation_data_from_numpy(
        self,
        columns: List[Tuple[str, str, int]], # (marker_name, property, index)
        start_frame: int,
        data: np.ndarray
    ):
        """Writes animation data from a NumPy array into the Action's F-Curves.

        This is a high-performance method that passes the entire data array
        to the Data Access Layer for batch processing.

        Args:
            columns: A list of (marker_name, property, index) tuples describing each column.
            start_frame: The starting frame for writing the animation data.
            data: A NumPy array with shape (frames, columns).
        """
        if self.action is None:
            return
        dal.set_fcurves_from_numpy(self.action, columns, start_frame, data)

    def apply_to_view(self, person_data_view: "PersonDataView"):
        """Applies this data series' Action to a Person View hierarchy.

        This method iterates through all marker objects in the PersonDataView.
        For each marker, it assigns the shared Action and sets the marker-specific
        Action Slot to activate the correct animation.

        Args:
            person_data_view: The PersonDataView object containing the marker objects.
        """
        if self.action is None:
            # In a real application, might want to log a warning here
            return

        for marker_role, marker_obj_ref in person_data_view.get_marker_objects().items():
            if dal.action_has_slot(self.action, marker_role):
                dal.assign_action_to_object(marker_obj_ref, self.action, marker_role)