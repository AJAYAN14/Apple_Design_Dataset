#!/usr/bin/env python3
"""
device.py — 设备分辨率数据库与倍率自适应识别模块
"""

# 设备分辨率数据库
# 键: (宽px, 高px)  值: (机型名, 缩放倍率, 逻辑宽pt, 逻辑高pt)
DEVICE_DB = {
    # @2x 设备
    (640,  1136): ("iPhone SE 1st",           2.0, 320, 568),
    (750,  1334): ("iPhone 6/7/8/SE2/SE3",    2.0, 375, 667),
    (828,  1792): ("iPhone XR/11",            2.0, 414, 896),
    # @3x 设备
    (1242, 2208): ("iPhone 6+/7+/8+",         3.0, 414, 736),
    (1125, 2436): ("iPhone X/XS/11 Pro",      3.0, 375, 812),
    (1242, 2688): ("iPhone XS Max/11 Pro Max", 3.0, 414, 896),
    (1080, 2340): ("iPhone 12/13 mini",       3.0, 360, 780),
    (1170, 2532): ("iPhone 12/13/14",         3.0, 390, 844),
    (1284, 2778): ("iPhone 12/13 Pro Max/14+", 3.0, 428, 926),
    (1179, 2556): ("iPhone 14/15/16 Pro",     3.0, 393, 852),
    (1290, 2796): ("iPhone 14/15 Pro Max/16+", 3.0, 430, 932),
    (1320, 2868): ("iPhone 16 Pro Max",       3.0, 440, 956),
    # Android / 小米设备
    (1080, 2400): ("Xiaomi 14 Pro (FHD+)",    2.625, 411, 914),
    (1440, 3200): ("Xiaomi 14 Pro (2K)",      3.5,   411, 914),
}


def detect_device(w: int, h: int, override_scale: float = None) -> dict:
    """从截图像素尺寸自动匹配设备信息。

    返回 dict:
      model        — 机型名（或 "Unknown"）
      scale        — 缩放倍率 (浮点数或整数，如 2.0 / 3.0 / 2.625)
      image_size_px — {"w": ..., "h": ...}
      logical_size_pt — {"w": ..., "h": ...}
    """
    key = (w, h)
    if key in DEVICE_DB:
        model, scale, pt_w, pt_h = DEVICE_DB[key]
        scale_source = "device_db"
    else:
        model = f"Unknown ({w}x{h})"
        scale = None
        pt_w = None
        pt_h = None
        scale_source = "unknown"

    # CLI --scale 覆盖
    if override_scale is not None:
        scale = override_scale
        pt_w = round(w / scale)
        pt_h = round(h / scale)
        scale_source = "user_override"

    return {
        "model": model,
        "scale": scale,
        "scale_source": scale_source,
        "image_size_px": {"w": w, "h": h},
        "logical_size_pt": {"w": pt_w, "h": pt_h} if pt_w is not None else None,
    }
