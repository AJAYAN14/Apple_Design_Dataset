#!/usr/bin/env python3
"""
component.py — 卡片内部组件与内边距自动探测模块（借鉴 UIED Component 分解算法）
"""

import numpy as np
import cv2


def measure_inner_components(img: np.ndarray, card_bounds: list, margin_info: dict, scale: float) -> dict:
    """卡片内部组件与内边距自动探测器（借鉴 UIED Component/Block 层次结构分解算法）。
    
    算法机制：
      1. 遍历卡片，截取卡片表面 ROI；
      2. 利用 HSV 饱和度差分与通道阈值，提取内部彩色图标容器或独立色块部件（Compo）；
      3. 自动计算内部部件的真实物理尺寸 (width, height)、距卡片左侧/上方的真实内边距 (padding_left, padding_top)；
      4. 提取部件拐角边缘，拟合内部小部件的标称圆角半径 (inner_item_radius_pt)。
    """
    empty_res = {
        "detected": False,
        "item_size_pt": None,
        "padding_left_pt": None,
        "padding_top_pt": None,
        "inner_radius_pt": None
    }
    if not card_bounds or margin_info.get("left_edge_px") is None:
        return empty_res

    left_x = int(margin_info["left_edge_px"])
    right_x = int(margin_info["right_edge_px"])
    if right_x <= left_x:
        return empty_res

    sizes = []
    pad_lefts = []
    pad_tops = []
    inner_radii = []

    for b in card_bounds:
        y0, y1 = b["y_start"], b["y_end"]
        if (y1 - y0) < 40 * scale:
            continue
        card_roi = img[y0:y1, left_x:right_x]
        
        # 提取高饱和度彩色图标或高对比度独立形状 (Compo)
        hsv = cv2.cvtColor(card_roi, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1]
        color_mask = (sat > 50).astype(np.uint8) * 255
        
        # 闭运算桥接图标内部矢量孔洞
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(round(6 * scale)), int(round(6 * scale))))
        closed = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            # 过滤过小噪声与过大容器 (目标尺寸通常在 24pt ~ 90pt 之间)
            min_dim = 24 * scale
            max_dim = 90 * scale
            if min_dim <= w <= max_dim and min_dim <= h <= max_dim:
                # 宽长比接近正方形 (0.8 ~ 1.25)
                ratio = w / float(h)
                if 0.8 <= ratio <= 1.25:
                    sizes.append((w / scale, h / scale))
                    pad_lefts.append(x / scale)
                    pad_tops.append(y / scale)
                    
                    # 尝试拟合该部件的小圆角
                    try:
                        icon_roi = card_roi[y : y + h, x : x + w]
                        g_icon = cv2.cvtColor(icon_roi, cv2.COLOR_RGB2GRAY)
                        ed_icon = cv2.Canny(g_icon, 20, 60)
                        corner_crop = ed_icon[:int(h * 0.4), :int(w * 0.4)]
                        c_pts = np.argwhere(corner_crop > 0)
                        if len(c_pts) >= 8:
                            c_ys = c_pts[:, 0]
                            c_xs = c_pts[:, 1]
                            A = np.column_stack([c_xs, c_ys, np.ones(len(c_xs))])
                            B = -(c_xs**2 + c_ys**2)
                            res_c, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
                            D, E, F = res_c
                            r_sq = D**2/4 + E**2/4 - F
                            if r_sq > 0:
                                r_px = np.sqrt(r_sq)
                                inner_radii.append(r_px / scale)
                    except Exception:
                        pass
                    break  # 每张卡片抓取首个主体部件

    if not sizes:
        return empty_res

    med_w = float(np.median([s[0] for s in sizes]))
    med_h = float(np.median([s[1] for s in sizes]))
    item_size = round((med_w + med_h) / 2.0, 1)
    pad_l = round(float(np.median(pad_lefts)), 1)
    pad_t = round(float(np.median(pad_tops)), 1)
    r_inner = round(float(np.median(inner_radii)), 1) if inner_radii else None

    return {
        "detected": True,
        "item_size_pt": item_size,
        "padding_left_pt": pad_l,
        "padding_top_pt": pad_t,
        "inner_radius_pt": r_inner,
        "detected_count": len(sizes)
    }
