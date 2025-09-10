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
        from pose_editor.blender.dal import BlenderObjRef # Import BlenderObjRef

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0) # Example color
        mock_dal.get_or_create_object.return_value = mock_blender_obj_ref

        # Act
        view = PersonDataView(view_name, mock_skeleton, color=marker_color)

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

        # Check that child marker objects were created using dal.create_marker
        expected_marker_calls = [
            call(parent=mock_blender_obj_ref, name="Nose", color=marker_color),
            call(parent=mock_blender_obj_ref, name="LEye", color=marker_color),
        ]
        mock_dal.create_marker.assert_has_calls(expected_marker_calls, any_order=True)
        # Total calls: 1 for root (get_or_create_object) + 2 for markers (create_marker)
        assert mock_dal.get_or_create_object.call_count == 1
        assert mock_dal.create_marker.call_count == 2

        # Assert that _populate_marker_objects_by_role was called and populated correctly
        # Mock the return value for get_children_of_object and get_custom_property
        mock_nose_marker_ref = BlenderObjRef("Nose_marker_obj")
        mock_leye_marker_ref = BlenderObjRef("LEye_marker_obj")
        mock_dal.get_children_of_object.return_value = [mock_nose_marker_ref, mock_leye_marker_ref]
        mock_dal.get_custom_property.side_effect = lambda obj_ref, prop: "Nose" if obj_ref.name == "Nose_marker_obj" else "LEye"

        # Re-run the population logic (it's called in __init__, but we need to mock its dependencies)
        view._populate_marker_objects_by_role()

        assert view.get_marker_objects() == {
            "Nose": mock_nose_marker_ref,
            "LEye": mock_leye_marker_ref
        }
                # Assert that _populate_marker_objects_by_role was called and populated correctly
        assert view.get_marker_objects() == {
            "Nose": mock_nose_marker_ref,
            "LEye": mock_leye_marker_ref
        }
        mock_dal.get_children_of_object.assert_called_with(mock_blender_obj_ref)
        mock_dal.get_custom_property.assert_has_calls([
            call(mock_nose_marker_ref, mock_dal.MARKER_ROLE),
            call(mock_leye_marker_ref, mock_dal.MARKER_ROLE)
        ], any_order=True)


    @patch('pose_editor.core.person_data_view.dal')
    def test_connect_to_series(self, mock_dal, mock_skeleton, mock_marker_data):
        """Test that connect_to_series calls apply_to_view on the marker data object."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0)
        mock_dal.get_or_create_object.return_value = MagicMock() # Mock root object for init

        # Mock the return values for _populate_marker_objects_by_role before init
        mock_nose_marker_ref = BlenderObjRef("Nose_marker_obj")
        mock_leye_marker_ref = BlenderObjRef("LEye_marker_obj")
        mock_dal.get_children_of_object.return_value = [mock_nose_marker_ref, mock_leye_marker_ref]
        mock_dal.get_custom_property.side_effect = lambda obj_ref, prop: "Nose" if obj_ref.name == "Nose_marker_obj" else "LEye"

        view = PersonDataView(view_name, mock_skeleton, color=marker_color)

        # Act
        view.connect_to_series(mock_marker_data)

        # Assert
        mock_marker_data.apply_to_view.assert_called_once_with(view_name)

    @patch('pose_editor.core.person_data_view.dal')
    def test_get_marker_objects(self, mock_dal, mock_skeleton, mock_blender_obj_ref):
        """Test that get_marker_objects returns the children from the DAL."""
        from pose_editor.core.person_data_view import PersonDataView
        from pose_editor.blender.dal import BlenderObjRef # Import BlenderObjRef

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0)
        mock_dal.get_or_create_object.return_value = mock_blender_obj_ref

        # Mock the return values for _populate_marker_objects_by_role before init
        mock_nose_marker_ref = BlenderObjRef("Nose_marker_obj")
        mock_leye_marker_ref = BlenderObjRef("LEye_marker_obj")
        mock_dal.get_children_of_object.return_value = [mock_nose_marker_ref, mock_leye_marker_ref]
        mock_dal.get_custom_property.side_effect = lambda obj_ref, prop: "Nose" if obj_ref.name == "Nose_marker_obj" else "LEye"

        view = PersonDataView(view_name, mock_skeleton, color=marker_color)

        # Act
        marker_objects_dict = view.get_marker_objects()

        # Assert
        assert marker_objects_dict == {
            "Nose": mock_nose_marker_ref,
            "LEye": mock_leye_marker_ref
        }
        # get_children_of_object is called once in __init__ and once in _populate_marker_objects_by_role
        assert mock_dal.get_children_of_object.call_count == 1 # Only called once in __init__ now

