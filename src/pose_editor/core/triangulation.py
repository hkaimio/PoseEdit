# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for 3D triangulation logic."""

import itertools as it
import math
from typing import NamedTuple

import numpy as np

class ReprojectionResult(NamedTuple):
    """The result of a reprojection operation."""
    x: float
    y: float
    cam_used: bool

class TriangulationOutput(NamedTuple):
    """The result of triangulating a single point in a single frame."""
    point_3d: np.ndarray  # Shape (3,) for (x, y, z)
    contributing_cameras: list[str]  # Names of cameras used
    reprojection_error: float
    reprojected_points: dict[str, np.ndarray]  # Camera name to (x, y) reprojected point


def rodrigues(rotation_vector) -> np.ndarray:
    """
    Converts a rotation vector to a rotation matrix using Rodrigues' formula.
    """
    theta = np.linalg.norm(rotation_vector)
    if theta < 1e-9:
        return np.eye(3)

    r = rotation_vector / theta
    rx, ry, rz = r
    K_mat = np.array([
        [0, -rz, ry],
        [rz, 0, -rx],
        [-ry, rx, 0]
    ])
    R = np.eye(3) + np.sin(theta) * K_mat + (1 - np.cos(theta)) * (K_mat @ K_mat)
    return R


def weighted_triangulation(P_all, x_all, y_all, likelihood_all):
    """
    Triangulation with direct linear transform, weighted by likelihood.
    """
    A_list = []
    for c in range(len(x_all)):
        P_cam = P_all[c]
        A_list.append((P_cam[0] - x_all[c] * P_cam[2]) * likelihood_all[c])
        A_list.append((P_cam[1] - y_all[c] * P_cam[2]) * likelihood_all[c])
    A = np.array(A_list)

    if np.shape(A)[0] >= 4:
        # Use numpy's SVD
        _U, _s, Vt = np.linalg.svd(A)
        # The solution is the null space of A, corresponding to the singular vector
        # associated with the smallest singular value. Vt is V transpose, and s is
        # sorted high-to-low, so the last row of Vt is the vector we want.
        Q = Vt[-1]
        Q = Q / Q[3]  # Normalize homogeneous coordinate
    else:
        Q = np.array([np.nan, np.nan, np.nan, 1])
    return Q

def reprojection(P, Q):
    """Reproject 3D point to 2D using projection matrix."""
    q_proj = P @ Q
    if q_proj[2] != 0:
        x = q_proj[0] / q_proj[2]
        y = q_proj[1] / q_proj[2]
    else:
        x = np.nan
        y = np.nan
    return x, y

def euclidean_distance(q1, q2):
    dist = np.array(q1) - np.array(q2)
    return np.sqrt(np.nansum(dist**2))


