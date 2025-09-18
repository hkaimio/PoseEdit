# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import unittest
from unittest.mock import MagicMock, patch

# We have to import the module in a way that allows us to reload it
from pose_editor.core import frame_handler as frame_handler_module


class TestFrameHandler(unittest.TestCase):
    def setUp(self):
        # Ensure we have a fresh instance for each test
        # This is important because it's a singleton
        frame_handler_module._instance = None
        self.handler = frame_handler_module.FrameHandler()

    def test_singleton_instance(self):
        """Test that the FrameHandler is a singleton."""
        handler2 = frame_handler_module.FrameHandler()
        self.assertIs(self.handler, handler2)

    def test_add_callback(self):
        """Test that a callback can be added."""
        mock_callback = MagicMock()
        self.handler.add_callback(mock_callback)
        self.assertIn(mock_callback, self.handler._callbacks)

    def test_add_duplicate_callback(self):
        """Test that adding a duplicate callback does not add it twice."""
        mock_callback = MagicMock()
        self.handler.add_callback(mock_callback)
        self.handler.add_callback(mock_callback)
        self.assertEqual(self.handler._callbacks.count(mock_callback), 1)

    def test_remove_callback(self):
        """Test that a callback can be removed."""
        mock_callback = MagicMock()
        self.handler.add_callback(mock_callback)
        self.handler.remove_callback(mock_callback)
        self.assertNotIn(mock_callback, self.handler._callbacks)

    @patch("pose_editor.core.frame_handler.bpy")
    def test_handler_registration(self, mock_bpy):
        """Test the main handler registration and unregistration with Blender."""
        self.handler.register_handler()
        mock_bpy.app.handlers.frame_change_post.append.assert_called_once_with(
            self.handler._on_frame_change
        )
        self.assertTrue(self.handler._is_registered)

        self.handler.unregister_handler()
        mock_bpy.app.handlers.frame_change_post.remove.assert_called_once_with(
            self.handler._on_frame_change
        )
        self.assertFalse(self.handler._is_registered)

    def test_on_frame_change_execution(self):
        """Test that registered callbacks are executed on frame change."""
        mock_callback_1 = MagicMock()
        mock_callback_2 = MagicMock()
        mock_scene = MagicMock()
        mock_depsgraph = MagicMock()

        self.handler.add_callback(mock_callback_1)
        self.handler.add_callback(mock_callback_2)

        self.handler._on_frame_change(mock_scene, mock_depsgraph)

        mock_callback_1.assert_called_once_with(mock_scene, mock_depsgraph)
        mock_callback_2.assert_called_once_with(mock_scene, mock_depsgraph)


if __name__ == "__main__":
    unittest.main()
