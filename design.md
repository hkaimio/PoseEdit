# Blender Add-on: Pose Data Editor Design

## Overview
This add-on provides tools for editing pose data captured from video, visualized and animated in Blender. It is designed to handle complex scenarios with multiple camera angles and multiple people, providing a workflow to consolidate fragmented tracking data into coherent character poses before editing.

The core class, `PoseData2D`, encapsulates the final, stitched pose data for a single person in a single camera view and manages the associated Blender objects.

## Requirements
- **Video Background:** The video from which pose data was extracted can be loaded and displayed as a synchronized background for the markers and skeleton.
- **Multi-Camera Support:** Support loading data from multiple camera angles into a single Blender scene. Each angle has its own video and pose data, and the user can switch between camera views.
- **Multi-Person Identity Stitching:** Provide a workflow to construct continuous animation tracks for real people by stitching together fragmented tracks from the source data.
- **Data Loading:** Pose data is loaded from a directory of JSON files. The loader also receives a skeleton definition.
- **Visualization:** Each marker is visualized as a small sphere. The skeleton is realized as a Blender armature whose bones connect the markers.
- **Standard Animation Tools:** All editing should be compatible with Blender's native animation tools (Graph Editor, Dope Sheet, etc.).
- **Hierarchical Manipulation:** Provide a tool to select a marker and all its children based on the skeleton structure. This action should also move the transform pivot point to the selected marker's location to facilitate rotating entire limbs.
- **Keyframe Effects:** Manually keyframing a marker automatically sets its likelihood to 1.0. Users must also be able to mark a marker as occluded (not visible) for a range of frames.
- **Data Export:** The edited animation data for a person can be exported to a numpy array.

## Identity Stitching Workflow
This phase allows the user to build continuous tracks for real people from fragmented raw tracking data.

1.  **Initial Visualization:** Upon loading a camera view, all raw tracks from the pose data are loaded and visualized simultaneously. Each raw track will have its own skeleton, markers, a bounding box, and an annotation with its track ID.
2.  **"Real Person" Creation:** The user creates a "Real Person" entity (e.g., "Alice"), which gets a dedicated armature and a unique color.
3.  **Stitching via Keyframed Index:** The Real Person's armature contains a custom property, `active_track_index`, which is keyframed over time. The value of this property at any given frame determines which raw track is used as the data source. The user scrubs the timeline and adds keyframes to this property to switch between source tracks when the person's tracking ID changes.

## Editing and Interaction Workflow
This section details the process of manually correcting the stitched pose data.

1.  **Core Principle:** Editing leverages Blender's standard animation editors. Marker locations are stored as f-curves on their transform channels, making them fully editable in the Graph Editor and Dope Sheet.

2.  **Manual Keyframing:**
    *   When a user moves a marker in the 3D viewport and inserts a keyframe, the add-on will automatically perform two actions on that frame:
        1.  Set the marker's `likelihood` custom property to `1.0`.
        2.  Set the marker's `visible` custom property to `True`.
    *   This reflects that a manual correction is considered a high-confidence observation.

3.  **Handling Occlusions:**
    *   The user can mark a marker as occluded (not visible) over a range of frames.
    *   A UI command will allow them to select a marker and a frame range, and then set the `visible` custom property to `False` and keyframe it accordingly.

4.  **Hierarchical Manipulation:**
    *   A "Select Children" UI command is available (e.g., via context menu or a button).
    *   When the user activates this on a selected marker:
        1.  The command selects the clicked marker and all of its descendants in the skeleton hierarchy (e.g., selecting a shoulder marker also selects the elbow, wrist, and hand).
        2.  Crucially, Blender's transform pivot point is automatically moved to the location of the initially selected marker (the root of the hierarchy).
    *   This allows the user to intuitively rotate or scale the entire limb from the correct joint.

## Key Use Case Flow
1.  **Setup:** Install and enable the add-on. Add camera views (video + pose data) to the project.

2.  **Identity Stitching:** For each camera view, visualize all raw tracks. Create "Real Person" armatures and use the keyframed `active_track_index` property to stitch together the correct animation sequences from the various raw tracks.

3.  **Editing and Refinement:**
    *   Once stitched, hide the raw data visualizations to focus on the "Real Person" armatures.
    *   Use the editing tools described in the **Editing and Interaction Workflow** section to correct the pose. This includes moving markers directly, using the Graph Editor, using the "Select Children" command to pose limbs, and marking occlusions.
    *   Switch between camera views to ensure consistency.

4.  **Export:** Select a "Real Person" and export their final, corrected animation data to a NumPy file.

## Class Design: PoseData2D
Represents a single, continuous pose for one person.

### Constructor
- Parameters:
	- `parent_object`: Blender object (geometry parent).
	- `base_color`: tuple (RGBA).
	- `skeleton`: Skeleton structure.
	- `stitched_pose_data`: The consolidated pose data for a single person, passed in after the identity stitching phase.

### Methods
- `load_pose_data()`: Now takes the `stitched_pose_data` and creates the spheres, armature, and keyframes.
- `select_children(marker_name)`: Selects all child markers and sets the pivot point.
- (Other methods like `update_marker_colors`, `get_animation_array` remain largely the same).

## Data Flow
1.  User sets up camera views (video + pose data directory).
2.  For each view, the user performs identity stitching using the keyframed index method to map raw tracks to final, "Real Person" armatures.
3.  The animation data for the Real Person is dynamically sourced from the underlying raw tracks based on the `active_track_index` property.
4.  After stitching, the user can directly edit the markers on the Real Person's armature using the defined editing workflows.
5.  User exports the final, edited data.

## Extensibility
- Support for 3D pose data by extending `PoseData2D` to `PoseData3D`.
- More advanced editing tools, such as interpolation between keyframes.

## References
- Marker data format: See `2d-markers.py`
- Skeleton structure: See `skeletons.py`