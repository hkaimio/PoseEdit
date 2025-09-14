# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for the triangulation module."""

import numpy as np
import pytest

from pose_editor.core.triangulation import triangulate_point, TriangulationOutput


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