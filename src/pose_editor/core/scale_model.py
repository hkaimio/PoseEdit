import numpy as np
from pose_editor.core.person_facade import RealPersonInstanceFacade
from pose_editor.core.person_3d_view import Person3DView
import bpy



def get_column_index(col_map, marker_name, meas_name):
    try:
        return col_map[(marker_name, meas_name)]
    except KeyError:
        raise ValueError(f"Column ({marker_name}, {meas_name}) not found")

def update_midpoint(data, col_map, marker1, marker2, midpoint_marker):
    for meas in ['x', 'y', 'z']:
        col1 = get_column_index(col_map, marker1, meas)
        col2 = get_column_index(col_map, marker2, meas)
        mid_col = get_column_index(col_map, midpoint_marker, meas)
        data[:, mid_col] = (data[:, col1] + data[:, col2]) / 2

    marker1_interpolated = data[:, get_column_index(col_map, marker1, 'interpolated')]
    marker2_interpolated = data[:, get_column_index(col_map, marker2, 'interpolated')]
    data[:, get_column_index(col_map, midpoint_marker, 'interpolated')] = np.logical_and(marker1_interpolated, marker2_interpolated)

def marker_data(data, col_map, marker: str, meas: list[str]):
    cols = [get_column_index(col_map, marker, m) for m in meas]
    return data[:, cols]

def marker_distance(data: np.ndarray, col_map: dict[tuple[str,str], int], marker1:str, marker2:str):
    """Calculate distances between two markers, computing midpoints if needed."""
    # Check if markers exist, if not try to compute them as midpoints
    marker1 = _ensure_marker_exists(data, col_map, marker1)
    marker2 = _ensure_marker_exists(data, col_map, marker2)

    coords1 = marker_data(data, col_map, marker1, ['x', 'y', 'z'])
    coords2 = marker_data(data, col_map, marker2, ['x', 'y', 'z'])
    distances = np.linalg.norm(coords1 - coords2, axis=1)
    return distances

def _ensure_marker_exists(data: np.ndarray, col_map: dict[tuple[str,str], int], marker_name: str) -> str:
    """Ensure marker exists in col_map with valid data, computing midpoint if needed.

    Returns the marker name to use (either original or computed).
    """
    # Check if marker exists AND has valid data
    has_valid_data = False
    if (marker_name, 'x') in col_map:
        # Check if the marker has any valid (non-NaN) data
        x_col = get_column_index(col_map, marker_name, 'x')
        y_col = get_column_index(col_map, marker_name, 'y')
        z_col = get_column_index(col_map, marker_name, 'z')

        # Check if there's at least some valid data
        has_valid_data = (
            np.any(np.isfinite(data[:, x_col])) and
            np.any(np.isfinite(data[:, y_col])) and
            np.any(np.isfinite(data[:, z_col]))
        )

        if has_valid_data:
            return marker_name
        else:
            print(f"Marker '{marker_name}' exists but has no valid data (all NaN)")

    # Define midpoint computations for missing markers
    midpoint_definitions = {
        'Hip': ('RHip', 'LHip'),
        'Neck': ('RShoulder', 'LShoulder'),
        'Head': ('LEar', 'REar'),
    }

    if marker_name in midpoint_definitions:
        marker1, marker2 = midpoint_definitions[marker_name]

        # Check if source markers exist
        if (marker1, 'x') in col_map and (marker2, 'x') in col_map:
            # Compute midpoint and add to data (or replace existing NaN data)
            for meas in ['x', 'y', 'z']:
                col1 = get_column_index(col_map, marker1, meas)
                col2 = get_column_index(col_map, marker2, meas)
                midpoint_values = (data[:, col1] + data[:, col2]) / 2

                # Check if marker column already exists
                if (marker_name, meas) in col_map:
                    # Replace existing NaN data
                    col_idx = get_column_index(col_map, marker_name, meas)
                    data[:, col_idx] = midpoint_values
                else:
                    # Add new column to data
                    new_col_idx = data.shape[1]
                    data_with_midpoint = np.column_stack([data, midpoint_values])
                    # Update data in-place (this is a bit hacky but works for our use case)
                    data.resize(data_with_midpoint.shape, refcheck=False)
                    data[:] = data_with_midpoint

                    # Add to col_map
                    col_map[(marker_name, meas)] = new_col_idx

            # Add interpolated column (both source markers must be valid)
            try:
                marker1_interp = data[:, get_column_index(col_map, marker1, 'interpolated')]
                marker2_interp = data[:, get_column_index(col_map, marker2, 'interpolated')]
                midpoint_interp = np.logical_and(marker1_interp, marker2_interp)

                if (marker_name, 'interpolated') in col_map:
                    # Replace existing interpolated data
                    col_idx = get_column_index(col_map, marker_name, 'interpolated')
                    data[:, col_idx] = midpoint_interp
                else:
                    # Add new column
                    new_col_idx = data.shape[1]
                    data_with_interp = np.column_stack([data, midpoint_interp])
                    data.resize(data_with_interp.shape, refcheck=False)
                    data[:] = data_with_interp
                    col_map[(marker_name, 'interpolated')] = new_col_idx
            except (KeyError, ValueError):
                # Interpolated column doesn't exist, skip it
                pass

            print(f"Computed midpoint marker '{marker_name}' from '{marker1}' and '{marker2}'")
            return marker_name

    # Marker doesn't exist and can't be computed
    raise ValueError(f"Marker '{marker_name}' not found and cannot be computed as midpoint")

