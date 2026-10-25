#!/usr/bin/env python3
"""
core — Apple Screenshot Token Pipeline 核心测量与算法引擎包
"""

from .device import detect_device, DEVICE_DB
from .colors import (
    sample_background,
    find_candidate_surface_color,
    generate_diagnostic_color_maps,
    rgb_to_hex,
    COLOR_QUANT,
    COLOR_MATCH,
    BG_DIFF_THRESH,
)
from .spacing import (
    _build_content_mask,
    measure_horizontal_margin,
    measure_card_vertical_gap,
    MIN_GAP_PX,
)
from .separator import measure_card_separator_inset
from .corner import estimate_card_corner_radius
from .component import measure_inner_components

__all__ = [
    "detect_device",
    "DEVICE_DB",
    "sample_background",
    "find_candidate_surface_color",
    "generate_diagnostic_color_maps",
    "rgb_to_hex",
    "COLOR_QUANT",
    "COLOR_MATCH",
    "BG_DIFF_THRESH",
    "_build_content_mask",
    "measure_horizontal_margin",
    "measure_card_vertical_gap",
    "MIN_GAP_PX",
    "measure_card_separator_inset",
    "estimate_card_corner_radius",
    "measure_inner_components",
]
