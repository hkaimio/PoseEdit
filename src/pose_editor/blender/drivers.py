# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy


def get_quality_driven_color_component(
    quality: float, original_r: float, original_g: float, original_b: float, original_a: float, channel_index: int
) -> float:
    """
    Calculates a single color component based on the quality value and original color.

    Args:
        quality: The quality value (float).
        original_r: The original red component of the color.
        original_g: The original green component of the color.
        original_b: The original blue component of the color.
        original_a: The original alpha component of the color.
        channel_index: The index of the color channel (0=R, 1=G, 2=B, 3=A).

    Returns:
        The calculated color component value.
    """
    original_color = [original_r, original_g, original_b, original_a]
    dark_red = [0.5, 0.0, 0.0, 1.0]  # Dark red for quality < 0.3
    grey = [0.5, 0.5, 0.5, 1.0]  # Grey for quality = 0.3

    if quality >= 1.0:
        return original_color[channel_index]
    elif quality < 0.3:
        return dark_red[channel_index]
    else:  # 0.3 <= quality < 1.0, linear interpolation
        # Normalize quality to range [0, 1] for interpolation between grey and original
        # quality_norm = (quality - 0.3) / (1.0 - 0.3)
        # Simplified: quality_norm = (quality - 0.3) / 0.7
        t = (quality - 0.3) / 0.7

        # Interpolate between grey and original color
        interpolated_value = grey[channel_index] * (1 - t) + original_color[channel_index] * t
        return interpolated_value


def register_drivers() -> None:
    """Register all driver functions."""
    bpy.app.driver_namespace["get_quality_driven_color_component"] = get_quality_driven_color_component


def unregister_drivers() -> None:
    """Unregister all driver functions."""
    del bpy.app.driver_namespace["get_quality_driven_color_component"]