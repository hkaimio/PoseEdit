from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pytest
from anytree import Node

from pose_editor.core.camera_view import (
    CameraView,
    _extract_frame_number,
    create_camera_view,
)
from pose_editor.core.skeleton import SkeletonBase


class DummySkeleton(SkeletonBase):
    def __init__(self):
        self._skeleton = Node("Root")

    def calculate_fake_marker_pos(self, name, marker_data):
        return None


@patch("pose_editor.core.camera_view.dal", autospec=True)
@patch("pose_editor.core.camera_view.PersonDataView", autospec=True)
@patch("pose_editor.core.camera_view.os.listdir", autospec=True)
@patch(
    "pose_editor.core.camera_view.open",
    new_callable=mock_open,
    read_data='{"people":[]}',
)
def test_create_camera_view_scaling_landscape(mock_open_file, mock_listdir, mock_person_data_view, mock_dal):
    # Arrange
    mock_movie_clip = MagicMock()
    mock_movie_clip.size = (1280, 720)
    mock_dal.load_movie_clip.return_value = mock_movie_clip
    camera_view_empty_mock = MagicMock(name="camera_view_empty")
    mock_dal.create_empty.return_value = camera_view_empty_mock
    mock_dal.create_camera.return_value = MagicMock(name="camera_obj_ref")
    mock_listdir.return_value = []

    skeleton = DummySkeleton()

    # Act
    create_camera_view("test_cam", Path("video.mp4"), Path("pose_data"), skeleton)

    # Assert
    from pose_editor.core.camera_view import BLENDER_TARGET_WIDTH

    video_width, video_height = mock_movie_clip.size
    scale_factor = BLENDER_TARGET_WIDTH / video_width

    xfactor = scale_factor
    yfactor = -scale_factor
    zfactor = scale_factor
    xoffset = -(video_width * scale_factor) / 2
    yoffset = (video_height * scale_factor) / 2

    scaled_blender_width = video_width * scale_factor
    mock_dal.set_camera_ortho.assert_called_once_with(
        mock_dal.create_camera.return_value, pytest.approx(scaled_blender_width)
    )

    # Assert that the transform properties were saved
    mock_dal.set_custom_property.assert_any_call(camera_view_empty_mock, "camera_x_scale", xfactor)
    mock_dal.set_custom_property.assert_any_call(camera_view_empty_mock, "camera_y_scale", yfactor)
    mock_dal.set_custom_property.assert_any_call(camera_view_empty_mock, "camera_z_scale", zfactor)
    mock_dal.set_custom_property.assert_any_call(camera_view_empty_mock, "camera_x_offset", xoffset)
    mock_dal.set_custom_property.assert_any_call(camera_view_empty_mock, "camera_y_offset", yoffset)


@patch("pose_editor.core.camera_view.dal", autospec=True)
@patch("pose_editor.core.camera_view.PersonDataView", autospec=True)
@patch("pose_editor.core.camera_view.os.listdir", autospec=True)
@patch(
    "pose_editor.core.camera_view.open",
    new_callable=mock_open,
    read_data='{"people":[]}',
)
def test_create_camera_view_scaling_portrait(mock_open_file, mock_listdir, mock_person_data_view, mock_dal):
    # Arrange
    mock_movie_clip = MagicMock()
    mock_movie_clip.size = (1080, 1920)
    mock_dal.load_movie_clip.return_value = mock_movie_clip
    mock_dal.create_empty.return_value = MagicMock(name="camera_view_empty")
    mock_dal.create_camera.return_value = MagicMock(name="camera_obj_ref")
    mock_listdir.return_value = []

    skeleton = DummySkeleton()

    # Act
    create_camera_view("test_cam", Path("video.mp4"), Path("pose_data"), skeleton)

    # Assert
    from pose_editor.core.camera_view import BLENDER_TARGET_WIDTH

    video_width, video_height = mock_movie_clip.size
    scale_factor = BLENDER_TARGET_WIDTH / video_height

    xfactor = scale_factor
    yfactor = -scale_factor
    xoffset = -(video_width * scale_factor) / 2
    yoffset = (video_height * scale_factor) / 2

    scaled_blender_width = video_width * scale_factor
    mock_dal.set_camera_ortho.assert_called_once_with(
        mock_dal.create_camera.return_value, pytest.approx(scaled_blender_width)
    )


def test_extract_frame_number_standard_format():
    """
    Test _extract_frame_number with standard camX_YYYYYY.json format.
    """
    assert _extract_frame_number("cam1_000000.json") == 0
    assert _extract_frame_number("cam2_001234.json") == 1234
    assert _extract_frame_number("cam_000001.json") == 1


