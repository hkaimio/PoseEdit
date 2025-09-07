# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
from src.pose_editor.blender.drivers import get_quality_driven_color_component

@pytest.mark.parametrize(
    "quality, original_color, expected_color",
    [
        (1.0, (1.0, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 1.0)), # Quality >= 1.0, original color
        (1.5, (0.0, 1.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0)), # Quality >= 1.0, original color
        (0.3, (1.0, 0.0, 0.0, 1.0), (0.5, 0.5, 0.5, 1.0)), # Quality = 0.3, grey
        (0.0, (1.0, 0.0, 0.0, 1.0), (0.5, 0.0, 0.0, 1.0)), # Quality < 0.3, dark red
        (0.2, (0.0, 1.0, 0.0, 1.0), (0.5, 0.0, 0.0, 1.0)), # Quality < 0.3, dark red
        (0.65, (1.0, 0.0, 0.0, 1.0), (0.75, 0.25, 0.25, 1.0)), # Interpolation: (0.5 + 1.0)/2, (0.5+0.0)/2, (0.5+0.0)/2
        (0.8, (0.0, 0.0, 1.0, 1.0), (0.14285714285714285, 0.14285714285714285, 0.8571428571428571, 1.0)), # Interpolation: (0.5 * (1-t)) + (original * t) where t = (0.8-0.3)/0.7 = 0.5/0.7 = 0.7142857142857143
    ]
)
def test_get_quality_driven_color_component(quality, original_color, expected_color):
    for i in range(4): # R, G, B, A channels
        result = get_quality_driven_color_component(quality, *original_color, i)
        assert result == pytest.approx(expected_color[i])
