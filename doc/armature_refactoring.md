# Armature Refactoring: PersonDataView (2D Marker Views)

## Overview
This document outlines the design and implementation plan for refactoring `PersonDataView` to use armature bones instead of Empty objects for markers, similar to the refactoring already completed for `Person3DView`.

## Current Architecture (2D Views)

### Data Structures
- **`_marker_objects_by_role`**: `dict[str, BlenderObjRef]` - Maps marker role to Empty object reference
- **`_armature_object`**: `BlenderObjRef` - Armature with connecting bones (visualization only)
- **Marker Objects**: Individual Empty objects for each joint, parented to view root
- **Connecting Bones**: Bones in armature that follow marker Empties via `COPY_LOCATION` and `STRETCH_TO` constraints

### Animation Flow
1. `MarkerData` stores animation in an Action with per-marker slots (layered action system)
2. Each marker Empty gets assigned the shared Action and its specific slot via `dal.assign_action_to_object()`
3. Connecting bones follow the Empties via constraints
4. Bones have drivers for `hide` property based on marker visibility

### Key Methods
- **`_create_marker_objects()`**: Creates Empty objects for each joint
- **`_create_armature()`**: Creates armature with bones constrained to marker Empties
- **`_populate_marker_objects_by_role()`**: Populates dict by reading custom properties from children
- **`connect_to_series()`**: Calls `MarkerData.apply_to_view()` which assigns action/slot to each Empty
- **`get_marker_objects()`**: Returns dict of marker Empties

## Completed Architecture (3D Views - Reference)

### Data Structures
- **`_marker_bones_by_role`**: `dict[str, str]` - Maps marker role to bone name
- **`armature_ref`**: `BlenderObjRef` - Single armature containing both marker and connecting bones
- **Marker Bones**: Bones in "Markers" collection, animated via armature's action
- **Connecting Bones**: Bones with `COPY_LOCATION` and `STRETCH_TO` constraints targeting marker bones

### Animation Flow
1. `MarkerData` stores animation in per-marker slots
2. `dal.create_armature_action_from_marker_data()` copies F-curves from MarkerData slots to armature slot, remapping data paths from `"location"` to `'pose.bones["Name"].location'`
3. Armature assigned single action with one slot; all bones animated via channelbag
4. Virtual markers (Hip, Neck, Head) use drivers on pose bone properties

### Key Differences from Old 3D System
- No separate marker objects - bones serve as both markers and visualization
- Single armature action instead of per-marker object actions
- Data path remapping: `"location"` → `'pose.bones["Name"].location'`
- Custom properties on bones instead of objects
- Bone custom shapes for visualization (WGT-sphere, WGT-line)

## Proposed Architecture (2D Views - New)

### Critical Realization: Broader Scope Than Initially Expected

**IMPORTANT**: After deeper analysis, this refactoring requires changes to **MarkerData's storage architecture** itself, not just PersonDataView. The scope is significantly larger than initially documented.

### Why MarkerData Needs to Change

**Current MarkerData Architecture**:
- Creates Actions with **per-marker slots** (one slot per marker name)
- Each slot has F-curves with simple data paths: `"location"`, `'["quality"]'`
- Works for Empty objects because each object gets its own slot

**Problem for Bone-Based Views**:
- Armatures need **single slot** with all bones animated via one channelbag
- F-curves must have bone-specific data paths: `'pose.bones["MarkerName"].location'`
- Cannot reuse per-marker slot architecture designed for objects

**Current Workaround (Person3DView)**:
- `dal.create_armature_action_from_marker_data()` **copies** F-curves from MarkerData slots → new armature slot
- **Doubles storage**: Data exists in both MarkerData (per-marker slots) and armature (single slot)
- Only works because 3D data is write-once (triangulation output)

**Why Workaround Fails for 2D Views**:
- 2D data is **read AND written** continuously:
  - Stitching: `update_frame_if_needed()` writes single-frame data from raw tracks → stitched views
  - Operators: Copy stitching keyframes between views
  - Shifts: `shift()` method moves entire timeline
- If MarkerData stores per-marker slots BUT views use armature slots, updates to one don't reflect in the other
- Must keep both in sync or pick one as source of truth

