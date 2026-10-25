#!/usr/bin/env python3
"""
separator.py — 列表分隔线检测与连续性防假阳性校验模块（借鉴 UIED）
"""

import numpy as np
import cv2


def measure_card_separator_inset(img: np.ndarray, card_bounds: list, margin_info: dict, scale: float, gap_pt: float = None) -> dict:
    """通用列表分隔线左缩进自动探测器（借鉴 UIED 防假阳性连续性检测与拓扑解耦）。
    
    算法机制：
      1. 拓扑解耦：若卡片呈现离散卡片结构（卡片间距 >= 6.0pt 且卡片高度大多 < 120pt），单张卡片本身即为离散容器，抑制文本行笔画误判；
      2. 连续性校验（借鉴 UIED check_continuous_line）：要求横向线条必须具备真正的单段空间连贯性（最大连续单段 >= 卡片宽度 45%），排除散列汉字笔画累加；
      3. 密集行抑制：文字区域往往在垂直方向连续数十行产生横向梯度，若出现紧邻密集响应则判定为字形文本并予以滤除。
    """
    if not card_bounds or margin_info.get("left_edge_px") is None:
        return {"inset_left_pt": None, "confidence": "none", "detected_lines": 0}

    left_x = int(margin_info["left_edge_px"])
    right_x = int(margin_info["right_edge_px"])
    card_w = right_x - left_x
    if card_w <= 0:
        return {"inset_left_pt": None, "confidence": "none", "detected_lines": 0}

    # 拓扑先验：若为离散卡片列表（且卡片高度适中），单卡内部通常无行间分割线
    card_heights_pt = [(b["y_end"] - b["y_start"]) / scale for b in card_bounds]
    median_h_pt = float(np.median(card_heights_pt)) if card_heights_pt else 0
    is_discrete_cards = (gap_pt is not None and gap_pt >= 6.0) and (median_h_pt <= 120.0)

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    insets = []

    for b in card_bounds:
        y0, y1 = b["y_start"], b["y_end"]
        # 仅在具备足够高度的分组容器或多行列表内部搜索分割线
        if (y1 - y0) < 50 * scale:
            continue
        pad_y = int(round(18 * scale))
        if y1 - y0 <= 2 * pad_y:
            continue

        roi = gray[y0 + pad_y : y1 - pad_y, left_x : right_x]
        sobely = np.abs(cv2.Sobel(roi, cv2.CV_64F, 0, 1, ksize=3))
        
        valid_lines_in_card = []
        for row_idx in range(roi.shape[0]):
            line = sobely[row_idx, :]
            # 真正分割线对比度较高且连续
            active = (line > 12.0).astype(np.uint8)
            # 统计最大连续 1 的线段长度（借鉴 UIED continuous length 算法）
            diffs = np.diff(np.concatenate(([0], active, [0])))
            starts = np.where(diffs == 1)[0]
            ends = np.where(diffs == -1)[0]
            lengths = ends - starts
            max_continuous_len = int(np.max(lengths)) if len(lengths) > 0 else 0

            # 连续线段必须达到卡片宽度的 45% 以上，且起始位置靠左
            if max_continuous_len >= card_w * 0.45:
                best_seg_idx = int(np.argmax(lengths))
                start_x = starts[best_seg_idx]
                valid_lines_in_card.append((row_idx, start_x))

        # 密集行过滤：若卡片内检测到 > 6 条或上下紧邻密集的线，属于文字排版噪声，强制剔除
        if len(valid_lines_in_card) > 0:
            if len(valid_lines_in_card) >= 6 or is_discrete_cards:
                # 密集文字噪声或独立卡片，抑制假阳性
                continue
            for _, start_x in valid_lines_in_card:
                if start_x > 4 * scale:
                    insets.append(start_x)
                elif start_x <= 4 * scale:
                    insets.append(0.0)

    if not insets:
        return {"inset_left_pt": None, "confidence": "none", "detected_lines": 0}

    median_px = float(np.median(insets))
    inset_pt = round(median_px / scale, 1)
    return {
        "inset_left_pt": inset_pt,
        "confidence": "high" if len(insets) >= 2 else "medium",
        "detected_lines": len(insets)
    }
