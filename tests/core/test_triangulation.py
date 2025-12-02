# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for the triangulation module."""

import numpy as np
import pytest

from pose_editor.core.triangulation import TriangulationOutput, triangulate_point


@pytest.fixture
def mock_calibration_data() -> dict:
    """Provides mock calibration data for two cameras."""
    # Using realistic-looking but arbitrary values
    calib = {
        "cam1": {
            "matrix": [[1500, 0, 960], [0, 1500, 540], [0, 0, 1]],
            "rotation": [0.1, 0.2, 0.3],
            "translation": [-1, 0, 0],
        },
        "cam2": {
            "matrix": [[1510, 0, 965], [0, 1510, 545], [0, 0, 1]],
            "rotation": [-0.1, -0.2, -0.3],
            "translation": [1, 0, 0],
        },
        "cam3": {
            "matrix": [[1490, 0, 955], [0, 1490, 535], [0, 0, 1]],
            "rotation": [0.0, 0.0, 0.0],
            "translation": [0, 1, 0],
        },
    }
    return calib


def test_triangulate_point_success(mock_calibration_data):
    """Test successful triangulation with good data from multiple cameras."""
    # Arrange
    # Mock 2D points that should result in a point near the origin (0,0,0)
    points_2d = {
        "cam1": np.array([960, 540, 0.9]),  # Center of cam1 view
        "cam2": np.array([965, 545, 0.9]),  # Center of cam2 view
        "cam3": np.array([955, 535, 0.9]),  # Center of cam3 view
    }

    # Act
    result = triangulate_point(points_2d, mock_calibration_data)

    # Assert
    assert result is not None
    assert isinstance(result, TriangulationOutput)
    assert result.point_3d.shape == (3,)
    assert isinstance(result.reprojection_error, float)
    assert len(result.contributing_cameras) >= 2
    # The point should be close to the origin
    assert np.allclose(result.point_3d, [0, 0, 0], atol=0.1)


def test_triangulate_point_not_enough_cameras(mock_calibration_data):
    """Test that triangulation returns None if not enough high-quality points exist."""
    # Arrange
    points_2d = {
        "cam1": np.array([960, 540, 0.9]),
        "cam2": np.array([965, 545, 0.2]),  # Low quality
        "cam3": np.array([955, 535, 0.1]),  # Low quality
    }

    # Act
    result = triangulate_point(points_2d, mock_calibration_data, min_cameras=2, min_quality=0.8)

    # Assert
    assert result is None


def test_triangulate_point_high_reprojection_error(mock_calibration_data):
    """Test that triangulation returns None if the error is too high."""
    # Arrange
    # Inconsistent points that will lead to a high reprojection error
    points_2d = {
        "cam1": np.array([1200, 600, 0.9]),
        "cam2": np.array([800, 500, 0.9]),
        "cam3": np.array([955, 535, 0.9]),
    }

    # Act
    # Use a very low threshold to force a failure
    result = triangulate_point(points_2d, mock_calibration_data, reproj_error_threshold=0.1)

    # Assert
    assert result is None


def test_triangulate_point_with_disabled_camera(mock_calibration_data):
    """Test that triangulation respects the is_enabled flag."""
    # Arrange
    points_2d = {
        "cam1": np.array([960, 540, 0.9, True]),   # Enabled
        "cam2": np.array([965, 545, 0.9, False]),  # Disabled
        "cam3": np.array([955, 535, 0.9, True]),   # Enabled
    }

    # Act
    result = triangulate_point(points_2d, mock_calibration_data, algorithm="ransac")

    # Assert
    assert result is not None
    # cam2 should not be in contributing cameras
    assert "cam2" not in result.contributing_cameras
    # cam2 should still have reprojection data
    assert "cam2" in result.reprojected_points


def test_triangulate_point_ransac_algorithm(mock_calibration_data):
    """Test that RANSAC algorithm can be explicitly selected."""
    # Arrange
    points_2d = {
        "cam1": np.array([960, 540, 0.9, True]),
        "cam2": np.array([965, 545, 0.9, True]),
        "cam3": np.array([955, 535, 0.9, True]),
    }

    # Act
    result = triangulate_point(points_2d, mock_calibration_data, algorithm="ransac")

    # Assert
    assert result is not None
    assert isinstance(result, TriangulationOutput)


def test_triangulate_point_exhaustive_algorithm(mock_calibration_data):
    """Test that exhaustive algorithm can be explicitly selected."""
    # Arrange
    points_2d = {
        "cam1": np.array([960, 540, 0.9, True]),
        "cam2": np.array([965, 545, 0.9, True]),
        "cam3": np.array([955, 535, 0.9, True]),
    }

    # Act
    result = triangulate_point(points_2d, mock_calibration_data, algorithm="exhaustive")

    # Assert
    assert result is not None
    assert isinstance(result, TriangulationOutput)


def test_triangulate_point_invalid_algorithm(mock_calibration_data):
    """Test that an invalid algorithm raises ValueError."""
    # Arrange
    points_2d = {
        "cam1": np.array([960, 540, 0.9]),
        "cam2": np.array([965, 545, 0.9]),
    }

    # Act & Assert
    with pytest.raises(ValueError, match="Unknown algorithm"):
        triangulate_point(points_2d, mock_calibration_data, algorithm="invalid")


def test_reprojected_points_include_all_cameras(mock_calibration_data):
    """Test that reprojected_points includes all cameras, not just filtered ones."""
    # Arrange
    points_2d = {
        "cam1": np.array([960, 540, 0.9, True]),   # High quality, enabled
        "cam2": np.array([965, 545, 0.2, True]),   # Low quality (filtered out)
        "cam3": np.array([955, 535, 0.9, True]),   # High quality, enabled
    }

    # Act
    result = triangulate_point(
        points_2d, mock_calibration_data,
        min_quality=0.5, algorithm="ransac"
    )

    # Assert
    assert result is not None
    # All cameras should have reprojection data
    assert "cam1" in result.reprojected_points
    assert "cam2" in result.reprojected_points
    assert "cam3" in result.reprojected_points
    # cam2 was filtered out, so should not be in contributing_cameras
    assert "cam2" not in result.contributing_cameras
