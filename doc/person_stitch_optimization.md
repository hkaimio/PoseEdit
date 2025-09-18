# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

# Design: On-Demand Person Stitching Optimization

## 1. Overview

This document details the design for optimizing the 2D identity stitching workflow. The current implementation suffers from poor performance on long animation sequences as it performs a bulk copy of keyframe data whenever a source track is assigned. This is a blocking operation that makes the UI unresponsive.

The new design replaces this with a lazy, on-demand, frame-by-frame copy mechanism. The core idea is to separate the user's *request* for a data source from the *application* of that data. The expensive data copy operation is deferred to a background process that runs on frame changes, making the interactive stitching process instantaneous for the user.

## 2. Core Components

### 2.1. Frame Change Handler (`core.frame_handler.py`)

A new global handler module will be created to manage callbacks for Blender's `frame_change_post` application handler. This provides a centralized and decoupled way for different parts of the add-on to react to frame changes, preventing multiple handlers from being registered for the same event.

-   **`FrameHandler` (Singleton Class):**
    -   `_callbacks`: A list of callable functions to be executed on frame change.
    -   `register(callback: Callable)`: Adds a function to the `_callbacks` list.
    -   `unregister(callback: Callable)`: Removes a function from the `_callbacks` list.
    -   `_on_frame_change(scene)`: The actual function that will be registered with `bpy.app.handlers.frame_change_post`. It iterates through all registered `_callbacks` and executes them, passing the `scene` as an argument.
-   **Registration:** An instance of the `FrameHandler` will be created and registered with Blender in the add-on's main `register()` function and unregistered in the `unregister()` function.

### 2.2. Data Model Changes (`core.person_data_view.py`)

The `PersonDataView` class, when representing a "Real Person" (not a raw track), will be updated to include two new animated properties. These properties will live on the associated `MarkerData` Empty object, allowing them to be animated within the person's master Action.

-   **New Custom Properties on the `MarkerData` Empty:**
    -   `requested_source_id` (Integer): Stores the `track_id` of the raw `PersonDataView` that the user has requested for a given frame segment.
        -   **Animation:** This property will have a **sparse**, "stepped" f-curve. Keyframes are only inserted when the user explicitly assigns a new source track via the UI.
    -   `applied_source_id` (Integer): Stores the `track_id` of the raw `PersonDataView` whose data has actually been copied into this `PersonDataView`'s action for a given frame.
        -   **Animation:** This property will have a **dense** f-curve, with a keyframe on every frame of the scene. This serves as a record of what has been processed.

-   **`PersonDataView` Class Updates:**
    -   `__init__`: If the view is for a "Real Person", it will register its `_check_and_update_frame` method with the global `FrameHandler`.
    -   `_check_and_update_frame(scene)`: This is the callback function that gets executed on every frame change.
    -   `set_requested_source_id(track_id: int, frame: int)`: A new method that inserts a keyframe on the `requested_source_id` property at the specified frame.

### 2.3. Pre-computation "Baking" (`core.person_facade.py`)

A mechanism is required to ensure all on-demand data is fully copied before running operations (like triangulation) that depend on the complete, up-to-date data.

-   **`RealPersonInstanceFacade.bake_stitching_data()`:**
    -   This new method will be called by operators like `PE_OT_TriangulatePerson` before they proceed.
    -   It iterates through every `PersonDataView` associated with the `RealPersonInstance`.
    -   For each view, it iterates through every frame in the scene's frame range.
    -   It calls a new method, `person_data_view.update_frame_if_needed(frame)`, which performs the core copy logic if `requested` != `applied` at that frame.

## 3. Workflow Changes

### 3.1. "Assign Source at Current Frame" Operator (`blender.operators.PE_OT_AssignTrack`)

The `execute` method of this operator will be significantly simplified to make it instantaneous.

1.  Get the current frame from the context.
2.  Get the active `RealPersonInstanceFacade` and the selected `track_id` from the UI.
3.  Find the corresponding "Real Person" `PersonDataView` for the active camera view.
4.  Call `person_data_view.set_requested_source_id(track_id, current_frame)`.
5.  **Immediate Feedback:** To prevent visual lag while scrubbing, the operator will explicitly trigger an update for the current, previous, and next frames by calling `person_data_view.update_frame_if_needed()` for `frame-1`, `frame`, and `frame+1`.

This change removes the slow, blocking bulk-copy operation from the user-facing operator.

### 3.2. On Frame Change (The Core Logic)

