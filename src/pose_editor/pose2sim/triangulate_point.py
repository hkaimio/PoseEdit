import numpy as np
import itertools as it

def weighted_triangulation(P_all, x_all, y_all, likelihood_all):
    """
    Triangulation with direct linear transform,
    weighted with likelihood of joint pose estimation.

    INPUTS:
    - P_all: list of arrays. Projection matrices of all cameras
    - x_all,y_all: x, y 2D coordinates to triangulate
    - likelihood_all: likelihood of joint pose estimation

    OUTPUT:
    - Q: array of triangulated point (x,y,z,1.)
    """

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
    """
    Reprojects 3D point on all cameras.

    INPUTS:
    - P_all: list of arrays. Projection matrix for all cameras
    - Q: array of triangulated point (x,y,z,1.)

    OUTPUTS:
    - x_calc, y_calc: list of coordinates of point reprojected on all cameras
    """

    x_calc, y_calc = [], []
    for c in range(len(P_all)):
        P_cam = P_all[c]
        x_calc.append(P_cam[0] @ Q / (P_cam[2] @ Q))
        y_calc.append(P_cam[1] @ Q / (P_cam[2] @ Q))

    return x_calc, y_calc


def euclidean_distance(q1, q2):
    """
    Euclidean distance between 2 points (N-dim).

    INPUTS:
    - q1: list of N_dimensional coordinates of point
         or list of N points of N_dimensional coordinates
    - q2: idem

    OUTPUTS:
    - euc_dist: float. Euclidian distance between q1 and q2
    """

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


