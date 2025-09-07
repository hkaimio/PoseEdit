import pytest
from pose_editor.core.camera_view import _extract_frame_number

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
