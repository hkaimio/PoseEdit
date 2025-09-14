# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for the Person3DView module."""

from unittest.mock import MagicMock, patch, call

from anytree import Node

from pose_editor.blender import dal
from pose_editor.core.person_3d_view import Person3DView


@patch("pose_editor.core.person_3d_view.dal3d")
@patch("pose_editor.core.person_3d_view.dal")
def test_create_new(mock_dal, mock_dal3d):
    """Test that Person3DView.create_new calls the correct DAL functions."""
    # Arrange
    # Mock a skeleton with virtual joints
    mock_skeleton = MagicMock()
    root = Node("Root", id=0)
    lhip = Node("LHip", parent=root, id=1)
    rhip = Node("RHip", parent=root, id=2)
    hip = Node("Hip", parent=root, id=None)  # Virtual
    lshoulder = Node("LShoulder", parent=root, id=3)
    rshoulder = Node("RShoulder", parent=root, id=4)
    neck = Node("Neck", parent=root, id=None)  # Virtual
    mock_skeleton._skeleton = root

    # Mock parent object and collection
    mock_parent_ref = MagicMock(name="ParentRef")
    mock_root_ref = MagicMock(spec=dal.BlenderObjRef)
    mock_root_ref.name = "Test3DView"
    mock_armature_ref = MagicMock(name="ArmatureRef")

    # Configure get_or_create_object to return the root ref first, then the armature ref
    mock_dal.get_or_create_object.side_effect = [mock_root_ref, mock_armature_ref]

    # The root object needs a collection for the markers to be placed in
    mock_root_obj = MagicMock()
    mock_root_obj.users_collection = [MagicMock()]
    mock_root_ref._get_obj.return_value = mock_root_obj

    # Mock marker objects returned by DAL to test armature/driver creation
    marker_mocks = {
        "Root": MagicMock(name="PV_Root"),
        "LHip": MagicMock(name="PV_LHip"),
        "RHip": MagicMock(name="PV_RHip"),
        "Hip": MagicMock(name="PV_Hip"),
        "LShoulder": MagicMock(name="PV_LShoulder"),
        "RShoulder": MagicMock(name="PV_RShoulder"),
        "Neck": MagicMock(name="PV_Neck"),
    }
    mock_dal3d.create_sphere_marker.side_effect = lambda parent, name, **kwargs: marker_mocks[name]
    mock_dal.create_empty.side_effect = lambda name, **kwargs: marker_mocks[name.split("_")[-1]]

    # Act
    Person3DView.create_new(
        view_name="Test3DView",
        skeleton=mock_skeleton,
        color=(1, 0, 0, 1),
        parent_ref=mock_parent_ref,
    )

    # Assert
    # Check root and armature object creation calls
    mock_dal.get_or_create_object.assert_has_calls([
        call(name="Test3DView", obj_type="EMPTY", collection_name="PersonViews", parent=mock_parent_ref),
        call(name="Test3DView_Armature", obj_type="ARMATURE", collection_name="PersonViews", parent=mock_root_ref)
    ])

    # Marker creation
    assert mock_dal3d.create_sphere_marker.call_count == 5  # Root, LHip, RHip, LShoulder, RShoulder
    assert mock_dal.create_empty.call_count == 2  # Hip, Neck

    # Armature creation details
    mock_dal.add_bones_in_bulk.assert_called_once()
    assert mock_dal.add_bone_constraint.call_count == 12  # 6 nodes with parents = 6 bones, 6 * 2 constraints

    # Driver creation
    assert mock_dal3d.add_object_driver.call_count == 6  # 2 virtual joints * 3 axes
    hip_marker_ref = marker_mocks["Hip"]
    lhip_marker_ref = marker_mocks["LHip"]
    rhip_marker_ref = marker_mocks["RHip"]
    expected_vars = [
        ("var1", "TRANSFORMS", lhip_marker_ref.name, 'location.x'),
        ("var2", "TRANSFORMS", rhip_marker_ref.name, 'location.x'),
    ]
    mock_dal3d.add_object_driver.assert_any_call(hip_marker_ref, "location", "(var1 + var2) / 2", expected_vars, index=0)