def triangulation_from_best_cameras(
    config_dict, coords_2D_kpt , coords_2D_kpt_swapped, projection_matrices:list[np.ndarray], calib_params
):
    """
    Triangulates 2D keypoint coordinates. If reprojection error is above threshold,
    tries swapping left and right sides. If still above, removes a camera until error
    is below threshold unless the number of remaining cameras is below a predefined number.

    1. Creates subset with N cameras excluded
    2. Tries all possible triangulations
    3. Chooses the one with smallest reprojection error
    If error too big, take off one more camera.
        If then below threshold, retain result.
        If better but still too big, take off one more camera.

    INPUTS:
    - a Config.toml file
    - coords_2D_kpt: (x,y,likelihood) * ncams array
    - coords_2D_kpt_swapped: (x,y,likelihood) * ncams array  with left/right swap
    - projection_matrices: list of arrays

    OUTPUTS:
    - Q: array of triangulated point (x,y,z,1.)
    - error_min: float
    - nb_cams_excluded: int
    """

    # Read config_dict
    error_threshold_triangulation = config_dict.get("triangulation").get("reproj_error_threshold_triangulation")
    min_cameras_for_triangulation = config_dict.get("triangulation").get("min_cameras_for_triangulation")
    handle_LR_swap = config_dict.get("triangulation").get("handle_LR_swap")

    undistort_points = config_dict.get("triangulation").get("undistort_points")
    if undistort_points:
        calib_params_K = calib_params["K"]
        calib_params_dist = calib_params["dist"]
        calib_params_R = calib_params["R"]
        calib_params_T = calib_params["T"]

    # Initialize
    x, y, quality = coords_2D_kpt
    x_swapped, y_swapped, quality_swapped = coords_2D_kpt_swapped
    n_cams = len(x)
    error_min = np.inf

    nb_cams_off = 0  # cameras will be taken-off until reprojection error is under threshold
    # print('\n')
    while error_min > error_threshold_triangulation and n_cams - nb_cams_off >= min_cameras_for_triangulation:
        # print("error min ", error_min, "thresh ", error_threshold_triangulation, 'nb_cams_off ', nb_cams_off)
        # Create subsets with "nb_cams_off" cameras excluded
        id_cams_off = np.array(list(it.combinations(range(n_cams), nb_cams_off)))

        if undistort_points:
            calib_params_K_filt = [calib_params_K] * len(id_cams_off)
            calib_params_dist_filt = [calib_params_dist] * len(id_cams_off)
            calib_params_R_filt = [calib_params_R] * len(id_cams_off)
            calib_params_T_filt = [calib_params_T] * len(id_cams_off)
        projection_matrices_filt = [projection_matrices] * len(id_cams_off)

        x_filt = np.vstack([x.copy()] * len(id_cams_off))
        y_filt = np.vstack([y.copy()] * len(id_cams_off))
        x_swapped_filt = np.vstack([x_swapped.copy()] * len(id_cams_off))
        y_swapped_filt = np.vstack([y_swapped.copy()] * len(id_cams_off))
        quality_filt = np.vstack([quality.copy()] * len(id_cams_off))

        if nb_cams_off > 0:
            for i in range(len(id_cams_off)):
                x_filt[i][id_cams_off[i]] = np.nan
                y_filt[i][id_cams_off[i]] = np.nan
                x_swapped_filt[i][id_cams_off[i]] = np.nan
                y_swapped_filt[i][id_cams_off[i]] = np.nan
                quality_filt[i][id_cams_off[i]] = np.nan

        # Excluded cameras index and count
        id_cams_off_tot_new = [np.argwhere(np.isnan(x)).ravel() for x in quality_filt]
        nb_cams_excluded_filt = [
            np.count_nonzero(np.nan_to_num(x) == 0) for x in quality_filt
        ]  # count nans and zeros
        nb_cams_off_tot = max(nb_cams_excluded_filt)
        # print('quality_filt ',quality_filt)
        # print('nb_cams_excluded_filt ', nb_cams_excluded_filt, 'nb_cams_off_tot ', nb_cams_off_tot)
        if nb_cams_off_tot > n_cams - min_cameras_for_triangulation:
            break
        id_cams_off_tot = id_cams_off_tot_new

        # print('still in loop')
        # if undistort_points:
        #     calib_params_K_filt = [
        #         [
        #             c[i]
        #             for i in range(n_cams)
        #             if not np.isnan(quality_filt[j][i]) and not quality_filt[j][i] == 0.0
        #         ]
        #         for j, c in enumerate(calib_params_K_filt)
        #     ]
        #     calib_params_dist_filt = [
        #         [
        #             c[i]
        #             for i in range(n_cams)
        #             if not np.isnan(quality_filt[j][i]) and not quality_filt[j][i] == 0.0
        #         ]
        #         for j, c in enumerate(calib_params_dist_filt)
        #     ]
        #     calib_params_R_filt = [
        #         [
        #             c[i]
        #             for i in range(n_cams)
        #             if not np.isnan(quality_filt[j][i]) and not quality_filt[j][i] == 0.0
        #         ]
        #         for j, c in enumerate(calib_params_R_filt)
        #     ]
        #     calib_params_T_filt = [
        #         [
        #             c[i]
        #             for i in range(n_cams)
        #             if not np.isnan(quality_filt[j][i]) and not quality_filt[j][i] == 0.0
        #         ]
        #         for j, c in enumerate(calib_params_T_filt)
        #     ]
        # projection_matrices_filt = [
        #     [
        #         p[i]
        #         for i in range(n_cams)
        #         if not np.isnan(quality_filt[j][i]) and not quality_filt[j][i] == 0.0
        #     ]
        #     for j, p in enumerate(projection_matrices_filt)
        # ]

        # print('\nnb_cams_off', repr(nb_cams_off), 'nb_cams_excluded', repr(nb_cams_excluded_filt))
        # print('quality ', repr(quality))
        # print('y ', repr(y))
        # print('x ', repr(x))
        # print('x_swapped ', repr(x_swapped))
        # print('quality_filt ', repr(quality_filt))
        # print('x_filt ', repr(x_filt))
        # print('id_cams_off_tot ', id_cams_off_tot)

        x_filt = [
            np.array(
                [
                    xx
                    for ii, xx in enumerate(x)
                    if not np.isnan(quality_filt[i][ii]) and not quality_filt[i][ii] == 0.0
                ]
            )
            for i, x in enumerate(x_filt)
        ]
        y_filt = [
            np.array(
                [
                    xx
                    for ii, xx in enumerate(x)
                    if not np.isnan(quality_filt[i][ii]) and not quality_filt[i][ii] == 0.0
                ]
            )
            for i, x in enumerate(y_filt)
        ]
        x_swapped_filt = [
            np.array(
                [
                    xx
                    for ii, xx in enumerate(x)
                    if not np.isnan(quality_filt[i][ii]) and not quality_filt[i][ii] == 0.0
                ]
            )
            for i, x in enumerate(x_swapped_filt)
        ]
        y_swapped_filt = [
            np.array(
                [
                    xx
                    for ii, xx in enumerate(x)
                    if not np.isnan(quality_filt[i][ii]) and not quality_filt[i][ii] == 0.0
                ]
            )
            for i, x in enumerate(y_swapped_filt)
        ]
        quality_filt = [
            np.array([xx for ii, xx in enumerate(x) if not np.isnan(xx) and not xx == 0.0])
            for x in quality_filt
        ]
        # print('y_filt ', repr(y_filt))
        # print('x_filt ', repr(x_filt))
        # Triangulate 2D points
        Q_filt = [
            weighted_triangulation(
                projection_matrices_filt[i], x_filt[i], y_filt[i], quality_filt[i]
            )
            for i in range(len(id_cams_off))
        ]

        # Reprojection
        # if undistort_points:
        #     coords_2D_kpt_calc_filt = [
        #         np.array(
        #             [
        #                 cv2.projectPoints(
        #                     np.array(Q_filt[i][:-1]),
        #                     calib_params_R_filt[i][j],
        #                     calib_params_T_filt[i][j],
        #                     calib_params_K_filt[i][j],
        #                     calib_params_dist_filt[i][j],
        #                 )[0].ravel()
        #                 for j in range(n_cams - nb_cams_excluded_filt[i])
        #             ]
        #         )
        #         for i in range(len(id_cams_off))
        #     ]
        #     coords_2D_kpt_calc_filt = [
        #         [coords_2D_kpt_calc_filt[i][:, 0], coords_2D_kpt_calc_filt[i][:, 1]] for i in range(len(id_cams_off))
        #     ]
        # else:
        coords_2D_kpt_calc_filt = [
            reprojection(projection_matrices_filt[i], Q_filt[i]) for i in range(len(id_cams_off))
        ]
        coords_2D_kpt_calc_filt = np.array(coords_2D_kpt_calc_filt, dtype=object)
        x_calc_filt = coords_2D_kpt_calc_filt[:, 0]
        # print('x_calc_filt ', x_calc_filt)
        y_calc_filt = coords_2D_kpt_calc_filt[:, 1]

        # Reprojection error
        error = []
        for config_off_id in range(len(x_calc_filt)):
            q_file = [
                (x_filt[config_off_id][i], y_filt[config_off_id][i])
                for i in range(len(x_filt[config_off_id]))
            ]
            q_calc = [
                (x_calc_filt[config_off_id][i], y_calc_filt[config_off_id][i])
                for i in range(len(x_calc_filt[config_off_id]))
            ]
            error.append(np.mean([euclidean_distance(q_file[i], q_calc[i]) for i in range(len(q_file))]))
        # print('error ', error)

        # Choosing best triangulation (with min reprojection error)
        # print('\n', error)
        # print('len(error) ', len(error))
        # print('len(x_calc_filt) ', len(x_calc_filt))
        # print('len(quality_filt) ', len(quality_filt))
        # print('len(id_cams_off_tot) ', len(id_cams_off_tot))
        # print('min error ', np.nanmin(error))
        # print('argmin error ', np.nanargmin(error))
        error_min = np.nanmin(error)
        # print(error_min)
        best_cams = np.nanargmin(error)
        nb_cams_excluded = nb_cams_excluded_filt[best_cams]

        Q = Q_filt[best_cams][:-1]

        # Swap left and right sides if reprojection error still too high
        if handle_LR_swap and error_min > error_threshold_triangulation:
            # print('handle')
            n_cams_swapped = 1
            error_off_swap_min = error_min
            while (
                error_off_swap_min > error_threshold_triangulation and n_cams_swapped < (n_cams - nb_cams_off_tot) / 2
            ):  # more than half of the cameras switched: may triangulate twice the same side
                # print('SWAP: nb_cams_off ', nb_cams_off, 'n_cams_swapped ', n_cams_swapped, 'nb_cams_off_tot ', nb_cams_off_tot)
                # Create subsets
                id_cams_swapped = np.array(list(it.combinations(range(n_cams - nb_cams_off_tot), n_cams_swapped)))
                # print('id_cams_swapped ', id_cams_swapped)
                x_filt_off_swap = [[x] * len(id_cams_swapped) for x in x_filt]
                y_filt_off_swap = [[y] * len(id_cams_swapped) for y in y_filt]
                # print('x_filt_off_swap ', x_filt_off_swap)
                # print('y_filt_off_swap ', y_filt_off_swap)
                for id_off in range(len(id_cams_off)):  # for each configuration with nb_cams_off_tot removed
                    for id_swapped, config_swapped in enumerate(
                        id_cams_swapped
                    ):  # for each of these configurations, test all subconfigurations with with n_cams_swapped swapped
                        # print('id_off ', id_off, 'id_swapped ', id_swapped, 'config_swapped ',  config_swapped)
                        x_filt_off_swap[id_off][id_swapped][config_swapped] = x_swapped_filt[id_off][
                            config_swapped
                        ]
                        y_filt_off_swap[id_off][id_swapped][config_swapped] = y_swapped_filt[id_off][
                            config_swapped
                        ]

                # Triangulate 2D points
                Q_filt_off_swap = np.array(
                    [
                        [
                            weighted_triangulation(
                                projection_matrices_filt[id_off],
                                x_filt_off_swap[id_off][id_swapped],
                                y_filt_off_swap[id_off][id_swapped],
                                quality_filt[id_off],
                            )
                            for id_swapped in range(len(id_cams_swapped))
                        ]
                        for id_off in range(len(id_cams_off))
                    ]
                )

                # Reprojection
                # if undistort_points:
                #     coords_2D_kpt_calc_off_swap = [
                #         np.array(
                #             [
                #                 [
                #                     cv2.projectPoints(
                #                         np.array(Q_filt_off_swap[id_off][id_swapped][:-1]),
                #                         calib_params_R_filt[id_off][j],
                #                         calib_params_T_filt[id_off][j],
                #                         calib_params_K_filt[id_off][j],
                #                         calib_params_dist_filt[id_off][j],
                #                     )[0].ravel()
                #                     for j in range(n_cams - nb_cams_off_tot)
                #                 ]
                #                 for id_swapped in range(len(id_cams_swapped))
                #             ]
                #         )
                #         for id_off in range(len(id_cams_off))
                #     ]
                #     coords_2D_kpt_calc_off_swap = np.array(
                #         [
                #             [
                #                 [
                #                     coords_2D_kpt_calc_off_swap[id_off][id_swapped, :, 0],
                #                     coords_2D_kpt_calc_off_swap[id_off][id_swapped, :, 1],
                #                 ]
                #                 for id_swapped in range(len(id_cams_swapped))
                #             ]
                #             for id_off in range(len(id_cams_off))
                #         ]
                #     )
                # else:
                coords_2D_kpt_calc_off_swap = [
                    np.array(
                        [
                            reprojection(projection_matrices_filt[id_off], Q_filt_off_swap[id_off][id_swapped])
                            for id_swapped in range(len(id_cams_swapped))
                        ]
                    )
                    for id_off in range(len(id_cams_off))
                ]
                # print(repr(coords_2D_kpt_calc_off_swap))
                x_calc_off_swap = [c[:, 0] for c in coords_2D_kpt_calc_off_swap]
                y_calc_off_swap = [c[:, 1] for c in coords_2D_kpt_calc_off_swap]

                # Reprojection error
                # print('x_filt_off_swap ', x_filt_off_swap)
                # print('x_calc_off_swap ', x_calc_off_swap)
                error_off_swap = []
                for id_off in range(len(id_cams_off)):
                    error_percam = []
                    for id_swapped, config_swapped in enumerate(id_cams_swapped):
                        # print(id_off,id_swapped,n_cams,nb_cams_off)
                        # print(repr(x_filt_off_swap))
                        q_file_off_swap = [
                            (x_filt_off_swap[id_off][id_swapped][i], y_filt_off_swap[id_off][id_swapped][i])
                            for i in range(n_cams - nb_cams_off_tot)
                        ]
                        q_calc_off_swap = [
                            (x_calc_off_swap[id_off][id_swapped][i], y_calc_off_swap[id_off][id_swapped][i])
                            for i in range(n_cams - nb_cams_off_tot)
                        ]
                        error_percam.append(
                            np.mean(
                                [
                                    euclidean_distance(q_file_off_swap[i], q_calc_off_swap[i])
                                    for i in range(len(q_file_off_swap))
                                ]
                            )
                        )
                    error_off_swap.append(error_percam)
                error_off_swap = np.array(error_off_swap)
                # print('error_off_swap ', error_off_swap)

                # Choosing best triangulation (with min reprojection error)
                error_off_swap_min = np.min(error_off_swap)
                best_off_swap_config = np.unravel_index(error_off_swap.argmin(), error_off_swap.shape)

                id_off_cams = best_off_swap_config[0]
                id_swapped_cams = id_cams_swapped[best_off_swap_config[1]]
                Q_best = Q_filt_off_swap[best_off_swap_config][:-1]

                n_cams_swapped += 1

            if error_off_swap_min < error_min:
                error_min = error_off_swap_min
                best_cams = id_off_cams
                Q = Q_best

        # print(error_min)

        nb_cams_off += 1

    # Index of excluded cams for this keypoint
    # print('Loop ended')

    if "best_cams" in locals():
        # print(id_cams_off_tot)
        # print('len(id_cams_off_tot) ', len(id_cams_off_tot))
        # print('id_cams_off_tot ', id_cams_off_tot)
        id_excluded_cams = id_cams_off_tot[best_cams]
        # print('id_excluded_cams ', id_excluded_cams)
    else:
        id_excluded_cams = list(range(n_cams))
        nb_cams_excluded = n_cams
    # print('id_excluded_cams ', id_excluded_cams)

    # If triangulation not successful, error = nan,  and 3D coordinates as missing values
    if error_min > error_threshold_triangulation:
        error_min = np.nan
        Q = np.array([np.nan, np.nan, np.nan])

    return Q, error_min, nb_cams_excluded, id_excluded_cams
