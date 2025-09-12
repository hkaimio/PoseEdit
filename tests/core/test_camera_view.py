import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
from anytree import Node

from pose_editor.core.camera_view import create_camera_view, _extract_frame_number
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
def test_create_camera_view_scaling_landscape(
    mock_open_file, mock_listdir, mock_person_data_view, mock_dal
):
    # Arrange
    mock_movie_clip = MagicMock()
    mock_movie_clip.size = (1280, 720)
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
    scale_factor = BLENDER_TARGET_WIDTH / video_width

    xfactor = scale_factor
    yfactor = -scale_factor
    xoffset = -(video_width * scale_factor) / 2
    yoffset = (video_height * scale_factor) / 2



    scaled_blender_width = video_width * scale_factor
    mock_dal.set_camera_ortho.assert_called_once_with(
        mock_dal.create_camera.return_value, pytest.approx(scaled_blender_width)
    )


@patch("pose_editor.core.camera_view.dal", autospec=True)
@patch("pose_editor.core.camera_view.PersonDataView", autospec=True)
@patch("pose_editor.core.camera_view.os.listdir", autospec=True)
@patch(
    "pose_editor.core.camera_view.open",
    new_callable=mock_open,
    read_data='{"people":[]}',
)
def test_create_camera_view_scaling_portrait(
    mock_open_file, mock_listdir, mock_person_data_view, mock_dal
):
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