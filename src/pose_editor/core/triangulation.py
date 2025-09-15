# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for 3D triangulation logic."""

import itertools as it
from typing import Dict, List, NamedTuple, Optional

try:
    import cv2
except ImportError:
    print("Warning: OpenCV (cv2) is not installed. Triangulation functions will not work.")
import numpy as np


class TriangulationOutput(NamedTuple):
    """The result of triangulating a single point in a single frame."""
    point_3d: np.ndarray  # Shape (3,) for (x, y, z)
    contributing_cameras: List[str]  # Names of cameras used
    reprojection_error: float


# Helper functions from the prototype
def weighted_triangulation(P_all, x_all, y_all, likelihood_all):
    A = np.empty((0, 4))
    for c in range(len(x_all)):
        P_cam = P_all[c]
        A = np.vstack((A, (P_cam[0] - x_all[c] * P_cam[2]) * likelihood_all[c]))
        A = np.vstack((A, (P_cam[1] - y_all[c] * P_cam[2]) * likelihood_all[c]))

    if np.shape(A)[0] >= 4:
        S, U, Vt = cv2.SVDecomp(A)
        V = Vt.T
        Q = np.array([V[0][3] / V[3][3], V[1][3] / V[3][3], V[2][3] / V[3][3], 1])
    else:
        Q = np.array([np.nan, np.nan, np.nan, 1])
    return Q

def reprojection(P_all, Q):
    x_calc, y_calc = [], []
    for c in range(len(P_all)):
        P_cam = P_all[c]
        x_calc.append(P_cam[0] @ Q / (P_cam[2] @ Q))
        y_calc.append(P_cam[1] @ Q / (P_cam[2] @ Q))
    return x_calc, y_calc

def euclidean_distance(q1, q2):
    q1 = np.array(q1)
    q2 = np.array(q2)
    dist = q2 - q1
    if np.isnan(dist).all():
        dist = np.empty_like(dist)
        dist[...] = np.inf

    if len(dist.shape) == 1:
        euc_dist = np.sqrt(np.nansum([d**2 for d in dist]))
    else:
        euc_dist = np.sqrt(np.nansum([d**2 for d in dist], axis=1))
    return euc_dist


def triangulate_point(
    points_2d_by_camera: Dict[str, np.ndarray],
    calibration_by_camera: Dict[str, dict],
    min_cameras: int = 2,
    reproj_error_threshold: float = 10.0,
    min_quality: float = 0.5,
) -> Optional[TriangulationOutput]:
    """Triangulates a single 3D point from multiple 2D observations."""
    
    # 1. Unpack the input dictionaries into lists, filtering by quality
    camera_names = list(points_2d_by_camera.keys())
    x_all, y_all, likelihood_all, projection_matrices = [], [], [], []
    
    for name in camera_names:
        point_2d = points_2d_by_camera[name]
        calib = calibration_by_camera.get(name)
        
        if calib and point_2d[2] >= min_quality:
            x_all.append(point_2d[0])
            y_all.append(point_2d[1])
            likelihood_all.append(point_2d[2])
            
            # Construct projection matrix P = K * [R|t]
            K = np.array(calib["matrix"])
            R = cv2.Rodrigues(np.array(calib["rotation"]))[0]
            t = np.array(calib["translation"]).reshape(3, 1)
            Rt = np.hstack((R, t))
            P = K @ Rt
            projection_matrices.append(P)
        else:
            # Append NaN for cameras that don't meet quality or have no calib
            x_all.append(np.nan)
            y_all.append(np.nan)
            likelihood_all.append(0)
            projection_matrices.append(None) # Placeholder

    # Filter out None projection matrices before processing
    valid_indices = [i for i, p in enumerate(projection_matrices) if p is not None]
    if len(valid_indices) < min_cameras:
        return None

    x = np.array([x_all[i] for i in valid_indices])
    y = np.array([y_all[i] for i in valid_indices])
    quality = np.array([likelihood_all[i] for i in valid_indices])
    proj_matrices = [projection_matrices[i] for i in valid_indices]
    valid_camera_names = [camera_names[i] for i in valid_indices]
    n_cams = len(valid_camera_names)

    # 2. Iteratively remove cameras to find the best triangulation
    error_min = np.inf
    Q_best = None
    best_cam_indices = None

    nb_cams_off = 0
    while n_cams - nb_cams_off >= min_cameras:
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

            x_calc, y_calc = reprojection(P_current, Q)
            
            q_file = list(zip(x_current, y_current))
            q_calc = list(zip(x_calc, y_calc))
            
            errors = [euclidean_distance(q_f, q_c) for q_f, q_c in zip(q_file, q_calc)]
            mean_error = np.mean(errors)

            error_configs.append(mean_error)
            q_configs.append(Q)
            indices_configs.append(current_indices)

        if not error_configs:
            nb_cams_off += 1
            continue

        min_err_for_this_iter = min(error_configs)
        if min_err_for_this_iter < error_min:
            error_min = min_err_for_this_iter
            best_config_idx = np.argmin(error_configs)
            Q_best = q_configs[best_config_idx]
            best_cam_indices = indices_configs[best_config_idx]

        if error_min < reproj_error_threshold:
            break

        nb_cams_off += 1

    # 3. Format the output
    if Q_best is None or error_min > reproj_error_threshold:
        return None

    contributing_cams = [valid_camera_names[i] for i in best_cam_indices]

    return TriangulationOutput(
        point_3d=Q_best[:3],
        contributing_cameras=contributing_cams,
        reprojection_error=error_min,
    )