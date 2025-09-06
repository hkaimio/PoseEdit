# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
import pytest
from unittest.mock import Mock, patch
from pose_editor.blender.operators import PE_OT_CreateProject

@patch('pose_editor.blender.scene_builder.create_project_structure')
def test_create_project_operator_mocked(mock_create_project_structure):
    """
    Tests that the PE_OT_CreateProject operator calls scene_builder.create_project_structure.
    """
    # Create a dummy context
    context = Mock()
    
    # Call the execute method directly
    PE_OT_CreateProject.execute(None, context) # self is None as it's a static call for testing
    
    # Assert that create_project_structure was called once
    mock_create_project_structure.assert_called_once()
