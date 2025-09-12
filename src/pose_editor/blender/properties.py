# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy

def get_available_tracks(self, context):
    """Dynamically gets the list of raw tracks for the active camera view."""
    # This function will be filled in later. For now, it returns a placeholder.
    # In the final implementation, it will inspect the scene to find the
    # active view and list the `MarkerData` series associated with it.
    return [("-1", "-- Select a Track --", "")]

class StitchingUIItem(bpy.types.PropertyGroup):
    """Represents a single row in the stitching UI, for one RealPerson."""
    
    person_name: bpy.props.StringProperty(
        name="Person Name",
        description="The name of the RealPersonInstance this row controls"
    )

    # The `items` for this EnumProperty will be generated dynamically.
    selected_track: bpy.props.EnumProperty(
        name="Source Track",
        description="The raw track to use as a source for this person",
        items=get_available_tracks
    )

class StitchingUIState(bpy.types.PropertyGroup):
    """Holds the state for the entire stitching UI panel."""

    items: bpy.props.CollectionProperty(
        type=StitchingUIItem
    )

    active_camera_view: bpy.props.StringProperty(
        name="Active Camera View",
        description="The camera view currently being displayed in the UI"
    )