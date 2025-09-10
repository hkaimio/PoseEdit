# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
from unittest.mock import MagicMock, patch, call
from anytree import Node

# Mock the dal module before importing the class to be tested
@pytest.fixture(autouse=True)
def mock_dal_module():
    with patch.dict('sys.modules', {'pose_editor.blender.dal': MagicMock()}):
        yield

@pytest.fixture
def mock_skeleton():
    """Creates a mock SkeletonBase object with a simple hierarchy."""
    root = Node("RootNode", id=-1)
    nose = Node("Nose", parent=root, id=0)
    leye = Node("LEye", parent=root, id=1)
    mock = MagicMock()
    mock._skeleton = root
    return mock

@pytest.fixture
def mock_marker_data():
    """Creates a mock MarkerData object."""
    return MagicMock()

@pytest.fixture
def mock_blender_obj_ref():
    """Creates a mock Blender object reference."""
    mock_ref = MagicMock()
    mock_ref.name = "MockBlenderObj"
    return mock_ref

class TestPersonDataView:

    @patch('pose_editor.core.person_data_view.dal')
    def test_init_creates_objects(self, mock_dal, mock_skeleton, mock_blender_obj_ref):
        """Test that __init__ creates the root empty and child marker empties."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        mock_dal.get_or_create_object.return_value = mock_blender_obj_ref

        # Act
        view = PersonDataView(view_name, mock_skeleton)

        # Assert
        # Check that the root object was created
        mock_dal.get_or_create_object.assert_any_call(
            name=view_name,
            obj_type='EMPTY',
            collection_name='PersonViews'
        )

        # Check that custom property was set on the root
        mock_dal.set_custom_property.assert_called_once_with(
            mock_blender_obj_ref, mock_dal.SKELETON, mock_skeleton._skeleton.name
        )

        # Check that child marker objects were created
        expected_marker_calls = [
            call(name="Nose", obj_type='EMPTY', parent=mock_blender_obj_ref),
            call(name="LEye", obj_type='EMPTY', parent=mock_blender_obj_ref),
        ]
        mock_dal.get_or_create_object.assert_has_calls(expected_marker_calls, any_order=True)
        # Total calls: 1 for root + 2 for markers
        assert mock_dal.get_or_create_object.call_count == 3

    @patch('pose_editor.core.person_data_view.dal')
    def test_connect_to_series(self, mock_dal, mock_skeleton, mock_marker_data):
        """Test that connect_to_series calls apply_to_view on the marker data object."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        view = PersonDataView(view_name, mock_skeleton)

        # Act
        view.connect_to_series(mock_marker_data)

        # Assert
        mock_marker_data.apply_to_view.assert_called_once_with(view_name)

    @patch('pose_editor.core.person_data_view.dal')
    def test_get_marker_objects(self, mock_dal, mock_skeleton, mock_blender_obj_ref):
        """Test that get_marker_objects returns the children from the DAL."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        mock_dal.get_or_create_object.return_value = mock_blender_obj_ref
        view = PersonDataView(view_name, mock_skeleton)

        mock_children = [MagicMock(), MagicMock()]
        mock_dal.get_children_of_object.return_value = mock_children

        # Act
        children = view.get_marker_objects()

        # Assert
        assert children == mock_children
        mock_dal.get_children_of_object.assert_called_once_with(mock_blender_obj_ref)