def triangulate_point_exhaustive(
    points_2d_by_camera: dict[str, np.ndarray],
    calibration_by_camera: dict[str, dict],
    min_cameras: int = 2,
    reproj_error_threshold: float = 10.0,
    min_quality: float = 0.5,
) -> TriangulationOutput | None:
    """
    Triangulates a single 3D point from multiple 2D observations using exhaustive search.
    This is the original algorithm kept for comparison.
    """

    camera_names = list(calibration_by_camera.keys())
    x_all, y_all, likelihood_all, projection_matrices = [], [], [], []

    for name in camera_names:
        point_2d = points_2d_by_camera.get(name)
        calib = calibration_by_camera.get(name)

        if calib and point_2d is not None and point_2d[2] >= min_quality:
            # Check is_enabled flag (4th column)
            is_enabled = point_2d[3] if len(point_2d) > 3 else True
            if not is_enabled:
                x_all.append(np.nan)
                y_all.append(np.nan)
                likelihood_all.append(0)
                projection_matrices.append(None)
                continue

            x_all.append(point_2d[0])
            y_all.append(point_2d[1])
            likelihood_all.append(point_2d[2])

            K = np.array(calib["matrix"])
            R = rodrigues(np.array(calib["rotation"]))
            t = np.array(calib["translation"]).reshape(3, 1)
            Rt = np.hstack((R, t))
            P = K @ Rt
            projection_matrices.append(P)
        else:
            x_all.append(np.nan)
            y_all.append(np.nan)
            likelihood_all.append(0)
            projection_matrices.append(None)

    valid_indices = [i for i, p in enumerate(projection_matrices) if p is not None]
    if len(valid_indices) < min_cameras:
        return None

    min_cameras_for_algo = min_cameras
    x = np.array([x_all[i] for i in valid_indices])
    y = np.array([y_all[i] for i in valid_indices])
    quality = np.array([likelihood_all[i] for i in valid_indices])
    proj_matrices = [projection_matrices[i] for i in valid_indices]
    valid_camera_names = [camera_names[i] for i in valid_indices]
    n_cams = len(valid_camera_names)

    error_min = np.inf
    Q_best = None
    best_cam_indices = None

    nb_cams_off = 0
    while n_cams - nb_cams_off >= min_cameras_for_algo:
        error_configs = []
        q_configs = []
        indices_configs = []

        for cam_indices in it.combinations(range(n_cams), n_cams - nb_cams_off):
            if not cam_indices:
                continue

            current_indices = list(cam_indices)
            P_current = [proj_matrices[i] for i in current_indices]
            x_current = x[current_indices]
            y_current = y[current_indices]
            q_current = quality[current_indices]

            Q = weighted_triangulation(P_current, x_current, y_current, q_current)
            if np.isnan(Q).any():
                continue

            # Reproject using new single-camera reprojection function
            x_calc = []
            y_calc = []
            for P_cam in P_current:
                x_r, y_r = reprojection(P_cam, Q)
                x_calc.append(x_r)
                y_calc.append(y_r)

            errors = [euclidean_distance([x_current[i], y_current[i]], [x_calc[i], y_calc[i]])
                     for i in range(len(current_indices))]
            mean_error = np.mean(errors)

            error_configs.append(mean_error)
            q_configs.append(Q)
            indices_configs.append(current_indices)

        if not error_configs:
            nb_cams_off += 1
            continue

        min_err_for_this_iter = min(error_configs) if error_configs else np.inf
        if min_err_for_this_iter < error_min:
            error_min = min_err_for_this_iter
            best_config_idx = np.argmin(error_configs)
            Q_best = q_configs[best_config_idx]
            best_cam_indices = indices_configs[best_config_idx]

        if error_min < reproj_error_threshold:
            break

        nb_cams_off += 1

    if Q_best is None or best_cam_indices is None:
        return None

    contributing_cams = [valid_camera_names[i] for i in best_cam_indices]

    # Reproject to ALL cameras in original list
    reprojected_points = {}
    for i, camera_name in enumerate(camera_names):
        P_cam = projection_matrices[i]
        if P_cam is not None:
            x_calc, y_calc = reprojection(P_cam, Q_best)
            used = camera_name in contributing_cams
            reprojected_points[camera_name] =  ReprojectionResult(x_calc, y_calc , used)

    return TriangulationOutput(
        point_3d=Q_best[:3],
        contributing_cameras=contributing_cams,
        reprojection_error=error_min,
        reprojected_points=reprojected_points
    )