### Affected Files & Systems - Complete Analysis

#### Core Files Requiring Major Changes

1. **`marker_data.py`** (MAJOR REFACTORING NEEDED)
   - Current: `set_animation_data()` creates per-marker slots
   - Current: `apply_to_view()` assigns action+slot to each Empty object
   - Current: `shift()` operates on per-marker slots
   - New: Must store data in **armature-compatible format** (single slot, bone data paths)
   - New: `apply_to_view()` must handle both objects (legacy) and bones (new)
   - Impact: **Changes internal storage format**

2. **`person_data_view.py`** (MAJOR REFACTORING - AS PLANNED)
   - Change `_marker_objects_by_role` → `_marker_bones_by_role`
   - Merge `_create_marker_objects()` + `_create_armature()` → `_create_armature_with_bones()`
   - Update `connect_to_series()` to connect armature to MarkerData
   - Update `update_frame_if_needed()` to write to armature bones
   - Update `set_requested_source_id()` - likely needs refactoring for bone data

3. **`person_3d_view.py`** (MINOR - already bone-based, may need sync)
   - Currently uses workaround: copies data from MarkerData → armature
   - If MarkerData changes to armature format, may simplify
   - `connect_to_series()` might no longer need `create_armature_action_from_marker_data()`

#### Files Reading MarkerData Animation (MODERATE IMPACT)

4. **`person_facade.py`** - **Triangulation & Stitching**
   - `triangulate()`: Reads 2D marker data to compute 3D positions
     - Line 337-348: `dal.get_fcurve_from_action(marker_data_2d.action, marker_name, "location", 0/1)`
     - Currently expects per-marker slots with `"location"` data path
     - **NEW**: Must read from armature slot with `'pose.bones["MarkerName"].location'` data path

   - `copy_stitching_from_view()`: Copies `requested_source_id` F-curves
     - Line 145: `dal.get_fcurve_on_object(source_md.data_series_object, '["requested_source_id"]')`
     - **QUESTION**: Where should `requested_source_id`/`applied_source_id` live in bone-based system?
     - Options:
       a) Keep on MarkerData Empty object (separate from armature action)
       b) Move to armature as custom property with F-curve
       c) Create separate "metadata" action slot

   - `bake_stitching_data()`: Calls `update_frame_if_needed()` for all frames
     - Line 190: `pdv.update_frame_if_needed(frame)`
     - Depends on PersonDataView changes

5. **`camera_view.py`** - **Import from JSON**
   - `import_data_from_json()`: Creates raw track PersonDataViews
   - Line ~315: Calls `MarkerData.set_animation_data()` with numpy arrays
   - **Impact**: If MarkerData changes storage format, import logic must adapt
   - **NEW**: Must pass data in armature-compatible column format

#### DAL Functions (MODERATE CHANGES)

6. **`dal.py`**
   - `get_fcurve_from_action()`: Gets F-curve from specific slot
     - Currently: `get_fcurve_from_action(action, slot_name, "location", 0)`
     - **NEW**: Must handle bone data paths: `'pose.bones["Name"].location'`
     - May need new function: `get_bone_fcurve_from_action()`

   - `replace_fcurve_segment_from_numpy()`: Writes data to F-curves
     - Line 1122: Used by `update_frame_if_needed()` for stitching
     - **Impact**: Column format must include bone data paths

   - `create_armature_action_from_marker_data()`: Copies MarkerData → armature
     - Line 655: Currently needed for Person3DView workaround
     - **FUTURE**: May become obsolete if MarkerData natively stores armature format
     - **OR**: May become conversion utility for legacy files

#### Operators (MINOR CHANGES)

7. **`operators.py`**
   - `POSE_EDITOR_OT_create_real_person`: Creates stitched PersonDataViews
     - Line 237-239: `MarkerData.create_new()` → `PersonDataView.create_new(marker_data=...)`
     - Should work if MarkerData/PersonDataView handle armature internally

   - `POSE_EDITOR_OT_assign_source_at_frame`: Sets stitching keyframes
     - Line 319-323: `pdv.set_requested_source_id()` + `update_frame_if_needed()`
     - Depends on PersonDataView changes

   - `POSE_EDITOR_OT_copy_stitching`: Copies stitching between views
     - Line 419: Calls `person_facade.copy_stitching_from_view()`
     - Depends on where `requested_source_id` lives

