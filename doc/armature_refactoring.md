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

### Goals
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
