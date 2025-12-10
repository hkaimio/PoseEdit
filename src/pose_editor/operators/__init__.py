"""Operators module for pose editor."""

from . import apply_rigging
from . import marker_enable_operators


def register():
    """Register all operators."""
    apply_rigging.register()
    marker_enable_operators.register()


def unregister():
    """Unregister all operators."""
    marker_enable_operators.unregister()
    apply_rigging.unregister()