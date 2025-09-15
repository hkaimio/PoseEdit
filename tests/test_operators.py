# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock, patch

import bpy
import pytest

from pose_editor import register, unregister  # Import register/unregister
from pose_editor.core.person_facade import IS_REAL_PERSON_INSTANCE


@pytest.fixture
def clean_blender_scene():
    """Fixture to ensure a clean Blender scene for each test."""
    # Clear all objects
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    # Clear all collections except the master collection
    for collection in bpy.data.collections:
        if collection.name != "Collection":  # Default master collection
            bpy.data.collections.remove(collection)
    yield
    # Clean up after test (optional, as fixture runs before each test)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in bpy.data.collections:
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)


@pytest.fixture(autouse=True)
def register_addon():
    """Fixture to register and unregister the add-on for tests."""
    register()
    yield
    unregister()


def test_create_project_operator(clean_blender_scene):
    """
    Tests that the PE_OT_CreateProject operator creates the expected collections and empty.
    """
    # Run the operator
    bpy.ops.pose_editor.create_project()

    # Assert collections are created
    assert "Camera Views" in bpy.data.collections
    assert "Real Persons" in bpy.data.collections

    # Assert _ProjectSettings empty is created
    assert "_ProjectSettings" in bpy.data.objects
    project_settings_empty = bpy.data.objects["_ProjectSettings"]
    assert project_settings_empty.type == "EMPTY"

    # Assert collections are linked to master collection
    master_collection_children_names = [
        c.name for c in bpy.context.scene.collection.children
    ]
    assert "Camera Views" in master_collection_children_names
    assert "Real Persons" in master_collection_children_names

    # Assert _ProjectSettings empty is linked to master collection
    assert project_settings_empty.users_collection[0] == bpy.context.scene.collection


class MockLocation:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.z = 0


@patch("pose_editor.blender.operators.PE_OT_AddPersonInstance._update_ui_state")
@patch("pose_editor.blender.operators.CameraView")
@patch("pose_editor.blender.operators.PersonDataView")
@patch("pose_editor.blender.operators.MarkerData")
@patch("pose_editor.blender.operators.RealPersonInstanceFacade")
def test_add_person_instance_operator(
    mock_person_facade,
    mock_marker_data,
    mock_person_data_view,
    mock_camera_view,
    mock_update_ui,
    clean_blender_scene,
):
    """
    Tests that the PE_OT_AddPersonInstance operator creates a Real Person instance
    and its associated views, applying the correct offset.
    """
    # Arrange
    # 1. Mock RealPersonInstanceFacade.get_all() to return empty list (no existing persons)
    mock_person_facade.get_all.return_value = []

    # 2. Mock RealPersonInstanceFacade.create_new() to return a mock facade with .obj
    mock_person_obj_ref = MagicMock()
    mock_person_obj_ref.name = "Alice"
    mock_facade_instance = MagicMock()
    mock_facade_instance.obj = mock_person_obj_ref
    mock_facade_instance.name = "Alice"
    mock_person_facade.create_new.return_value = mock_facade_instance

    # 3. Mock CameraView.get_all() to return a mock CameraView instance
    mock_cam_view = MagicMock()
    mock_cam_view._obj.name = "View_cam1"
    mock_camera_view.get_all.return_value = [mock_cam_view]

    # 4. Mock PersonDataView.create_new to return a mock with a settable location
    mock_pv = MagicMock()
    mock_loc = MockLocation()
    mock_obj = MagicMock()
    mock_obj.location = mock_loc
    mock_pv.view_root_object._get_obj.return_value = mock_obj
    mock_person_data_view.create_new.return_value = mock_pv

    # Act
    bpy.ops.pose_editor.add_person_instance(person_name="Alice")

    # Assert
    # Check that the UI state update was called
    mock_update_ui.assert_called_once()

    # Check that RealPersonInstanceFacade.get_all was called to check for existing person
    mock_person_facade.get_all.assert_called_once()

    # Check that RealPersonInstanceFacade.create_new was called to create the person
    mock_person_facade.create_new.assert_called_once_with("Alice")

    # Check that PersonDataView was created for the camera view
    mock_person_data_view.create_new.assert_called_once()