def estimate_marker_distance(data, col_map, marker1, marker2, min_percentile = 0.2, max_percentile = 0.8):
    distances = marker_distance(data, col_map, marker1, marker2)

    # Filter out NaN and infinite values
    valid_distances = distances[np.isfinite(distances)]

    if len(valid_distances) == 0:
        # No valid distances found
        return np.nan, np.nan

    # Filter by percentile range
    min_val = np.percentile(valid_distances, min_percentile * 100)
    max_val = np.percentile(valid_distances, max_percentile * 100)
    filtered_distances = valid_distances[(valid_distances >= min_val) & (valid_distances <= max_val)]

    if len(filtered_distances) == 0:
        # Fallback to all valid distances if filtering removed everything
        filtered_distances = valid_distances

    mean_distance = np.mean(filtered_distances)
    std_distance = np.std(filtered_distances)
    return mean_distance, std_distance

def preprocess_marker_data(data: np.ndarray, col_map: dict[tuple[str,str], int]):
    fake_markers = [("Hip", "RHip", "LHip"), ("Neck", "RShoulder", "LShoulder"), ("Head", "LEar", "REar")]

    for midpoint, m1, m2 in fake_markers:
        update_midpoint(data, col_map, m1, m2, midpoint)

def scale_armature_subset(armature: bpy.types.Object, bone_name: str, scale: float):
    """Scale a bone and its descendants in Edit Mode, using the 3D cursor as pivot.

    Args:
        armature: bpy.types.Object. The armature object.
        bone_name: str. The name of the root bone of the sub-hierarchy to scale.
        scale: float. The scaling factor.
    """
    # Always start from Object Mode
    bpy.ops.object.mode_set(mode='OBJECT')
    # Deselect all objects
    bpy.ops.object.select_all(action='DESELECT')
    # Select and activate the armature
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    # Switch to Edit Mode
    bpy.ops.object.mode_set(mode='EDIT')
    # Deselect all bones
    for b in armature.data.edit_bones:
        b.select = False
        b.select_head = False
        b.select_tail = False

    bone = armature.data.edit_bones[bone_name]
    global_head = armature.matrix_world @ bone.head
    bpy.context.scene.cursor.location = global_head

    bpy.context.scene.tool_settings.transform_pivot_point = 'CURSOR'

    def select_descendants(b):
        b.select = True
        b.select_head = True
        b.select_tail = True
        for child in b.children:
            select_descendants(child)
    select_descendants(bone)
    armature.data.edit_bones.active = bone
    # Find the first 3D View area and WINDOW region
    for area in bpy.context.window.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    override = {'area': area, 'region': region}
                    with bpy.context.temp_override(**override):
                        bpy.ops.transform.resize(
                            value=(scale, scale, scale),
                            orient_type='GLOBAL'
                        )
                    break
            break

    bpy.ops.object.mode_set(mode='OBJECT')


