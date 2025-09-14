# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for the calibration module."""

import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from pose_editor.core.calibration import (
    CALIBRATION_DATA_JSON,
    CALIBRATION_OBJECT_NAME,
    Calibration,
    load_calibration_from_file,
)


@patch("pose_editor.core.calibration.dal")
@patch("pose_editor.core.calibration.tomllib.load")
def test_load_calibration_from_file(mock_tomllib_load, mock_dal):
    """Test that loading from file calls DAL functions correctly."""
    # Arrange
    mock_calib_obj = MagicMock()
    mock_dal.get_or_create_object.return_value = mock_calib_obj

    toml_data = {"camera": {"matrix": [1, 2, 3]}}
    mock_tomllib_load.return_value = toml_data

    # Act
    with patch("builtins.open", mock_open(read_data="")):
        load_calibration_from_file("dummy.toml")

    # Assert
    mock_dal.get_or_create_object.assert_called_once_with(CALIBRATION_OBJECT_NAME, "EMPTY")

    expected_json_string = json.dumps(toml_data, indent=2)
    mock_dal.set_custom_property.assert_called_once_with(
        mock_calib_obj, CALIBRATION_DATA_JSON, expected_json_string
    )


class TestCalibration:
    """Tests for the Calibration facade class."""

    @patch("pose_editor.core.calibration.dal")
    def test_calibration_load_success(self, mock_dal):
        """Test successful loading and parsing of calibration data."""
        # Arrange
        mock_calib_obj = MagicMock()
        mock_dal.get_object_by_name.return_value = mock_calib_obj

        test_data = {
            "int_cam1_img": {"matrix": [[1, 0, 0]]},
            "int_cam2_img": {"matrix": [[2, 0, 0]]},
            "metadata": {"error": 0.0},
        }
        json_string = json.dumps(test_data)
        mock_dal.get_custom_property.return_value = json_string

        # Act
        calib = Calibration()

        # Assert
        mock_dal.get_object_by_name.assert_called_once_with(CALIBRATION_OBJECT_NAME)
        mock_dal.get_custom_property.assert_called_once_with(mock_calib_obj, CALIBRATION_DATA_JSON)

        assert calib.get_camera_names() == ["int_cam1_img", "int_cam2_img"]
        assert calib.get_camera_data("int_cam1_img") == {"matrix": [[1, 0, 0]]}
        assert calib.get_matrix("int_cam2_img") == [[2, 0, 0]]
        assert calib.get_camera_data("non_existent_cam") is None

    @patch("pose_editor.core.calibration.dal")
    def test_calibration_load_no_object(self, mock_dal):
        """Test behavior when the calibration object doesn't exist."""
        # Arrange
        mock_dal.get_object_by_name.return_value = None

        # Act
        calib = Calibration()

        # Assert
        assert calib._data == {}
        mock_dal.get_custom_property.assert_not_called()

    @patch("pose_editor.core.calibration.dal")
    def test_calibration_load_no_property(self, mock_dal):
        """Test behavior when the custom property doesn't exist on the object."""
        # Arrange
        mock_calib_obj = MagicMock()
        mock_dal.get_object_by_name.return_value = mock_calib_obj
        mock_dal.get_custom_property.return_value = None

        # Act
        calib = Calibration()

        # Assert
        assert calib._data == {}

    @patch("pose_editor.core.calibration.dal")
    def test_calibration_load_corrupted_json(self, mock_dal):
        """Test behavior with invalid JSON in the custom property."""
        # Arrange
        mock_calib_obj = MagicMock()
        mock_dal.get_object_by_name.return_value = mock_calib_obj
        mock_dal.get_custom_property.return_value = "{this is not json}"

        # Act
        calib = Calibration()

        # Assert
        assert calib._data == {}