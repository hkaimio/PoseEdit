# OpenSim Integration Package

This package provides a configuration-based system for exporting Blender armatures to OpenSim biomechanical models.

## Features

- **Declarative Configuration**: Define armature export parameters in Python configuration files
- **Flexible Joint Constraints**: Configure joint types (FREE, CUSTOM) and per-axis constraints
- **Validation**: Comprehensive validation of configurations to catch errors early
- **Example Configurations**: Pre-built configurations for common armature types

## Quick Start

### Using an Existing Configuration

```python
from pose_editor.opensim.configs import create_humanoid_config

# Create a humanoid configuration
config = create_humanoid_config()

# Validate the configuration
errors = config.validate()
if errors:
    print("Configuration errors:", errors)
else:
    print(f"Configuration valid: {config}")
    print(f"Total bones: {config.get_bone_count()}")
    print(f"Total DOF: {config.get_total_dof()}")
```

### Creating a Custom Configuration

```python
from pose_editor.opensim import (
    ArmatureExportConfig,
    BoneConfig,
    JointConstraints,
    JointType,
    AxisConstraint,
)

# Create configuration
config = ArmatureExportConfig()
config.model_name = "MyModel"

# Add root bone with FREE joint (6 DOF)
config.add_bone(BoneConfig(
    blender_name="root",
    opensim_name="pelvis",
    constraints=JointConstraints(joint_type=JointType.FREE),
    body_mass=10.0,
))

# Add child bone with hinge joint (1 DOF)
config.add_bone(BoneConfig(
    blender_name="leg.R",
    opensim_name="femur_r",
    constraints=JointConstraints(
        joint_type=JointType.CUSTOM,
        x_axis=AxisConstraint(locked=True),
        y_axis=AxisConstraint(locked=False, min_angle=-120, max_angle=30),
        z_axis=AxisConstraint(locked=True),
    ),
    body_mass=8.0,
))

# Validate
errors = config.validate()
```

## Configuration Classes

### `JointType`
Enum defining joint types:
- `FREE`: 6 DOF (3 translation + 3 rotation)
- `CUSTOM`: 0-3 DOF rotation only

### `AxisConstraint`
Configuration for a single rotation axis:
- `locked`: Whether axis is completely locked
- `min_angle`: Minimum angle in degrees
- `max_angle`: Maximum angle in degrees

### `JointConstraints`
Joint configuration with axis constraints:
- `joint_type`: FREE or CUSTOM
- `x_axis`, `y_axis`, `z_axis`: Constraints for each axis

### `BoneConfig`
Configuration for a single bone:
- `blender_name`: Name in Blender armature
- `opensim_name`: Name in OpenSim model
- `constraints`: Joint constraints
- `export_body`: Whether to export as OpenSim Body
- `body_mass`: Mass in kg
- `body_inertia`: Inertia tensor (6 elements)

### `ArmatureExportConfig`
Main configuration class:
- `model_name`: Name for exported model
- `bones`: Dictionary of bone configurations
- `marker_config`: Marker name overrides
- `marker_collection_name`: Blender collection containing markers

## Example Configurations

### Humanoid

The humanoid configuration includes:
- **Root**: Pelvis with 6 DOF (FREE joint)
- **Torso**: Spine, chest, neck, head with 3 DOF each
- **Upper Limbs**: Shoulders (3 DOF), elbows (1 DOF), wrists (2 DOF)
- **Lower Limbs**: Hips (3 DOF), knees (1 DOF), ankles (2 DOF)
- **Total**: 17 bones, 42 degrees of freedom

```python
from pose_editor.opensim.configs import create_humanoid_config

config = create_humanoid_config()
```

## Validation

All configuration classes include validation methods that check:
- Required fields are not empty
- Numeric values are in valid ranges
- Constraints are consistent
- No duplicate names

```python
config = create_humanoid_config()
errors = config.validate()

if not errors:
    print("Configuration is valid!")
else:
    for error in errors:
        print(f"ERROR: {error}")
```

## Testing

Comprehensive unit tests are provided in `tests/opensim/`:
- `test_config.py`: Tests for configuration classes
- `test_configs.py`: Tests for example configurations

Run tests with:
```bash
pytest tests/opensim/ -v
```

## Current Status

✅ **Phase 1: Configuration System** - Complete
✅ **Phase 2: Export Integration** - Complete
✅ **Phase 3: Solution Import** - Complete

### Features Available

**Export (Blender → OpenSim):**
- Configuration-based armature export
- Support for Free, Custom, and Weld joints
- Automatic joint type selection based on DOF
- Coordinate range validation and extension
- Marker export with custom naming
- Proper coordinate system conversion (Z-up → Y-up)

**Import (OpenSim → Blender):**
- Parse .mot and .sto solution files
- Map OpenSim coordinates back to Blender bones
- Apply animation as keyframes
- Support for all joint types (Free, Custom, Weld)
- Configurable FPS and frame range
- Robust error handling and reporting

### Future Enhancements

- GUI integration for export/import in Blender panels
- Backward compatibility wrapper for legacy export function
- Batch export/import for multiple armatures
- Animation export (coordinate values over time)
- Performance optimization for large solutions
- Keyframe interpolation options
