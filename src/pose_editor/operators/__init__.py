"""Operators module for pose editor."""

from . import apply_rigging


def register():
    """Register all operators."""
    apply_rigging.register()


def unregister():
    """Unregister all operators."""
    apply_rigging.unregister()