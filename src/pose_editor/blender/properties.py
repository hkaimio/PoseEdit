# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
from ..blender import dal
import re

def get_available_tracks(self, context):
    """Dynamically gets the list of raw tracks for the active camera view."""
    items = [("-1", "-- Select a Track --", "")]
    
    if not context or not context.space_data or not context.space_data.camera:
        return items

    active_camera = context.space_data.camera
    if not active_camera.name.startswith("Cam_"):
        return items

    view_name = active_camera.name.replace("Cam_", "")
    view_obj = dal.get_object_by_name(f"View_{view_name}")
    if not view_obj:
        return items

    # Find all PersonDataView objects, which represent raw tracks
    raw_track_names = []
    for child in dal.get_children_of_object(view_obj):
        if child.name.startswith("PV."):
            raw_track_names.append(child.name)

    # Extract the person index from the name (e.g., "PV.cam1_person5" -> "5")
    for name in sorted(raw_track_names):
        match = re.search(r'person(\d+)$', name)
        if match:
            track_index = match.group(1)
            # The EnumProperty item format is (identifier, display_name, description)
            items.append((track_index, f"Person {track_index}", f"Use raw track from Person {track_index}"))
            
    return items

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
