# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
import pytest
from pose_editor import register, unregister # Import register/unregister functions

def test_install_addon():
    """
    Tests that the extension can be registered and unregistered.
    """
    # Register the extension
    register()

    # Check that the dummy operator is registered
    assert hasattr(bpy.ops.pose_editor, "dummy")

    # Unregister the extension
    unregister()

    # Check that the dummy operator is unregistered
    with pytest.raises(AttributeError):
        bpy.ops.pose_editor.dummy()