def create_and_scale_armature(measurements: np.ndarray, col_map: dict[tuple[str,str], int], name:str):
    """
    Load and scale a custom Blender armature based on marker measurements.
    - measurements: numpy array of marker measurements
    - col_map: dict mapping (marker_name, measurement) to column index
    - name: name for the imported armature
    """

    # Load the custom rig from the blend file
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(script_dir)), 'assets')
    blend_file = os.path.join(assets_dir, 'opensim-export-armature-wholebody.blend')

    # Import the armature from the blend file
    with bpy.data.libraries.load(blend_file, link=False) as (data_from, data_to):
        data_to.objects = [obj for obj in data_from.objects if obj == 'metarig']

    # Link the imported object to the current scene
    armature = None
    for obj in data_to.objects:
        if obj is not None:
            bpy.context.collection.objects.link(obj)
            armature = obj
            break

    if armature is None:
        raise ValueError(f"Could not find 'metarig' armature in {blend_file}")

    # Rename and set as active
    armature.name = name
    bpy.context.view_layer.objects.active = armature

    bpy.context.scene.tool_settings.transform_pivot_point = 'ACTIVE_ELEMENT'

    # Set rest T-pose for upper arms (example for left arm)
    bpy.ops.object.mode_set(mode='POSE')
    for bone_name in ['upper_arm.L', 'upper_arm.R']:
        bone = armature.pose.bones.get(bone_name)

        if bone:
            head = bone.head
            tail = bone.tail
            diff = tail - head
            if diff.x > 0.0:
                rot_y = np.arctan(diff.z / diff.x)
                bone.rotation_mode = 'XYZ'
                bone.rotation_euler[1] = rot_y * 180.0 / np.pi

    bpy.ops.pose.armature_apply(selected=False)


    bpy.ops.object.mode_set(mode='EDIT')

    # Set pivot point to 3D cursor

    bpy.context.scene.tool_settings.transform_pivot_point = 'ACTIVE_ELEMENT'

    # Scale entire armature by hip-to-shoulder ratio
    bones = armature.data.edit_bones
    model_hip_shoulder = bones['upper_arm.R'].head.z - bones['thigh.R'].head.z
    meas_hip_shoulder = estimate_marker_distance(measurements, col_map, 'Hip', 'Neck')[0]

    if np.isnan(meas_hip_shoulder):
        raise ValueError("Cannot estimate Hip-to-Neck distance. Make sure markers 'Hip' and 'Neck' have valid data.")

    global_scale = meas_hip_shoulder / model_hip_shoulder
    print(f"Global scale: {global_scale:.3f} model_hip_shoulder: {model_hip_shoulder:.3f} meas_hip_shoulder: {meas_hip_shoulder:.3f}")
    scale_armature_subset(armature, "spine", global_scale)

    # Adjust legs
    bpy.ops.object.mode_set(mode='EDIT')
    bones = armature.data.edit_bones  # Refresh bone references
    model_thigh_length = bones['thigh.R'].length
    meas_thigh_length = estimate_marker_distance(measurements, col_map, 'RHip', 'RKnee')[0]
    meas_shin_length = estimate_marker_distance(measurements, col_map, 'RKnee', 'RAnkle')[0]

    if np.isnan(meas_thigh_length):
        raise ValueError("Cannot estimate thigh length. Make sure markers 'RHip' and 'RKnee' have valid data.")
    if np.isnan(meas_shin_length):
        raise ValueError("Cannot estimate shin length. Make sure markers 'RKnee' and 'RAnkle' have valid data.")

    for side in ['L', 'R']:
        thigh_name = f"thigh.{side}"
        shin_name = f"shin.{side}"
        # Scale thigh
        print(f"Scaling {thigh_name}: model {model_thigh_length:.3f} -> meas {meas_thigh_length:.3f}, scale {meas_thigh_length / model_thigh_length:.3f}")
        scale_armature_subset(armature, thigh_name, meas_thigh_length / model_thigh_length)
        # Scale shin
        bpy.ops.object.mode_set(mode='EDIT')
        bones = armature.data.edit_bones  # Refresh bone references after scaling
        model_shin_length = bones[shin_name].length
        print(f"Scaling {shin_name}: model {model_shin_length:.3f} -> meas {meas_shin_length:.3f}, scale {meas_shin_length / model_shin_length:.3f}")
        scale_armature_subset(armature, shin_name, meas_shin_length / model_shin_length)
        # Move leg in Y direction (example, adjust as needed)
        # move_delta = Vector((0, half_hip_width - abs(armature.data.edit_bones[thigh_name].head.y), 0))
        # move_armature_subset(armature, thigh_name, move_delta)

    # Adjust arms
    bpy.ops.object.mode_set(mode='EDIT')
    bones = armature.data.edit_bones  # Refresh bone references
    meas_upper_arm_length = estimate_marker_distance(measurements, col_map, 'RShoulder', 'RElbow')[0]
    meas_forearm_length = estimate_marker_distance(measurements, col_map, 'RElbow', 'RWrist')[0]

    if np.isnan(meas_upper_arm_length):
        raise ValueError("Cannot estimate upper arm length. Make sure markers 'RShoulder' and 'RElbow' have valid data.")
    if np.isnan(meas_forearm_length):
        raise ValueError("Cannot estimate forearm length. Make sure markers 'RElbow' and 'RWrist' have valid data.")

    for side in ['L', 'R']:
        upper_arm_name = f"upper_arm.{side}"
        forearm_name = f"forearm.{side}"

        bpy.ops.object.mode_set(mode='EDIT')
        bones = armature.data.edit_bones  # Refresh bone references
        model_upper_arm_length = bones[upper_arm_name].length
        print(f"Scaling {upper_arm_name}: model {model_upper_arm_length:.3f} -> meas {meas_upper_arm_length:.3f}, scale {meas_upper_arm_length / model_upper_arm_length:.3f}")
        scale_armature_subset(armature, upper_arm_name, meas_upper_arm_length / model_upper_arm_length)
        bpy.ops.object.mode_set(mode='EDIT')
        bones = armature.data.edit_bones  # Refresh bone references after scaling
        model_forearm_length = bones[forearm_name].length
        print(f"Scaling {forearm_name}: model {model_forearm_length:.3f} -> meas {meas_forearm_length:.3f}, scale {meas_forearm_length / model_forearm_length:.3f}")
        scale_armature_subset(armature, forearm_name, meas_forearm_length / model_forearm_length)

    # Adjust head
    bpy.ops.object.mode_set(mode='EDIT')
    bones = armature.data.edit_bones  # Refresh bone references
    neck_to_head_model = bones['face'].tail.z - bones['spine.003'].tail.z
    neck_to_head_meas = estimate_marker_distance(measurements, col_map, 'Neck', 'Head')[0]

    # Head scaling is optional - skip if no valid data
    if not np.isnan(neck_to_head_meas):
        print(f"Scaling head: model {neck_to_head_model:.3f} -> meas {neck_to_head_meas:.3f}, scale {neck_to_head_meas / neck_to_head_model:.3f}")
        scale_armature_subset(armature, 'spine.004', neck_to_head_meas / neck_to_head_model)
    else:
        print("Skipping head scaling: 'Neck' or 'Head' markers have no valid data")



