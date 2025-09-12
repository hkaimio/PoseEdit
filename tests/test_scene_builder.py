# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
import pytest

from pose_editor import register, unregister  # Import register/unregister
from pose_editor.blender import scene_builder


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


def test_create_project_structure(clean_blender_scene):
    """
    Tests that create_project_structure creates the expected collections and empty.
    """
    scene_builder.create_project_structure()

    # Assert collections are created
    assert "Camera Views" in bpy.data.collections
    assert "Real Persons" in bpy.data.collections

    # Assert _ProjectSettings empty is created
    assert "_ProjectSettings" in bpy.data.objects
    project_settings_empty = bpy.data.objects["_ProjectSettings"]
    assert project_settings_empty.type == "EMPTY"

    # Assert collections are linked to master collection
    master_collection_children_names = [c.name for c in bpy.context.scene.collection.children]
    assert "Camera Views" in master_collection_children_names
    assert "Real Persons" in master_collection_children_names

    # Assert _ProjectSettings empty is linked to master collection
    assert project_settings_empty.users_collection[0] == bpy.context.scene.collection