def test_extract_frame_number_other_formats():
    """
    Test _extract_frame_number with other filename formats.
    """
    assert _extract_frame_number("video_frame_00123.png") == 123
    assert _extract_frame_number("my_clip_frame_99.mp4") == 99
    assert _extract_frame_number("image_1.jpg") == 1


def test_extract_frame_number_multiple_numbers():
    """
    Test _extract_frame_number with multiple numbers in the filename.
    """
    assert _extract_frame_number("cam1_session_2_000050.json") == 50
    assert _extract_frame_number("cam_a_1_b_2_c_3.txt") == 3


def test_extract_frame_number_no_number():
    """
    Test _extract_frame_number with no numbers in the filename.
    """
    with pytest.raises(ValueError, match="No frame number found in filename"):
        _extract_frame_number("no_numbers_here.txt")


def test_extract_frame_number_empty_string():
    """
    Test _extract_frame_number with an empty string.
    """
    with pytest.raises(ValueError, match="No frame number found in filename"):
        _extract_frame_number("")


@patch("pose_editor.core.camera_view.dal", autospec=True)
@patch("pose_editor.core.camera_view.MarkerData", autospec=True)
@patch("pose_editor.core.camera_view.PersonDataView", autospec=True)
@patch("pose_editor.core.camera_view.os.listdir", autospec=True)
@patch("pose_editor.core.camera_view.open", new_callable=mock_open)
@patch("pose_editor.core.camera_view.json.load", autospec=True)
def test_create_camera_view_missing_person_data(
    mock_json_load, mock_open_file, mock_listdir, mock_person_data_view, mock_marker_data, mock_dal
):
    """
    Tests that when a person is not detected in a frame, the quality of their markers is set to -1.
    """
    # Arrange
    # Mock movie clip
    mock_movie_clip = MagicMock()
    mock_movie_clip.size = (1920, 1080)
    mock_dal.load_movie_clip.return_value = mock_movie_clip
    mock_dal.create_empty.return_value = MagicMock()
    mock_dal.create_camera.return_value = MagicMock()

    # Configure PersonDataView mock
    mock_person_view_instance = MagicMock()
    mock_person_view_instance.view_name = "mock_person_view"
    mock_root_obj = MagicMock()
    mock_root_obj.name = "mock_root_obj"
    mock_blender_obj = MagicMock()
    mock_root_obj._get_obj.return_value = mock_blender_obj
    mock_person_view_instance.view_root_object = mock_root_obj
    mock_person_data_view.return_value = mock_person_view_instance

    # Mock skeleton
    skeleton = DummySkeleton()
    # Add one joint to the dummy skeleton
    from anytree import Node

    Node("joint1", parent=skeleton._skeleton, id=0)

    # Mock listdir to return 3 frames
    mock_listdir.return_value = ["frame_0.json", "frame_1.json", "frame_2.json"]

    # Mock json.load to return data for frames 0 and 2, but not 1 for person 0
    mock_json_load.side_effect = [
        {"people": [{"pose_keypoints_2d": [10, 20, 0.9]}]},  # frame 0
        {"people": []},  # frame 1
        {"people": [{"pose_keypoints_2d": [12, 22, 0.9]}]},  # frame 2
    ]

    # Act
    create_camera_view("test_cam", Path("video.mp4"), Path("pose_data"), skeleton)

    # Assert
    # Check the data passed to set_animation_data_from_numpy
    marker_data_instance = mock_marker_data.return_value
    call_args = marker_data_instance.set_animation_data_from_numpy.call_args

    data = call_args.kwargs["data"]

    # data should have 3 rows (frames)
    # Frame 0: [10, 20, 0.9]
    # Frame 1: [nan, nan, -1.0]
    # Frame 2: [12, 22, 0.9]

    assert np.isclose(data[0, 2], 0.9)
    assert np.isnan(data[1, 0])
    assert np.isnan(data[1, 1])
    assert np.isclose(data[1, 2], -1.0)
    assert np.isclose(data[2, 2], 0.9)


class TestCameraView:
    @patch("pose_editor.core.camera_view.dal", autospec=True)
    def test_get_transform(self, mock_dal):
        # Arrange
        cv = CameraView()
        cv._obj = MagicMock()

        mock_dal.get_custom_property.side_effect = lambda obj, key: {
            "camera_x_scale": 0.1,
            "camera_y_scale": -0.2,
            "camera_z_scale": 0.3,
            "camera_x_offset": 10.0,
            "camera_y_offset": -20.0,
        }.get(key)

        # Act
        scale = cv.get_transform_scale()
        location = cv.get_transform_location()

        # Assert
        assert scale == (0.1, -0.2, 0.3)
        assert location == (10.0, -20.0, 0.0)