def best_coords_for_measurements(Q_coords, keypoints_names, fastest_frames_to_remove_percent=0.2, close_to_zero_speed=0.2, large_hip_knee_angles=45):
    '''
    Compute the best coordinates for measurements, after removing:
    - 20% fastest frames (may be outliers)
    - frames when speed is close to zero (person is out of frame): 0.2 m/frame, or 50 px/frame
    - frames when hip and knee angle below 45° (imprecise coordinates when person is crouching)

    INPUTS:
    - Q_coords: pd.DataFrame. The XYZ coordinates of each marker
    - keypoints_names: list. The list of marker names
    - fastest_frames_to_remove_percent: float
    - close_to_zero_speed: float (sum for all keypoints: about 50 px/frame or 0.2 m/frame)
    - large_hip_knee_angles: int
    - trimmed_extrema_percent

    OUTPUT:
    - Q_coords_low_speeds_low_angles: pd.DataFrame. The best coordinates for measurements
    '''

    # Add MidShoulder column
    df_MidShoulder = pd.DataFrame((Q_coords['RShoulder'].values + Q_coords['LShoulder'].values) /2)
    df_MidShoulder.columns = ['MidShoulder']*3
    Q_coords = pd.concat((Q_coords.reset_index(drop=True), df_MidShoulder), axis=1)

    # Add Hip column if not present
    n_markers_init = len(keypoints_names)
    if 'Hip' not in keypoints_names:
        df_Hip = pd.DataFrame((Q_coords['RHip'].values + Q_coords['LHip'].values) /2)
        df_Hip.columns = ['Hip']*3
        Q_coords = pd.concat((Q_coords.reset_index(drop=True), df_Hip), axis=1)
    n_markers = len(keypoints_names)

    # Using 80% slowest frames
    sum_speeds = pd.Series(np.nansum([np.linalg.norm(Q_coords[kpt].diff(), axis=1) for kpt in keypoints_names], axis=0))
    sum_speeds = sum_speeds[sum_speeds>close_to_zero_speed] # Removing when speeds close to zero (out of frame)
    if len(sum_speeds)==0:
        logging.warning('All frames have speed close to zero. Make sure the person is moving and correctly detected, or change close_to_zero_speed to a lower value. Not restricting the speeds to be above any threshold.')
        Q_coords_low_speeds = Q_coords
    else:
        min_speed_indices = sum_speeds.abs().nsmallest(int(len(sum_speeds) * (1-fastest_frames_to_remove_percent))).index
        Q_coords_low_speeds = Q_coords.iloc[min_speed_indices].reset_index(drop=True)

    # Only keep frames with hip and knee flexion angles below 45%
    # (if more than 50 of them, else take 50 smallest values)
    try:
        ang_mean = mean_angles(Q_coords_low_speeds, ang_to_consider = ['right knee', 'left knee', 'right hip', 'left hip'])
        Q_coords_low_speeds_low_angles = Q_coords_low_speeds[ang_mean < large_hip_knee_angles]
        if len(Q_coords_low_speeds_low_angles) < 50:
            Q_coords_low_speeds_low_angles = Q_coords_low_speeds.iloc[pd.Series(ang_mean).nsmallest(50).index]
    except:
        Q_coords_low_speeds_low_angles = Q_coords_low_speeds
        logging.warning(f"At least one among the RAnkle, RKnee, RHip, RShoulder, LAnkle, LKnee, LHip, LShoulder markers is missing for computing the knee and hip angles. Not restricting these angles to be below {large_hip_knee_angles}°.")

    if Q_coords_low_speeds_low_angles.empty:
        logging.warning('The selected person might not move, or is crouching for the whole sequence, or is not well detected. Taking all available data instead of filtering them.')
        Q_coords_low_speeds_low_angles = Q_coords.copy()

    if n_markers_init < n_markers:
        Q_coords_low_speeds_low_angles = Q_coords_low_speeds_low_angles.iloc[:,:-3]

    return Q_coords_low_speeds_low_angles


