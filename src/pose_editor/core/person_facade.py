# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from .marker_data import MarkerData
from ..blender import dal
from typing import Optional

PERSON_DEFINITION_ID = dal.CustomProperty[str]("person_definition_id")
IS_REAL_PERSON_INSTANCE = dal.CustomProperty[bool]("is_real_person_instance")

class RealPersonInstanceFacade:
    """A facade for a Real Person Instance.

    Manages the master Empty object for a person and provides methods for
    stitching and managing their data across multiple camera views.
    """

    def __init__(self, person_instance_obj: dal.BlenderObjRef):
        self.obj = person_instance_obj

    def get_marker_data_for_view(self, view_name: str) -> Optional[MarkerData]:
        """Gets the MarkerData object for this person in a specific camera view."""
        # This is a placeholder implementation. A more robust version would
        # search through collections or use custom properties to find the correct
        # MarkerData object.
        series_name = f"{view_name}_person{self.obj.name}" # This assumes a naming convention
        return MarkerData(series_name)

    def assign_source_track_for_segment(
        self, 
        view_name: str, 
        source_track_index: int, 
        start_frame: int
    ):
        """Assigns a new source track for a segment of the timeline.

        This involves setting a keyframe on the `active_track_index` property
        and copying the animation data from the source track's action to this
        person's action for the determined frame range.

        Args:
            view_name: The name of the camera view to perform the stitch in.
            source_track_index: The integer index of the raw track to use as a source.
            start_frame: The frame at which the switch should occur.
        """
        pass # To be implemented