# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
import pytest

def test_install_addon():
    """
    Tests that the add-on can be enabled and disabled.
    """
    addon_name = "pose_editor"

    # Enable the add-on
    bpy.ops.preferences.addon_enable(module=addon_name)
    assert addon_name in bpy.context.preferences.addons

    # Check that the dummy operator is registered
    assert hasattr(bpy.ops.pose_editor, "dummy")

    # Disable the add-on
    bpy.ops.preferences.addon_disable(module=addon_name)
    assert addon_name not in bpy.context.preferences.addons

    # Check that the dummy operator is unregistered
    with pytest.raises(AttributeError):
        bpy.ops.pose_editor.dummy()
