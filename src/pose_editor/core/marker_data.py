# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause


import numpy as np

# No direct 'import bpy' here! All Blender interactions go through the DAL.
from ..blender import dal

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .camera_view import CameraView
    from .person_data_view import PersonDataView
    from .person_facade import RealPersonInstanceFacade

from ..blender.dal import CAMERA_VIEW_ID

class MarkerData:
    """A facade for a marker data series (model layer).

    Manages a DataSeries Empty and its associated slotted Action, providing
    methods to set and retrieve animation data without directly interacting
    with Blender's `bpy` module.

    Blender Representation:
    -   **Data-Block**: A Blender `Action` data-block (e.g., `AC.cam1_person0_raw`).
        This action stores all the F-Curves for the marker animations using the
        Slotted Actions API.
    -   **Scene Object**: A corresponding Empty object (e.g., `DS.cam1_person0_raw`)
        is created in the `DataSeries` collection to hold metadata about the
        action, such as its `series_name` and the `skeleton` type it uses.
    """

    def __init__(self, series_name: str, skeleton_name: str | None = None, action=None, data_series_object=None):
        """
        Initializes the MarkerData object as a runtime instance.

        Args:
            series_name: Unique name for this data series (e.g., "cam1_person0_raw").
            skeleton_name: Name of the skeleton definition used for this data series.
            action: Blender Action object associated with this data series.
            data_series_object: Blender Empty object holding metadata for this data series.
        """
        self.series_name = series_name
        self.action_name = f"AC.{series_name}"
        self.data_series_object_name = f"DS.{series_name}"
        self.skeleton_name = skeleton_name
        self.data_series_object = data_series_object
        self.action = action

    @classmethod
    def create_new(cls, series_name: str, skeleton_name: str | None = None, camera_view: "CameraView" = None, person: "RealPersonInstanceFacade" = None) -> "MarkerData":
        """
        Creates a new persistent MarkerData object in Blender.

        Args:
            series_name: Unique name for this data series.
            skeleton_name: Name of the skeleton definition used.

        Returns:
            MarkerData: The newly created MarkerData instance.
        """

        from .person_facade import PERSON_DEFINITION_REF

        data_series_object = dal.get_or_create_object(
            name=f"DS.{series_name}", obj_type="EMPTY", collection_name="DataSeries"
        )
        dal.set_custom_property(data_series_object, dal.SERIES_NAME, series_name)
        dal.set_custom_property(data_series_object, dal.SKELETON, skeleton_name if skeleton_name else "")
        dal.set_custom_property(data_series_object, dal.ACTION_NAME, f"AC.{series_name}")
        dal.set_custom_property(data_series_object, dal.POSE_EDITOR_OBJECT_TYPE, "MarkerData")
        camera_view_id = camera_view._obj.name if camera_view and camera_view._obj else ""
        dal.set_custom_property(data_series_object, CAMERA_VIEW_ID, camera_view_id)
        person_id = person.obj._id if person and person.obj else ""
        dal.set_custom_property(data_series_object, PERSON_DEFINITION_REF, person_id)

        action = dal.get_or_create_action(f"AC.{series_name}")

        return cls(series_name, skeleton_name, action=action, data_series_object=data_series_object)

    @classmethod
    def from_blender_object(cls, data_series_obj_ref: dal.BlenderObjRef) -> "MarkerData | None":
        """
        Initializes MarkerData from an existing Blender DataSeries object.

        Args:
            data_series_obj_ref: BlenderObjRef pointing to the DataSeries Empty.

        Returns:
            MarkerData | None: The initialized MarkerData instance, or None if not found.
        """
        if not data_series_obj_ref or not data_series_obj_ref._get_obj():
            return None

        series_name = dal.get_custom_property(data_series_obj_ref, dal.SERIES_NAME)
        if not series_name:
            return None
        skeleton_name = dal.get_custom_property(data_series_obj_ref, dal.SKELETON)
        action_name = dal.get_custom_property(data_series_obj_ref, dal.ACTION_NAME)
        action = dal.get_or_create_action(action_name) if action_name else None

        return cls(series_name, skeleton_name, action=action, data_series_object=data_series_obj_ref)

    def set_animation_data(
        self,
        data: np.ndarray,
        columns: list[tuple[str, str, int]],  # (marker_name, property, index)
        start_frame: int = 0,
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
            fcurve = dal.get_or_create_fcurve(action=self.action, slot_name=marker_name, data_path=prop, index=index)

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
        columns: list[tuple[str, str, int]],  # (marker_name, property, index)
        start_frame: int,
        data: np.ndarray,
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

    def shift(self, frame_delta: int):
        """Shifts the MarkerData timeline data in its action by frame_delta frames.
        
        Args:
            frame_delta: The number of frames to shift the animation data. Positive values
                         shift forward in time, negative values shift backward.
        """
        if self.action is not None:
            dal.shift_action(self.action, frame_delta)
