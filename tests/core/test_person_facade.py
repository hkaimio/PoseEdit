# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock, patch

import pytest

# By patching the dal module where it is imported, we can control its behavior
# for all classes that use it, like RealPersonInstanceFacade and MarkerData.


@pytest.fixture
def mock_skeleton():
    """Creates a mock SkeletonBase object with a simple hierarchy."""
    from anytree import Node

    mock_skeleton = MagicMock()

    mock_skeleton = MagicMock()
    mock_skeleton._skeleton = Node("COCO-133", id=-1, children=[Node("Nose", id=0), Node("LEye", id=1)])
    return mock_skeleton
    return mock_skeleton


@patch("pose_editor.core.person_facade.dal", autospec=True)
def test_find_next_stitch_frame(mock_dal):
    """Tests that the next keyframe is correctly identified."""
    from pose_editor.core.person_facade import RealPersonInstanceFacade

    # Arrange
    person_ref = MagicMock()
    person_ref.name = "Alice"
    facade = RealPersonInstanceFacade(person_ref)

    mock_dal.get_object_by_name.return_value = MagicMock()  # Ensure ds_obj is not None
    mock_dal.get_fcurve_on_object.return_value = MagicMock()
    mock_dal.get_fcurve_keyframes.return_value = [(1.0, 0.0), (50.0, 1.0), (100.0, 2.0)]
    mock_dal.get_scene_frame_range.return_value = (1, 250)

    # Act
    next_frame = facade.find_next_stitch_frame("cam1", 50)

    # Assert
    assert next_frame == 99  # The segment should end the frame before the next keyframe


@patch("pose_editor.core.person_facade.dal", autospec=True)
def test_find_next_stitch_frame_no_future_keys(mock_dal):
    """Tests that the scene end frame is used when no future keyframes exist."""
    from pose_editor.core.person_facade import RealPersonInstanceFacade

    # Arrange
    person_ref = MagicMock()
    person_ref.name = "Alice"
    view_name = "cam1"
    facade = RealPersonInstanceFacade(person_ref)

    mock_dal.get_object_by_name.return_value = MagicMock()
    mock_dal.get_fcurve_on_object.return_value = MagicMock()
    mock_dal.get_fcurve_keyframes.return_value = [(1.0, 0.0), (50.0, 1.0)]
    mock_dal.get_scene_frame_range.return_value = (1, 250)

    # Act
    next_frame = facade.find_next_stitch_frame("cam1", 50)

    # Assert
    assert next_frame == 250

    # Mock dal.get_or_create_object to prevent TypeError when setting parent
    mock_blender_obj_ref_with_parent = MagicMock()
    mock_blender_obj_ref_with_parent._get_obj.return_value = MagicMock()
    mock_blender_obj_ref_with_parent._get_obj().parent = MagicMock()  # Allow parent to be set
    mock_dal.get_or_create_object.return_value = mock_blender_obj_ref_with_parent

    # Mock dal.get_object_by_name to return a mock BlenderObjRef with custom properties
    mock_pv_root_obj_ref = MagicMock()
    mock_pv_root_obj_ref.name = f"PV.{person_ref.name}.{view_name}"
    mock_pv_root_obj_ref._get_obj.return_value = MagicMock()
    mock_pv_root_obj_ref._get_obj().get.side_effect = (
        lambda prop: "PersonDataView" if prop == mock_dal.POSE_EDITOR_OBJECT_TYPE else None
    )
    mock_dal.get_object_by_name.return_value = mock_pv_root_obj_ref

    # Mock dal.get_or_create_object in person_data_view.py
    mock_dal.get_or_create_object.return_value = mock_blender_obj_ref_with_parent
