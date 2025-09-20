from pose_editor.core.skeleton import COCO133Skeleton, SkeletonBase
from pose_editor.pose2sim import skeletons


import pytest
from pose_editor.core.skeleton import get_skeleton, SkeletonBase, COCO133Skeleton
from pose_editor.pose2sim import skeletons

def test_get_skeleton_definition_valid():
    # COCO_133 should exist and be a Node
    node = skeletons.get_skeleton_definition("COCO_133")
    from anytree import Node
    assert isinstance(node, Node)
    assert node.name == "Hip"

def test_get_skeleton_definition_invalid():
    with pytest.raises(ValueError) as excinfo:
        skeletons.get_skeleton_definition("NOT_A_SKELETON")
    assert "No skeleton definition found" in str(excinfo.value)

def test_get_skeleton_coco133():
    skel = get_skeleton("COCO_133")
    assert isinstance(skel, COCO133Skeleton)
    assert hasattr(skel, "_skeleton")
    assert skel.name == "COCO_133"

def test_get_skeleton_other_valid():
    # This test assumes another skeleton exists, e.g. "HALPE_26"
    # If not, you can skip or add a dummy skeleton for testing
    try:
        skel = get_skeleton("HALPE_26")
        assert isinstance(skel, SkeletonBase)
        assert skel.name == "HALPE_26"
    except ValueError:
        pytest.skip("HALPE_26 skeleton not defined in test environment")

def test_get_skeleton_invalid():
    with pytest.raises(ValueError) as excinfo:
        get_skeleton("NOT_A_SKELETON")
    assert "No skeleton definition found" in str(excinfo.value)

def test_get_joint_name_valid_id():
    """
    Test that get_joint_name returns the correct name for a valid ID.
    """
    skeleton = SkeletonBase(skeletons.HALPE_26)
    assert skeleton.get_joint_name(19) == "Hip"
    assert skeleton.get_joint_name(0) == "Nose"
    assert skeleton.get_joint_name(10) == "RWrist"


def test_get_joint_name_invalid_id():
    """
    Test that get_joint_name returns None for an invalid ID.
    """
    skeleton = SkeletonBase(skeletons.HALPE_26)
    assert skeleton.get_joint_name(999) is None
    assert skeleton.get_joint_name(-1) is None


def test_get_joint_id_valid_name():
    """
    Test that get_joint_id returns the correct ID for a valid name.
    """
    skeleton = SkeletonBase(skeletons.HALPE_26)
    assert skeleton.get_joint_id("Hip") == 19
    assert skeleton.get_joint_id("Nose") == 0
    assert skeleton.get_joint_id("RWrist") == 10


def test_get_joint_id_invalid_name():
    """
    Test that get_joint_id returns None for an invalid name.
    """
    skeleton = SkeletonBase(skeletons.HALPE_26)
    assert skeleton.get_joint_id("InvalidJoint") is None
    assert skeleton.get_joint_id("hip") is None  # Case sensitive


def test_skeleton_with_none_id_node():
    """
    Test skeleton with nodes that have id=None.
    """
    skeleton = SkeletonBase(skeletons.COCO_17)
    assert skeleton.get_joint_name(12) == "RHip"
    assert skeleton.get_joint_id("RHip") == 12
    assert skeleton.get_joint_name(None) is None  # Should not find a node with id=None
    assert skeleton.get_joint_id("Hip") is None  # Node with name "Hip" has id=None


def test_calculate_fake_marker_pos_placeholder():
    """
    Test that calculate_fake_marker_pos is a placeholder and does nothing.
    """
    skeleton = SkeletonBase(skeletons.HALPE_26)
    assert skeleton.calculate_fake_marker_pos("fake_marker", {}) is None


def test_coco133_skeleton_calculate_fake_marker_pos_hip_2d():
    """
    Test calculate_fake_marker_pos for Hip in 2D for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton()
    marker_data = {"RHip": [10.0, 20.0, 1.0], "LHip": [30.0, 40.0, 1.0]}
    expected_pos = [20.0, 30.0, 1.0]
    assert skeleton.calculate_fake_marker_pos("Hip", marker_data) == expected_pos


def test_coco133_skeleton_calculate_fake_marker_pos_hip_3d():
    """
    Test calculate_fake_marker_pos for Hip in 3D for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton()
    marker_data = {"RHip": [10.0, 20.0, 30.0], "LHip": [30.0, 40.0, 50.0]}
    expected_pos = [20.0, 30.0, 40.0]
    assert skeleton.calculate_fake_marker_pos("Hip", marker_data) == expected_pos


def test_coco133_skeleton_calculate_fake_marker_pos_neck_2d():
    """
    Test calculate_fake_marker_pos for Neck in 2D for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton()
    marker_data = {"RShoulder": [100.0, 110.0, 1.0], "LShoulder": [120.0, 130.0, 1.0]}
    expected_pos = [110.0, 120.0, 1.0]
    assert skeleton.calculate_fake_marker_pos("Neck", marker_data) == expected_pos


def test_coco133_skeleton_calculate_fake_marker_pos_neck_3d():
    """
    Test calculate_fake_marker_pos for Neck in 3D for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton()
    marker_data = {"RShoulder": [100.0, 110.0, 120.0], "LShoulder": [120.0, 130.0, 140.0]}
    expected_pos = [110.0, 120.0, 130.0]
    assert skeleton.calculate_fake_marker_pos("Neck", marker_data) == expected_pos


def test_coco133_skeleton_calculate_fake_marker_pos_insufficient_data():
    """
    Test calculate_fake_marker_pos with insufficient data for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton()
    marker_data = {
        "RHip": [10.0, 20.0, 1.0]  # Missing LHip
    }
    assert skeleton.calculate_fake_marker_pos("Hip", marker_data) is None

    marker_data = {
        "RShoulder": [100.0, 110.0, 1.0]  # Missing LShoulder
    }
    assert skeleton.calculate_fake_marker_pos("Neck", marker_data) is None


def test_coco133_skeleton_calculate_fake_marker_pos_unhandled_name():
    """
    Test calculate_fake_marker_pos for an unhandled marker name (should fall back to base).
    """
    skeleton = COCO133Skeleton()
    marker_data = {}
    assert skeleton.calculate_fake_marker_pos("SomeOtherMarker", marker_data) is None

def test_coco133_body_parts_mapping():
    """
    Test that COCO133Skeleton correctly maps joints to body parts.
    """
    skeleton = COCO133Skeleton()
    # Check some known mappings
    assert skeleton.body_part("Nose") == "Head"
    assert skeleton.body_part("LShoulder") == "Torso"
    assert skeleton.body_part("RElbow") == "Right arm"
    assert skeleton.body_part("RKnee") == "Right leg"
    assert skeleton.body_part("Hip") == "Torso"
    assert skeleton.body_part("Neck") == "Torso"
    # Check a joint that doesn't exist
    assert skeleton.body_part("NonExistentJoint") is "Unknown"