def compute_height(Q_coords, keypoints_names, fastest_frames_to_remove_percent=0.1, close_to_zero_speed=50, large_hip_knee_angles=45, trimmed_extrema_percent=0.5):
    '''
    Compute the height of the person from the trc data.

    INPUTS:
    - Q_coords: pd.DataFrame. The XYZ coordinates of each marker
    - keypoints_names: list. The list of marker names
    - fastest_frames_to_remove_percent: float. Frames with high speed are considered as outliers
    - close_to_zero_speed: float. Sum for all keypoints: about 50 px/frame or 0.2 m/frame
    - large_hip_knee_angles5: float. Hip and knee angles below this value are considered as imprecise
    - trimmed_extrema_percent: float. Proportion of the most extreme segment values to remove before calculating their mean)

    OUTPUT:
    - height: float. The estimated height of the person
    '''

    # Retrieve most reliable coordinates, adding MidShoulder and Hip columns if not present
    Q_coords_low_speeds_low_angles = best_coords_for_measurements(Q_coords, keypoints_names,
                                                                  fastest_frames_to_remove_percent=fastest_frames_to_remove_percent, close_to_zero_speed=close_to_zero_speed, large_hip_knee_angles=large_hip_knee_angles)

    # Automatically compute the height of the person
    feet_pairs = [['RHeel', 'RAnkle'], ['LHeel', 'LAnkle']]
    try:
        rfoot, lfoot = [euclidean_distance(Q_coords_low_speeds_low_angles[pair[0]],Q_coords_low_speeds_low_angles[pair[1]]) for pair in feet_pairs]
    except:
        rfoot, lfoot = 0.10, 0.10
        logging.warning('The Heel marker is missing from your model. Considering Foot to Heel size as 10 cm.')

    ankle_to_shoulder_pairs =  [['RAnkle', 'RKnee'], ['RKnee', 'RHip'], ['RHip', 'RShoulder'],
                                ['LAnkle', 'LKnee'], ['LKnee', 'LHip'], ['LHip', 'LShoulder']]
    try:
        rshank, rfemur, rback, lshank, lfemur, lback = [euclidean_distance(Q_coords_low_speeds_low_angles[pair[0]],Q_coords_low_speeds_low_angles[pair[1]]) for pair in ankle_to_shoulder_pairs]
    except:
        logging.error('At least one of the following markers is missing for computing the height of the person:\
                            RAnkle, RKnee, RHip, RShoulder, LAnkle, LKnee, LHip, LShoulder.\n\
                            Make sure that the person is entirely visible, or use a calibration file instead, or set "to_meters=false".')
        raise ValueError('At least one of the following markers is missing for computing the height of the person:\
                         RAnkle, RKnee, RHip, RShoulder, LAnkle, LKnee, LHip, LShoulder.\
                         Make sure that the person is entirely visible, or use a calibration file instead, or set "to_meters=false".')

    try:
        head_pair = [['MidShoulder', 'Head']]
        head = [euclidean_distance(Q_coords_low_speeds_low_angles[pair[0]],Q_coords_low_speeds_low_angles[pair[1]]) for pair in head_pair][0]
    except:
        head_pair = [['MidShoulder', 'Nose']]
        head = [euclidean_distance(Q_coords_low_speeds_low_angles[pair[0]],Q_coords_low_speeds_low_angles[pair[1]]) for pair in head_pair][0]\
                *1.33
        logging.warning('The Head marker is missing from your model. Considering Neck to Head size as 1.33 times Neck to MidShoulder size.')

    heights = (rfoot + lfoot)/2 + (rshank + lshank)/2 + (rfemur + lfemur)/2 + (rback + lback)/2 + head

    # Remove the 20% most extreme values
    height = trimmed_mean(heights, trimmed_extrema_percent=trimmed_extrema_percent)

    return height
