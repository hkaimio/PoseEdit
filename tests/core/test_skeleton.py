from pose_editor.core.skeleton import COCO133Skeleton, SkeletonBase
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
    skeleton = COCO133Skeleton(skeletons.COCO_133)
    marker_data = {"RHip": [10.0, 20.0, 1.0], "LHip": [30.0, 40.0, 1.0]}
    expected_pos = [20.0, 30.0, 1.0]
    assert skeleton.calculate_fake_marker_pos("Hip", marker_data) == expected_pos


def test_coco133_skeleton_calculate_fake_marker_pos_hip_3d():
    """
    Test calculate_fake_marker_pos for Hip in 3D for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton(skeletons.COCO_133)
    marker_data = {"RHip": [10.0, 20.0, 30.0], "LHip": [30.0, 40.0, 50.0]}
    expected_pos = [20.0, 30.0, 40.0]
    assert skeleton.calculate_fake_marker_pos("Hip", marker_data) == expected_pos


def test_coco133_skeleton_calculate_fake_marker_pos_neck_2d():
    """
    Test calculate_fake_marker_pos for Neck in 2D for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton(skeletons.COCO_133)
    marker_data = {"RShoulder": [100.0, 110.0, 1.0], "LShoulder": [120.0, 130.0, 1.0]}
    expected_pos = [110.0, 120.0, 1.0]
    assert skeleton.calculate_fake_marker_pos("Neck", marker_data) == expected_pos


def test_coco133_skeleton_calculate_fake_marker_pos_neck_3d():
    """
    Test calculate_fake_marker_pos for Neck in 3D for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton(skeletons.COCO_133)
    marker_data = {"RShoulder": [100.0, 110.0, 120.0], "LShoulder": [120.0, 130.0, 140.0]}
    expected_pos = [110.0, 120.0, 130.0]
    assert skeleton.calculate_fake_marker_pos("Neck", marker_data) == expected_pos


def test_coco133_skeleton_calculate_fake_marker_pos_insufficient_data():
    """
    Test calculate_fake_marker_pos with insufficient data for COCO133Skeleton.
    """
    skeleton = COCO133Skeleton(skeletons.COCO_133)
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
    skeleton = COCO133Skeleton(skeletons.COCO_133)
    marker_data = {}
    assert skeleton.calculate_fake_marker_pos("SomeOtherMarker", marker_data) is None
