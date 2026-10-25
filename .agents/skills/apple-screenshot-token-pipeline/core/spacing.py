#!/usr/bin/env python3
"""
spacing.py — 水平外边距、内容掩码与卡片垂直间距检测模块
"""

from collections import Counter
import numpy as np
import cv2

MIN_GAP_PX = 6          # 忽略 < 2pt(@3x) 的微缝（噪声 / 分割线）


def _build_content_mask(img: np.ndarray, bg: tuple, scale: float, bg_diff_thresh: int = 5) -> tuple:
    """生成二值内容掩码（1 = 非背景像素）。

    步骤:
      1. 逐像素取各通道与 bg 的最大绝对差 → diff 矩阵
      2. diff > 阈值 → 原始掩码
      3. 水平形态学闭运算（宽核 ~20pt × 1pt）：
         - 横向合并卡片内散落的文字/图标 → 得到整块卡片区域
         - 竖向保守，不会桥接卡片间的垂直缝隙
      核大小随 scale 动态调整，确保跨设备一致的 pt 级行为。

    返回: (mask, kernel_params)
      mask          — np.ndarray, 二值掩码
      kernel_params — dict, {"kernel_w_px": int, "kernel_h_px": int}
    """
    diff = np.max(
        np.abs(img.astype(np.int16) - np.array(bg, dtype=np.int16)),
        axis=2,
    )
    raw = (diff > bg_diff_thresh).astype(np.uint8)

    # 目标 ~20pt 宽、~1pt 高，按 scale 换算为 px 并确保奇数
    kernel_w = max(3, int(round(20 * scale))) | 1
    kernel_h = max(1, int(round(1 * scale))) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, kernel_h))
    closed = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kernel)

    kernel_params = {"kernel_w_px": kernel_w, "kernel_h_px": kernel_h}
    return closed, kernel_params


def measure_horizontal_margin(mask: np.ndarray, scale: float) -> dict:
    """逐行扫描取最左/最右内容像素，众数即卡片边缘 → 屏幕外边距。

    只分析垂直中部 70%（跳过状态栏、导航栏、TabBar 区域）。
    以 scale px (1 pt) 为桶做众数，消除亚像素抖动。

    返回:
      {"margin_pt": float, "left_edge_px": int, "right_edge_px": int}
    """
    h, w = mask.shape
    y0, y1 = int(h * 0.15), int(h * 0.85)

    lefts, rights = [], []
    for r in range(y0, y1):
        cols = np.nonzero(mask[r])[0]
        if len(cols) < w * 0.15:
            continue  # 稀疏行 = 卡片间隙，跳过
        lefts.append(int(cols[0]))
        rights.append(int(w - 1 - cols[-1]))

    if not lefts:
        return {
            "margin_pt": None, "left_edge_px": None,
            "right_edge_px": None,
            "failure_reason": "no_content_rows_detected",
        }

    def _mode_binned(vals: list) -> int:
        """以 scale px 为桶取众数。"""
        binned = [int(round((v / scale))) * scale for v in vals]
        return Counter(binned).most_common(1)[0][0]

    left_px = _mode_binned(lefts)
    right_px = _mode_binned(rights)
    avg_px = (left_px + right_px) / 2.0

    return {
        "margin_pt": round(avg_px / scale, 1),
        "left_edge_px": left_px,
        "right_edge_px": w - 1 - right_px,   # 转为右侧边缘 x 坐标
    }


def measure_card_vertical_gap(mask: np.ndarray, scale: float) -> dict:
    """利用行投影检测卡片间垂直缝隙，同时输出卡片与间隙的 Y 坐标。

    返回:
      {
        "gap_pt": float,              # 最常见间距 (pt)
        "section_gap_pt": float,      # 宏观 Section 间距 (pt)
        "card_bounds_px": [...],      # 每个卡片 {"y_start": int, "y_end": int}
        "gap_ranges_px": [...]        # 每个间隙 {"y_start": int, "y_end": int, "height_px": int}
      }
    """
    h, w = mask.shape
    row_sum = mask.sum(axis=1)
    is_gap = row_sum < w * 0.03

    y0, y1 = int(h * 0.12), int(h * 0.88)

    # ── 状态机：交替收集 content 段和 gap 段 ────────────
    segments = []       # (type, start, end)  type = "card" | "gap"
    current_type = "gap" if is_gap[y0] else "card"
    seg_start = y0

    for r in range(y0 + 1, y1):
        row_type = "gap" if is_gap[r] else "card"
        if row_type != current_type:
            segments.append((current_type, seg_start, r))
            current_type = row_type
            seg_start = r
    segments.append((current_type, seg_start, y1))

    # ── 过滤与微缝桥接 (合并卡片内部发丝线，解耦宏观 Section 留白) ───────
    raw_card_bounds = []
    raw_gap_ranges = []
    gap_heights = []

    for seg_type, s, e in segments:
        height = e - s
        if seg_type == "card" and height >= MIN_GAP_PX:
            raw_card_bounds.append({"y_start": int(s), "y_end": int(e)})
        elif seg_type == "gap" and height >= MIN_GAP_PX:
            raw_gap_ranges.append({
                "y_start": int(s),
                "y_end": int(e),
                "height_px": int(height),
            })
            gap_heights.append(height)

    # 桥接卡片内部 <= 3.5pt 的微小发丝线缝隙，还原真实的卡片容器整体
    bridged_cards = []
    if raw_card_bounds:
        max_bridge_px = int(round(3.5 * scale))
        bridged_cards = [raw_card_bounds[0].copy()]
        for cur in raw_card_bounds[1:]:
            if cur["y_start"] - bridged_cards[-1]["y_end"] <= max_bridge_px:
                bridged_cards[-1]["y_end"] = cur["y_end"]
            else:
                bridged_cards.append(cur.copy())

    if not gap_heights:
        return {
            "gap_pt": None,
            "section_gap_pt": None,
            "card_bounds_px": bridged_cards or raw_card_bounds,
            "raw_card_bounds_px": raw_card_bounds,
            "gap_ranges_px": [],
            "failure_reason": "no_gaps_detected",
        }

    binned = [int(round(g / scale)) * scale for g in gap_heights]
    mode_px = Counter(binned).most_common(1)[0][0]

    # 计算跨容器的大留白 (Section Gap)
    section_gaps = []
    for i in range(len(bridged_cards) - 1):
        sg = (bridged_cards[i + 1]["y_start"] - bridged_cards[i]["y_end"]) / scale
        if sg >= 16.0:  # 大于 16pt 视为 Section 间距
            section_gaps.append(sg)
    section_gap_pt = round(float(np.median(section_gaps)), 1) if section_gaps else round(mode_px / scale, 1)

    return {
        "gap_pt": round(mode_px / scale, 1),
        "section_gap_pt": section_gap_pt,
        "card_bounds_px": bridged_cards or raw_card_bounds,
        "raw_card_bounds_px": raw_card_bounds,
        "gap_ranges_px": raw_gap_ranges,
    }
