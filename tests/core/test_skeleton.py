import pytest
from anytree import Node
from pose_editor.core.skeleton import SkeletonBase
from pose_editor.pose2sim import skeletons

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
    assert skeleton.get_joint_id("hip") is None # Case sensitive

def test_skeleton_with_none_id_node():
    """
    Test skeleton with nodes that have id=None.
    """
    skeleton = SkeletonBase(skeletons.COCO_17)
    assert skeleton.get_joint_name(12) == "RHip"
    assert skeleton.get_joint_id("RHip") == 12
    assert skeleton.get_joint_name(None) is None # Should not find a node with id=None
    assert skeleton.get_joint_id("Hip") is None # Node with name "Hip" has id=None

def test_calculate_fake_marker_pos_placeholder():
    """
    Test that calculate_fake_marker_pos is a placeholder and does nothing.
    """
    skeleton = SkeletonBase(skeletons.HALPE_26)
    assert skeleton.calculate_fake_marker_pos("fake_marker", {}) is None
