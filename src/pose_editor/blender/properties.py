# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import re

import bpy

from ..blender import dal
from ..core.camera_view import CameraView
from ..core.person_facade import RealPersonInstanceFacade


def get_available_tracks(self, context):
    """Dynamically gets the list of raw tracks for the active camera view."""
    items = [
        ("-1", "-- Select a Track --", "Don't change the current track"),
        ("-2", "None", "Mark this segment as untracked (clears keyframes)"),
    ]

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
        match = re.search(r"person(\d+)$", name)
        if match:
            track_index = match.group(1)
            # The EnumProperty item format is (identifier, display_name, description)
            items.append((track_index, f"Person {track_index}", f"Use raw track from Person {track_index}"))

    return items


def update_view_start(self, context):
    """Update callback for the view_start property."""
    if not context.space_data.camera:
        return

    active_camera = context.space_data.camera
    if not active_camera.name.startswith("Cam_"):
        return

    view_name = active_camera.name.replace("Cam_", "")
    view_obj_ref = dal.get_object_by_name(f"View_{view_name}")
    if not view_obj_ref:
        return

    camera_view = CameraView.from_blender_obj(view_obj_ref)
    camera_view.set_start_frame(self.view_start)


class CameraViewSettings(bpy.types.PropertyGroup):
    """Properties for managing camera view settings."""

    view_start: bpy.props.IntProperty(
        name="Start Frame",
        description="The start frame of the camera view",
        default=1,
        update=update_view_start,
    )


class StitchingUIItem(bpy.types.PropertyGroup):
    """Represents a single row in the stitching UI, for one RealPerson."""

    person_name: bpy.props.StringProperty(
        name="Person Name", description="The name of the RealPersonInstance this row controls"
    )

    # The `items` for this EnumProperty will be generated dynamically.
    selected_track: bpy.props.EnumProperty(
        name="Source Track", description="The raw track to use as a source for this person", items=get_available_tracks
    )


class StitchingUIState(bpy.types.PropertyGroup):
    """Holds the state for the entire stitching UI panel."""

    items: bpy.props.CollectionProperty(type=StitchingUIItem)

    active_camera_view: bpy.props.StringProperty(
        name="Active Camera View", description="The camera view currently being displayed in the UI"
    )

def get_persons_for_enum(scene, context):
    """Returns a list of Real Persons for an EnumProperty."""
    items = []
    persons = RealPersonInstanceFacade.get_all()
    for i, person in enumerate(persons):
        items.append((person.name, person.name, f"Copy stitching for {person.name}", i))
    return items

def get_camera_views_for_enum(scene, context):
    """Returns a list of camera views for an EnumProperty."""
    items = []
    camera_views = CameraView.get_all()
    for i, view in enumerate(camera_views):
        items.append((view.name, view.name, f"Copy from {view.name}", i))
    return items


class CopyStitchingProperties(bpy.types.PropertyGroup):
    """Properties for the Copy Stitching operator."""
    source_camera: bpy.props.EnumProperty(
        name="Source Camera",
        description="The camera view to copy the stitching data from",
        items=get_camera_views_for_enum,
    )

    person_to_copy: bpy.props.EnumProperty(
        name="Person",
        description="The person whose stitching data will be copied",
        items=get_persons_for_enum,
    )


classes = [
    CameraViewSettings,
    StitchingUIItem,
    StitchingUIState,
    CopyStitchingProperties,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.camera_view_settings = bpy.props.PointerProperty(type=CameraViewSettings)
    bpy.types.Scene.pose_editor_stitching_ui = bpy.props.PointerProperty(type=StitchingUIState)
    bpy.types.Scene.pose_editor_copy_stitching = bpy.props.PointerProperty(type=CopyStitchingProperties)


def unregister():
    del bpy.types.Scene.pose_editor_copy_stitching
    del bpy.types.Scene.stitching_ui_state
    del bpy.types.Scene.camera_view_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