#### Tests (UPDATES NEEDED)

8. **Test Files** (Many)
   - `test_marker_data.py`: Tests MarkerData creation, animation application
   - `test_person_data_view.py`: Tests stitching, `update_frame_if_needed()`
   - `test_camera_view.py`: Tests import from JSON
   - **Impact**: All tests assuming per-marker slots must be updated

### Design Decision Required: MarkerData Storage Format

We need to decide on **ONE** of these approaches:

#### Option A: MarkerData Stores Armature Format (RECOMMENDED)
**MarkerData creates Actions with armature-compatible structure**:
- Single slot per person (e.g., slot name = armature name)
- F-curves use bone data paths: `'pose.bones["MarkerName"].location'`, `'pose.bones["MarkerName"]["quality"]'`
- Metadata (`requested_source_id`, `applied_source_id`) stored on armature as custom properties with F-curves

**Pros**:
- Single source of truth - no data duplication
- PersonDataView armature directly uses MarkerData action
- Stitching writes directly to final destination
- No sync issues between MarkerData and view

**Cons**:
- Breaking change to MarkerData API
- Must handle legacy files with per-marker slots
- camera_view.import_from_json() must construct bone data paths

**Migration**:
- Detect old format (per-marker slots) vs new format (armature slot) in `from_blender_object()`
- Provide conversion utility for existing files

#### Option B: Dual Format Support (COMPLEX)
**MarkerData maintains BOTH formats**:
- Stores data in per-marker slots (backward compat)
- When `apply_to_view()` detects bone-based view, creates armature slot dynamically
- Keeps both in sync on writes

**Pros**:
- Backward compatible
- Gradual migration possible

**Cons**:
- Complex sync logic - error-prone
- Still doubles storage
- Performance overhead keeping formats in sync
- Stitching workflow becomes complicated (which format to update?)

**Verdict**: Avoid this approach - too complex

#### Option C: Separate Storage for Object vs Bone Views (NOT RECOMMENDED)
**Create two MarkerData subclasses**:
- `ObjectMarkerData`: Per-marker slots (legacy)
- `ArmatureMarkerData`: Armature slot (new)

**Pros**:
- Clean separation of concerns
- No sync issues

**Cons**:
- Code duplication
- Difficult to migrate existing data
- Operators must handle both types
- Violates DRY principle

### Recommended Approach: Option A with Phased Migration

#### Phase 0: Design & Documentation (BEFORE CODE CHANGES)
1. Define new MarkerData storage schema:
   - Slot naming: Use armature object name (e.g., `"PV.cam1_Alice_Armature"`)
   - Data path format: `'pose.bones["MarkerName"].location'`, `'pose.bones["MarkerName"]["quality"]'`
   - Metadata storage: Armature custom properties with F-curves

2. Design backward compatibility:
   - Detection: Check if action has per-marker slots or armature slot
   - Conversion: Utility to remap per-marker slots → armature slot

3. Update ALL affected functions' signatures and contracts
4. Create detailed test plan covering migration scenarios

#### Phase 1: MarkerData Core Refactoring
1. Update `MarkerData.__init__()` and `create_new()`:
   - Accept `armature_ref` parameter (optional for backward compat)
   - If armature provided, create single slot with armature name
   - Set `self._is_armature_based = True/False`

2. Update `set_animation_data()` and `set_animation_data_from_numpy()`:
   - Check `_is_armature_based` flag
   - If armature-based: construct bone data paths from column tuples
   - Column format: `(marker_name, property, index)` → `'pose.bones["{marker_name}"].{property}'` or `'pose.bones["{marker_name}"]["{property}"]'`

3. Update `apply_to_view()`:
   - Detect if view is object-based or bone-based (check `hasattr(view, 'armature_ref')`)
   - Object-based: Use existing per-marker slot assignment
   - Bone-based: Assign single armature slot to armature object

