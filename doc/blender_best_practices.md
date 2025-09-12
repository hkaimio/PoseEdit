# Blender Python API Best Practices

This document outlines best practices discovered during the development of the Pose Editor add-on, particularly those related to performance and stability.

## 1. Avoid Rapid Mode Switching in Loops

**Problem:**

Repeatedly toggling between Object Mode and Edit Mode (`bpy.ops.object.mode_set()`) inside a loop is highly unstable and can lead to unpredictable crashes in Blender, often reported as an `EXCEPTION_ACCESS_VIOLATION`.

This issue is especially prevalent when dealing with large amounts of data, such as creating an armature with many bones. Each mode switch forces Blender to tear down and rebuild internal data structures, and doing this hundreds or thousands of times in a tight loop can lead to memory corruption or other internal state errors.

**Bad Practice (Causes Crashes):**

```python
# Anti-pattern: Do NOT do this.
import bpy

armature_obj = bpy.context.object

for i in range(500):
    # Inefficiently enter and exit Edit Mode for every single bone
    bpy.ops.object.mode_set(mode='EDIT')

    # Create one bone
    armature_obj.data.edit_bones.new(f"Bone_{i}")

    # Exit Edit Mode
    bpy.ops.object.mode_set(mode='OBJECT')
```

## 2. Use Bulk Operations

**Solution:**

Perform operations in bulk whenever possible. For tasks that require Edit Mode, structure your code to enter the mode once, perform all necessary actions, and then exit once. This minimizes the overhead of mode switching and is significantly more stable and performant.

**Good Practice (Stable and Performant):**

```python
# Preferred method:
import bpy

armature_obj = bpy.context.object
bones_to_create = []

# First, prepare all the data you need
for i in range(500):
    bone_name = f"Bone_{i}"
    head_pos = (0, 0, i)
    tail_pos = (0, 0, i + 0.5)
    bones_to_create.append((bone_name, head_pos, tail_pos))

# 1. Enter Edit Mode a single time
bpy.ops.object.mode_set(mode='EDIT')

try:
    # 2. Perform all creation operations in one batch
    edit_bones = armature_obj.data.edit_bones
    for name, head, tail in bones_to_create:
        bone = edit_bones.new(name)
        bone.head = head
        bone.tail = tail
finally:
    # 3. Exit Edit Mode a single time
    bpy.ops.object.mode_set(mode='OBJECT')

# 4. If needed, add constraints or drivers in Object Mode after all bones exist
for name, _, _ in bones_to_create:
    pose_bone = armature_obj.pose.bones.get(name)
    # ... add constraints to pose_bone ...

```

By following this "bulk operation" principle, the add-on can handle much larger datasets without succumbing to the instability caused by rapid mode switching.
