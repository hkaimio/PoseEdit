# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the global frame change handler."""

from typing import Callable, Optional

import bpy
from bpy.app.handlers import persistent



class FrameHandler:
    """A singleton class to manage callbacks for the frame_change_post event."""

    _instance: Optional["FrameHandler"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FrameHandler, cls).__new__(cls)
            cls._instance._callbacks = []
            cls._instance._is_registered = False
        return cls._instance

    def register_handler(self):
        """Registers the frame change handler with Blender if not already registered."""
        if not self._is_registered:
            try:
                bpy.app.handlers.frame_change_post.append(self._on_frame_change)
                self._is_registered = True
                print("Frame change handler registered.")
            except Exception as e:
                print(f"Error registering frame change handler: {e}")

    def unregister_handler(self):
        """Unregisters the frame change handler from Blender."""
        if self._is_registered:
            try:
                bpy.app.handlers.frame_change_post.remove(self._on_frame_change)
                self._is_registered = False
                print("Frame change handler unregistered.")
            except ValueError:
                # Handler might have already been removed, which is fine.
                pass
            except Exception as e:
                print(f"Error unregistering frame change handler: {e}")

    def add_callback(self, callback: Callable):
        """Adds a callback function to be executed on frame change."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        """Removes a callback function."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    @staticmethod
    @persistent
    def _on_frame_change(scene, depsgraph):
        """The actual function that gets called by Blender on frame change."""
        if FrameHandler._instance is None:
            return
        
        for callback in FrameHandler._instance._callbacks:
            try:
                callback(scene, depsgraph)
            except Exception as e:
                print(f"Error in frame change callback {callback.__name__}: {e}")


# Global instance of the handler
frame_handler = FrameHandler()