4. Add conversion methods:
   - `convert_to_armature_format(armature_ref)`: Migrates per-marker slots → armature slot
   - `_remap_data_path()`: Helper to convert `"location"` → `'pose.bones["Name"].location'`

5. Update `shift()`:
   - Must work on both formats
   - Use `dal.shift_action()` which operates on all F-curves regardless of format

#### Phase 2: PersonDataView Refactoring (AS ORIGINALLY PLANNED)
- See original phases 1-3 in document above
- Key addition: Pass armature_ref to MarkerData.create_new()

#### Phase 3: Update Data Readers
1. **person_facade.triangulate()**:
   - Change F-curve lookups to use armature-aware helper
   - New helper: `get_marker_fcurve(marker_data, marker_name, property, index)`:
     - Detects format
     - Returns correct F-curve from either per-marker slot or armature slot

2. **Stitching system**:
   - Move `requested_source_id`/`applied_source_id` to armature custom properties
   - Update `update_frame_if_needed()` to read/write armature bone F-curves
   - Update `set_requested_source_id()` to work with armature

3. **camera_view.import_from_json()**:
   - When creating MarkerData, pass armature_ref from PersonDataView
   - Construct column tuples with marker names (helper converts to bone paths)

#### Phase 4: DAL Updates
1. Add `get_bone_fcurve_from_armature_action()`:
   - Helper to get F-curve with bone data path
   - `get_bone_fcurve_from_armature_action(action, armature_slot_name, bone_name, property, index)`

2. Consider deprecating `create_armature_action_from_marker_data()`:
   - Still useful for conversion/migration
   - May not be needed for new workflow

#### Phase 5: Testing & Migration
1. Unit tests for MarkerData dual-format support
2. Integration test: Import JSON → create bone-based view → verify animation
3. Integration test: Stitching workflow with bone-based views
4. Integration test: Triangulation from bone-based 2D views → bone-based 3D view
5. Migration script for existing .blend files
6. Performance benchmarking (bone-based should be faster - fewer objects)

### Bone Collection Organization (UPDATED PER USER REQUEST)

