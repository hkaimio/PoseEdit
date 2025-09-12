# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import patch

from pose_editor.blender import scene_builder


@patch("pose_editor.blender.dal.create_collection")
@patch("pose_editor.blender.dal.create_empty")
def test_create_project_structure_mocked(mock_create_empty, mock_create_collection):
    """
    Tests that create_project_structure calls DAL functions with correct arguments.
    """
    scene_builder.create_project_structure()

    # Assert create_collection is called for "Camera Views"
    mock_create_collection.assert_any_call("Camera Views")
    # Assert create_collection is called for "Real Persons"
    mock_create_collection.assert_any_call("Real Persons")
    # Assert create_empty is called for "_ProjectSettings"
    mock_create_empty.assert_called_once_with("_ProjectSettings")

    # Assert that create_collection was called twice in total
    assert mock_create_collection.call_count == 2