This logic resides in `PersonDataView._check_and_update_frame(scene)` and its helper `update_frame_if_needed(frame)`.

1.  **`_check_and_update_frame(scene)`:**
    -   Gets the current frame from the `scene`.
    -   Calls `self.update_frame_if_needed(scene.frame_current)`.
    -   To improve scrubbing responsiveness, it also calls `self.update_frame_if_needed(scene.frame_current - 1)` and `self.update_frame_if_needed(scene.frame_current + 1)`.

2.  **`update_frame_if_needed(frame)`:**
    -   **Guard Clause:** If `frame` is outside the scene range, return.
    -   **Evaluate Properties:** Get the values of `requested_source_id` and `applied_source_id` at the given `frame` by evaluating their respective f-curves.
    -   **Compare:** If `requested_id == applied_id`, do nothing and return. The data is up-to-date for this frame.
    -   **Perform Single-Frame Copy:**
        1.  Find the source `PersonDataView` (raw track) corresponding to `requested_id`.
        2.  If `requested_id` is `-2` ("None"):
            -   Create a single-frame NumPy array with `np.nan` for locations and `0` for quality.
        3.  If a valid source `PersonDataView` is found:
            -   Call `dal.get_animation_data_as_numpy` on the source track's action, but only for the single `frame`.
        4.  Call `dal.replace_fcurve_segment_from_numpy` on the *target* "Real Person" action, for the single `frame` range (`start_frame=frame`, `end_frame=frame`).
        5.  **Update Applied ID:** Insert a keyframe on the `applied_source_id` f-curve at `frame`, setting its value to `requested_id` to mark the operation as complete for this frame.

## 4. API and Data Structure Summary

-   **`core.frame_handler.py`**
    -   `class FrameHandler`:
        -   `register(callback: Callable)`
        -   `unregister(callback: Callable)`

-   **`core.person_data_view.py`**
    -   `class PersonDataView`:
        -   `__init__(...)`: Registers its update method with the `FrameHandler`.
        -   `set_requested_source_id(track_id: int, frame: int)`: Sets a keyframe on the `requested_source_id` f-curve.
        -   `_check_and_update_frame(scene)`: The function that is called by the frame change handler.
        -   `update_frame_if_needed(frame: int)`: The core single-frame copy logic.

-   **`core.person_facade.py`**
    -   `class RealPersonInstanceFacade`:
        -   `bake_stitching_data()`: Iterates through all frames of all associated views and calls `update_frame_if_needed` to ensure data consistency before a major operation.

-   **`blender.operators.py`**
    -   `class PE_OT_AssignTrack`:
        -   `execute()`: Now only calls `set_requested_source_id` and triggers an immediate update for adjacent frames.
    -   `class PE_OT_TriangulatePerson`:
        -   `execute()`: Now calls `facade.bake_stitching_data()` for each selected person before running the main triangulation logic.

## 5. Phased Implementation Plan

1.  **Phase 1: Frame Handler & Data Model.**
    -   Implement the `FrameHandler` singleton in a new file: `src/pose_editor/core/frame_handler.py`.
    -   Register the handler in the add-on's main `__init__.py`.
    -   In `PersonDataView.create_new`, add the `requested_source_id` and `applied_source_id` custom properties to the `MarkerData` object. Initialize `requested_source_id` with a single keyframe at frame 1 (value `-1`) and `applied_source_id` with a keyframe for every frame in the scene range (all with value `-1`).
    -   In `PersonDataView.__init__`, add the logic to register `_check_and_update_frame` with the global `FrameHandler`.

2.  **Phase 2: Operator and Core On-Demand Logic.**
    -   Implement the new simplified logic for the `PE_OT_AssignTrack` operator.
    -   Implement the `set_requested_source_id` method in `PersonDataView`.
    -   Implement the `_check_and_update_frame` and `update_frame_if_needed` methods in `PersonDataView`. This is the most complex part, containing the single-frame copy logic for both valid tracks and the "None" case.

3.  **Phase 3: Baking and Integration.**
    -   Implement the `bake_stitching_data` method in `RealPersonInstanceFacade`.
    -   Update `PE_OT_TriangulatePerson` and any other relevant operators (e.g., future export operators) to call `bake_stitching_data` before they execute their main logic.

4.  **Phase 4: Refactoring.**
    -   The old, slow, bulk-copy logic in `assign_source_track_for_segment` can now be completely removed. The method can be refactored to be a simple wrapper around `set_requested_source_id` or removed entirely, with the operator calling the `PersonDataView` method directly.