**Body Part Collections for Both Marker and Connecting Bones**:
- Create collections: `Head`, `Torso`, `Arms`, `Legs` (matching skeleton body parts)
- **Marker Bones**: Assign to body part collection based on `skeleton.body_part(marker_name)`
- **Connecting Bones**: Assign to **parent marker's body part collection**
  - Example: Bone connecting `LShoulder` (Arms) → `LElbow` (Arms) goes to `Arms`
  - Example: Bone connecting `Neck` (Torso) → `Nose` (Head) goes to `Torso` (parent's collection)
- **Remove "Markers" collection** - all bones in body part collections for consistency

**Rationale**:
- Consistent with Person3DView architecture
- Better organization for animation workflow
- Easier to show/hide groups by body part
- Parent's collection makes sense: bone originates from parent marker

### Goals (UPDATED)
1. **Consistency**: Match Person3DView architecture for maintainability
2. **Performance**: Reduce object count (remove ~133 Empties per person view)
3. **Cleaner Hierarchy**: Single armature instead of armature + marker Empties
4. **Better Visualization**: Custom bone shapes (smaller spheres for 2D markers)

### Data Structures (Changed)
```python
# Before
_marker_objects_by_role: dict[str, BlenderObjRef]  # Empty objects
_armature_object: BlenderObjRef                     # Separate armature

# After
_marker_bones_by_role: dict[str, str]              # Bone names
armature_ref: BlenderObjRef                         # Single armature
```

### Blender Representation
- **Root Object**: PV.cam1_person0 (Empty, unchanged)
- **Armature Object**: PV.cam1_person0_Armature (child of root)
  - **Marker Bones**: In "Markers" bone collection
    - Custom properties: `MARKER_ROLE`, `BODY_PART`, `quality` (animated)
    - Custom shape: WGT-sphere, scale=0.02, wire_width=3.0
    - Animated via armature's action with remapped F-curves
  - **Connecting Bones**: In body part collections (Head, Torso, Arms, Legs)
    - Constraints: `COPY_LOCATION` → marker bone, `STRETCH_TO` → marker bone
    - Custom shape: WGT-line, scale=1.0, wire_width=3.0
    - Driver: `hide` property based on marker bone visibility

### Animation Flow (New)
1. `MarkerData` stores animation in per-marker slots (unchanged)
2. `PersonDataView.connect_to_series()` calls:
   - `dal.create_armature_action_from_marker_data(armature_ref, marker_data)`
   - Copies F-curves from MarkerData slots → armature slot
   - Remaps: `"location"` → `'pose.bones["MarkerName"].location'`
   - Remaps: `'["quality"]'` → `'pose.bones["MarkerName"]["quality"]'`
3. Armature assigned single action; all bones animate via channelbag
4. Connecting bones follow marker bones via constraints (targets are now bones, not objects)

## Implementation Plan

### Phase 1: Data Structure Refactoring
**File**: `person_data_view.py`

#### Changes:
1. **Class attributes**:
   ```python
   # Change
   self._marker_objects_by_role: dict[str, BlenderObjRef]
   # To
   self._marker_bones_by_role: dict[str, str]

   # Change
   self._armature_object: BlenderObjRef
   # To
   self.armature_ref: BlenderObjRef
   ```

2. **`_init_from_blender_ref()`**:
   - Change `_populate_marker_objects_by_role()` to `_populate_marker_bones_by_role()`
   - Populate `_marker_bones_by_role` by reading `MARKER_ROLE` custom property from armature bones

3. **`create_new()`**:
   - Remove `_create_marker_objects()` call
   - Merge marker + armature creation into `_create_armature_with_bones(body_part_collections)`
   - Remove `_populate_marker_objects_by_role()` call (bones created directly, no population needed)

### Phase 2: Armature Creation
**File**: `person_data_view.py`

#### New Method: `_create_armature_with_bones()`
Merges functionality of `_create_marker_objects()` and `_create_armature()`.

**Implementation**:
```python
def _create_armature_with_bones(self, body_part_collections: dict[str, CollectionRef]):
    """Creates an armature with marker bones and connecting bones."""
    import os

    armature_name = f"{self.view_name}_Armature"
    armature_object = dal.get_or_create_object(
        name=armature_name,
        obj_type="ARMATURE",
        collection_name="PersonViews",
        parent=self.view_root_object,
    )
    armature_object._get_obj().color = self.color
    dal.set_armature_display_stick(armature_object)
    self.armature_ref = armature_object

    # Load custom shape widgets
    extension_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    widgets_path = os.path.join(extension_dir, "assets", "widgets.blend")
    sphere_widget = dal.load_widget_from_blend(widgets_path, "WGT-sphere")
    line_widget = dal.load_widget_from_blend(widgets_path, "WGT-line")

    # Create bone collections
    dal.create_bone_collection(armature_object, "Markers")
    for body_part_name in self.skeleton.body_parts():
        dal.create_bone_collection(armature_object, body_part_name)

    # Prepare all bones (markers + connecting)
    bones_to_add = []

    # Add marker bones
    for node in PreOrderIter(self.skeleton._skeleton):
        if not (hasattr(node, "id") and node.id is not None):
            continue
        marker_name = node.name
        bones_to_add.append((marker_name, (0, 0, 0), (0, 0.01, 0)))
        self._marker_bones_by_role[marker_name] = marker_name

    # Add connecting bones
    for node in self.skeleton._skeleton.descendants:
        if node.parent and hasattr(node, "id") and node.id is not None:
            parent_marker_role = node.parent.name
            child_marker_role = node.name
            bone_name = f"{parent_marker_role}-{child_marker_role}"
            bones_to_add.append((bone_name, (0, 0, 0), (0, 1, 0)))

    # Create all bones in one edit mode session
    dal.add_bones_in_bulk(armature_object, bones_to_add)

    # Set custom properties and collections for marker bones
    for node in PreOrderIter(self.skeleton._skeleton):
        if not (hasattr(node, "id") and node.id is not None):
            continue
        marker_name = node.name
        body_part = self.skeleton.body_part(marker_name)

        # Set custom properties on bone
        dal.set_bone_custom_property(armature_object, marker_name, dal.MARKER_ROLE, marker_name)
        dal.set_bone_custom_property(armature_object, marker_name, dal.BODY_PART, body_part)

        # Initialize quality custom property (will be animated by F-curves)
        armature_obj = armature_object._get_obj()
        pose_bone = armature_obj.pose.bones.get(marker_name)
        if pose_bone:
            pose_bone["quality"] = 0.0

        # Move to Markers collection
        dal.move_bone_to_collection(armature_object, marker_name, "Markers")

        # Set custom shape
        if sphere_widget:
            dal.set_bone_custom_shape(
                armature_object, marker_name, sphere_widget,
                scale=0.02, wireframe=True, wire_width=3.0
            )

    # Add constraints to connecting bones
    for node in self.skeleton._skeleton.descendants:
        if not (node.parent and hasattr(node, "id") and node.id is not None):
            continue

        parent_marker_role = node.parent.name
        child_marker_role = node.name
        parent_marker_bone = self._marker_bones_by_role.get(parent_marker_role)
        child_marker_bone = self._marker_bones_by_role.get(child_marker_role)

        if parent_marker_bone and child_marker_bone:
            bone_name = f"{parent_marker_role}-{child_marker_role}"

            # Add constraints (target is armature, subtarget is bone name)
            dal.add_bone_constraint(
                armature_object, bone_name, "COPY_LOCATION",
                armature_object, parent_marker_bone
            )
            dal.add_bone_constraint(
                armature_object, bone_name, "STRETCH_TO",
                armature_object, child_marker_bone
            )

            # Add driver for hide property
            expression = "var1 or var2"
            variables = [
                ("var1", "SINGLE_PROP", armature_object._id,
                 f'pose.bones["{parent_marker_bone}"].hide'),
                ("var2", "SINGLE_PROP", armature_object._id,
                 f'pose.bones["{child_marker_bone}"].hide'),
            ]
            dal.add_bone_driver(armature_object, bone_name, "hide", expression, variables)

            # Move to body part collection
            body_part = self.skeleton.body_part(child_marker_role)
            dal.move_bone_to_collection(armature_object, bone_name, body_part)

            # Set custom shape
            if line_widget:
                dal.set_bone_custom_shape(
                    armature_object, bone_name, line_widget,
                    scale=1.0, wireframe=True, wire_width=3.0
                )
```

**Key Differences from 3D Version**:
- No virtual markers (Hip, Neck, Head) in 2D views - these are detection-based
- Smaller sphere scale (0.02 vs 0.02) - same size for consistency
- Driver for connecting bone `hide` property targets pose bones, not objects
- Custom property `quality` instead of `reprojection_error`, `contributing_cam_count`, etc.

#### Method to Remove: `_create_marker_objects()`
Delete entirely - functionality merged into `_create_armature_with_bones()`.

#### Method to Replace: `_create_armature()`
Delete and replace with `_create_armature_with_bones()` above.

#### Method to Replace: `_populate_marker_objects_by_role()`
Rename to `_populate_marker_bones_by_role()`:
```python
def _populate_marker_bones_by_role(self):
    """Populates the _marker_bones_by_role dictionary by reading bone custom properties."""
    self._marker_bones_by_role = {}
    if not self.armature_ref:
        return

    armature_obj = self.armature_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        return

    for bone in armature_obj.data.bones:
        marker_role = dal.get_bone_custom_property(self.armature_ref, bone.name, dal.MARKER_ROLE)
        if marker_role:
            self._marker_bones_by_role[marker_role] = bone.name
```

### Phase 3: Animation Connection
**File**: `person_data_view.py`

#### Method to Update: `connect_to_series()`
```python
def connect_to_series(self, marker_data: MarkerData):
    """Connects this view to a MarkerData series.

    This creates an armature action from the marker data by copying and remapping
    F-curves from per-marker slots to the armature's single slot.

    Args:
        marker_data: The MarkerData series to connect to.
    """
    if not self.armature_ref:
        print(f"Warning: Cannot connect {self.view_name} - no armature found.")
        return

    # Create armature action from marker data
    dal.create_armature_action_from_marker_data(self.armature_ref, marker_data)

    # Store reference to marker data
    dal.set_custom_property(
        self.view_root_object,
        dal.MARKER_DATA_ID,
        marker_data.data_series_object_name
    )
```

**Key Changes**:
- Remove call to `marker_data.apply_to_view(self)` (applied to objects, not bones)
- Add call to `dal.create_armature_action_from_marker_data()` (same as Person3DView)
- This function already exists in DAL from 3D refactoring

#### Method to Update: `get_marker_objects()`
Rename to `get_marker_bones()` for consistency:
```python
def get_marker_bones(self) -> dict[str, str]:
    """Returns a dictionary of marker bone names in this view, keyed by their role."""
    return self._marker_bones_by_role
```

### Phase 4: MarkerData Integration
**File**: `marker_data.py`

#### Method to Update: `apply_to_view()`
This method is currently called by `PersonDataView.connect_to_series()`. After refactoring, it should:
1. Check if the view is using bones or objects
2. Route to appropriate handler

**Two Options**:

**Option A: Keep for backward compatibility, add bone support**
```python
def apply_to_view(self, person_data_view: "PersonDataView"):
    """Applies this data series' Action to a Person View hierarchy.

    Supports both object-based views (legacy) and bone-based views (new).

    Args:
        person_data_view: The PersonDataView object.
    """
    if self.action is None:
        return

    # Check if this is a bone-based view
    if hasattr(person_data_view, 'armature_ref') and person_data_view.armature_ref:
        # Bone-based view: use armature action creation
        dal.create_armature_action_from_marker_data(
            person_data_view.armature_ref, self
        )
    else:
        # Object-based view: legacy behavior
        for marker_role, marker_obj_ref in person_data_view.get_marker_objects().items():
            if dal.action_has_slot(self.action, marker_role):
                dal.assign_action_to_object(marker_obj_ref, self.action, marker_role)
```

**Option B: Remove and handle in PersonDataView (RECOMMENDED)**
Since `PersonDataView.connect_to_series()` will call `dal.create_armature_action_from_marker_data()` directly, `apply_to_view()` is no longer needed for PersonDataView.

However, check if `apply_to_view()` is used elsewhere:
```bash
grep -r "apply_to_view" src/
```

If only used by PersonDataView, we can deprecate it. If used by other systems, keep with Option A.

**Recommendation**: Option B - remove call to `apply_to_view()` from PersonDataView, keep method for backward compatibility but mark as deprecated.

### Phase 5: DAL Updates
**File**: `dal.py`

All required DAL functions already exist from Person3DView refactoring:
- ✅ `load_widget_from_blend()` - Loads widget meshes
- ✅ `set_bone_custom_shape()` - Assigns custom shapes with scale/wire width
- ✅ `set_bone_custom_property()` - Sets properties on bones
- ✅ `get_bone_custom_property()` - Gets properties from bones
- ✅ `add_bone_driver()` - Adds drivers to pose bones (with array index handling)
- ✅ `create_armature_action_from_marker_data()` - Copies F-curves with remapping
- ✅ `add_bone_constraint()` - Adds constraints to bones

**Potential Enhancement**:
The driver creation for connecting bone `hide` property needs pose bone data paths. Current `add_bone_driver()` expects object IDs in variables. May need to verify it handles bone-to-bone drivers correctly.

**Test**: Verify driver variables can reference pose bone properties:
```python
variables = [
    ("var1", "SINGLE_PROP", armature_id, 'pose.bones["BoneName"].hide'),
]
```

This should work as-is since drivers accept full data paths.

## Migration Path

### For Existing Scenes
Existing PersonDataView objects (with Empty markers) will continue to work. New views created will use bones.

**Detection**:
```python
def is_bone_based(self) -> bool:
    """Returns True if this view uses bones instead of objects."""
    return hasattr(self, 'armature_ref') and self.armature_ref is not None
```

### Conversion Tool (Optional Future Work)
Create operator to convert existing object-based views to bone-based:
1. Create new armature with bones
2. Copy animation data from object actions to armature action
3. Delete old marker objects
4. Update references

## Testing Strategy

### Unit Tests
1. **Bone Creation**:
   - Verify all marker bones created in "Markers" collection
   - Verify connecting bones in body part collections
   - Verify custom properties on bones

2. **Animation Application**:
   - Verify `dal.create_armature_action_from_marker_data()` creates action
   - Verify F-curves remapped correctly
   - Verify armature assigned action with correct slot

3. **Constraints**:
   - Verify COPY_LOCATION targets marker bones
   - Verify STRETCH_TO targets marker bones
   - Verify hide drivers reference pose bone properties

4. **Custom Shapes**:
   - Verify widgets loaded
   - Verify shapes assigned with correct scale/wire width

### Integration Tests
1. **2D View Creation**:
   - Create camera view
   - Create marker data
   - Create person data view
   - Verify armature structure
   - Verify animation plays correctly

2. **Stitching Workflow**:
   - Create multiple raw tracks
   - Create stitched view
   - Set requested_source_id keyframes
   - Verify `update_frame_if_needed()` works with bone-based views

3. **Triangulation Workflow**:
   - Create 2D views (bone-based)
   - Run triangulation
   - Verify 3D view created
   - Verify both 2D and 3D views use consistent bone architecture

## Risks & Mitigations

### Risk 1: Backward Compatibility
**Issue**: Existing .blend files have object-based PersonDataViews.
**Mitigation**: Keep `from_blender_object()` smart - detect whether objects or bones exist.

### Risk 2: Performance Impact
**Issue**: Creating bones might be slower than creating Empties.
**Mitigation**: Bulk bone creation via `add_bones_in_bulk()` minimizes edit mode transitions.

### Risk 3: Driver Complexity
**Issue**: Bone-to-bone drivers for `hide` property might not work.
**Mitigation**: Test early; fall back to alternative visibility control if needed.

### Risk 4: Custom Shape Loading
**Issue**: widgets.blend might not be found in all environments.
**Mitigation**: Graceful degradation - if widgets not found, bones display as default shapes.

## Success Criteria

1. ✅ PersonDataView creates single armature with marker + connecting bones
2. ✅ Marker bones in "Markers" collection with custom properties
3. ✅ Connecting bones follow marker bones via constraints
4. ✅ Animation data from MarkerData applied to armature via remapped F-curves
5. ✅ Custom shapes (sphere/line) display correctly
6. ✅ Stitching workflow (`update_frame_if_needed()`) works with bone-based views
7. ✅ Consistent architecture between 2D (PersonDataView) and 3D (Person3DView)
8. ✅ No performance regression compared to object-based approach

## Implementation Checklist

- [ ] Phase 1: Data structure refactoring
  - [ ] Change `_marker_objects_by_role` → `_marker_bones_by_role`
  - [ ] Change `_armature_object` → `armature_ref`
  - [ ] Update `_init_from_blender_ref()`
  - [ ] Update `create_new()`

- [ ] Phase 2: Armature creation
  - [ ] Implement `_create_armature_with_bones()`
  - [ ] Delete `_create_marker_objects()`
  - [ ] Delete `_create_armature()`
  - [ ] Rename `_populate_marker_objects_by_role()` → `_populate_marker_bones_by_role()`

- [ ] Phase 3: Animation connection
  - [ ] Update `connect_to_series()`
  - [ ] Rename `get_marker_objects()` → `get_marker_bones()`

- [ ] Phase 4: MarkerData integration
  - [ ] Update or deprecate `apply_to_view()`

- [ ] Phase 5: Testing
  - [ ] Test 2D view creation
  - [ ] Test animation playback
  - [ ] Test stitching workflow
  - [ ] Test triangulation end-to-end

## Timeline Estimate
- **Phase 1**: 1 hour (data structure changes)
- **Phase 2**: 2 hours (armature creation logic)
- **Phase 3**: 30 minutes (animation connection)
- **Phase 4**: 30 minutes (MarkerData updates)
- **Phase 5**: 2 hours (testing and bug fixes)
- **Total**: ~6 hours

## Notes
- This refactoring follows the exact pattern established for Person3DView
- Main difference: 2D views have `quality` property, 3D views have `reprojection_error`, `contributing_cam_count`, camera flags
- Driver for connecting bone `hide` requires careful data path construction for bone targets
- Custom shape scale for 2D markers might need tuning based on visual feedback