def triangulate_point_ransac(
    points_2d_by_camera: dict[str, np.ndarray],
    calibration_by_camera: dict[str, dict],
    min_cameras: int = 2,
    reproj_error_threshold: float = 10.0,
    min_quality: float = 0.5,
    max_ransac_iterations: int = 100,
) -> TriangulationOutput | None:
    """
    Triangulates a single 3D point from multiple 2D observations using RANSAC algorithm.

    Args:
        points_2d_by_camera: Dict mapping camera names to [x, y, quality, is_enabled]
        calibration_by_camera: Dict mapping camera names to calibration dicts
        min_cameras: Minimum number of cameras required
        reproj_error_threshold: Maximum reprojection error for inliers (pixels)
        min_quality: Minimum quality threshold for filtering
        max_ransac_iterations: Maximum RANSAC iterations

    Returns:
        TriangulationOutput with 3D point and metadata, or None if triangulation fails
    """
    camera_names = list(calibration_by_camera.keys())

    # Step 1: Filter cameras based on quality and is_enabled flag
    filtered_cameras = []
    all_camera_data = {}  # Store data for ALL cameras for final reprojection

    for name in camera_names:
        if name not in points_2d_by_camera:
            continue

        pt_data = points_2d_by_camera[name]
        x, y, quality = pt_data[0], pt_data[1], pt_data[2]
        is_enabled = pt_data[3] if len(pt_data) > 3 else True

        calib = calibration_by_camera[name]

        # Build projection matrix
        K = np.array(calib['matrix'])
        R = rodrigues(np.array(calib['rotation']))
        T = np.array(calib['translation']).reshape(3, 1)
        P = K @ np.hstack([R, T])

        # Store for ALL cameras
        all_camera_data[name] = {
            'x': x, 'y': y, 'quality': quality,
            'is_enabled': is_enabled, 'P': P
        }

        # Filter for triangulation
        if quality >= min_quality and is_enabled:
            filtered_cameras.append(name)

    n_filtered = len(filtered_cameras)

    if n_filtered < min_cameras:
        return None

    # Step 2: RANSAC iterations
    best_solution = None
    best_error = np.inf
    best_n_cameras = 0
    best_cameras = []

    max_ransac_iterations = min(math.comb(len(filtered_cameras), 2), max_ransac_iterations)

    for _iteration in range(max_ransac_iterations):
        # Sample 2 cameras randomly
        if n_filtered == 2:
            sample_cameras = filtered_cameras
        else:
            sample_cameras = list(np.random.choice(filtered_cameras, size=2, replace=False))

        # Initial triangulation with sample
        sample_x = [all_camera_data[c]['x'] for c in sample_cameras]
        sample_y = [all_camera_data[c]['y'] for c in sample_cameras]
        sample_quality = [all_camera_data[c]['quality'] for c in sample_cameras]
        sample_P = [all_camera_data[c]['P'] for c in sample_cameras]

        Q_sample = weighted_triangulation(sample_P, sample_x, sample_y, sample_quality)

        # Skip if invalid
        if np.any(np.isnan(Q_sample)):
            continue

        # Reproject to all filtered cameras and find inliers
        reprojection_errors = {}
        for cam in filtered_cameras:
            cam_data = all_camera_data[cam]
            x_reproj, y_reproj = reprojection(cam_data['P'], Q_sample)

            if np.isnan(x_reproj) or np.isnan(y_reproj):
                reprojection_errors[cam] = np.inf
            else:
                error = euclidean_distance([cam_data['x'], cam_data['y']], [x_reproj, y_reproj])
                reprojection_errors[cam] = error

        # Find inlier cameras
        inlier_cameras = [cam for cam in filtered_cameras
                         if reprojection_errors[cam] < reproj_error_threshold]

        n_inliers = len(inlier_cameras)

        if n_inliers < min_cameras:
            continue

        # Re-triangulate with all inliers
        inlier_x = [all_camera_data[c]['x'] for c in inlier_cameras]
        inlier_y = [all_camera_data[c]['y'] for c in inlier_cameras]
        inlier_quality = [all_camera_data[c]['quality'] for c in inlier_cameras]
        inlier_P = [all_camera_data[c]['P'] for c in inlier_cameras]

        Q_inliers = weighted_triangulation(inlier_P, inlier_x, inlier_y, inlier_quality)

        if np.any(np.isnan(Q_inliers)):
            continue

        # Recalculate errors with new triangulation
        final_errors = []
        for cam in inlier_cameras:
            cam_data = all_camera_data[cam]
            x_reproj, y_reproj = reprojection(cam_data['P'], Q_inliers)
            error = euclidean_distance([cam_data['x'], cam_data['y']], [x_reproj, y_reproj])
            final_errors.append(error)

        mean_error = np.mean(final_errors)

        # Update best solution if more cameras or same cameras with lower error
        if (n_inliers > best_n_cameras) or \
           (n_inliers == best_n_cameras and mean_error < best_error):
            best_solution = Q_inliers
            best_error = mean_error
            best_n_cameras = n_inliers
            best_cameras = inlier_cameras

        # Early termination if all cameras are inliers with low error
        if n_inliers == n_filtered and mean_error < reproj_error_threshold:
            break

    if best_solution is None:
        return None

    # Step 3: Reproject to ALL cameras (not just filtered ones)
    reprojected_points = {}
    for cam_name in all_camera_data.keys():
        cam_data = all_camera_data[cam_name]
        x_reproj, y_reproj = reprojection(cam_data['P'], best_solution)
        reprojected_points[cam_name] =ReprojectionResult(x_reproj, y_reproj,
                                                        cam_name in best_cameras)

    return TriangulationOutput(
        point_3d=best_solution[:3],
        contributing_cameras=best_cameras,
        reprojection_error=float(best_error),
        reprojected_points=reprojected_points
    )


def triangulate_point(
    points_2d_by_camera: dict[str, np.ndarray],
    calibration_by_camera: dict[str, dict],
    min_cameras: int = 2,
    reproj_error_threshold: float = 10.0,
    min_quality: float = 0.5,
    algorithm: str = "ransac",
    max_ransac_iterations: int = 100,
) -> TriangulationOutput | None:
    """
    Triangulates a single 3D point from multiple 2D observations.

    Args:
        points_2d_by_camera: Dict mapping camera names to [x, y, quality, is_enabled]
        calibration_by_camera: Dict mapping camera names to calibration dicts
        min_cameras: Minimum number of cameras required
        reproj_error_threshold: Maximum reprojection error threshold
        min_quality: Minimum quality threshold for filtering
        algorithm: "ransac" or "exhaustive" (default: "ransac")
        max_ransac_iterations: Maximum RANSAC iterations (only for RANSAC)

    Returns:
        TriangulationOutput with 3D point and metadata, or None if triangulation fails
    """
    if algorithm == "ransac":
        return triangulate_point_ransac(
            points_2d_by_camera,
            calibration_by_camera,
            min_cameras,
            reproj_error_threshold,
            min_quality,
            max_ransac_iterations,
        )
    elif algorithm == "exhaustive":
        return triangulate_point_exhaustive(
            points_2d_by_camera,
            calibration_by_camera,
            min_cameras,
            reproj_error_threshold,
            min_quality,
        )
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}. Use 'ransac' or 'exhaustive'.")

