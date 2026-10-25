#!/usr/bin/env python3
"""
corner.py — 双轨圆角识别引擎（多角巡检抗遮挡纯度自适应拟合与超椭圆曲率解算）
"""

import numpy as np
import cv2
from scipy.optimize import least_squares


def estimate_card_corner_radius(img: np.ndarray, bg: tuple, card_bounds: list,
                                margin_info: dict, scale: float) -> dict:
    """双轨圆角识别引擎（引入多角巡检抗遮挡纯度自适应拟合 Multi-Corner Purity Selection）。
    
    算法核心：
      1. 多角巡检：同时评估卡片的 4 个拐角（TL 左上、TR 右上、BR 右下、BL 左下）；
      2. 纯度评分（借鉴 UIED 噪声抑制）：计算各拐角内部区域的色彩方差 σ²。若左上角存在彩色图标或文字侵入（σ² 高），自动切换至纯净无遮挡的右上角或右下角（σ² ≈ 0）；
      3. 规范化亚像素拟合：将最优角统一变换至规范化象限，利用 Devernay 二次抛物线插值与最小二乘拟合标称圆角 R；
      4. 智驾超椭圆曲率解算：结合 Soft L1 鲁棒核函数，求解超椭圆方程 |x/a|^n + |y/b|^n = 1 及形状指数 n。
    """
    empty_res = {
        "traditional_circle": {"radius_pt": None, "compensated_radius_pt": None},
        "superellipse": {"shape_exponent_n": None, "radius_a_pt": None, "radius_b_pt": None,
                         "curve_style": None, "exact_formula": None, "figma_corner_smoothing": None},
        "is_subtle_tint": False,
        "confidence": "none",
        "corner_selected": None,
        "corner_variances": {}
    }
    if not card_bounds or margin_info.get("left_edge_px") is None:
        return empty_res

    left_x = int(margin_info["left_edge_px"])
    right_x = int(margin_info["right_edge_px"])
    
    # 优先选取高度适中 (50pt ~ 120pt) 的独立干净卡片作为圆角测量目标
    target_card = None
    for b in card_bounds:
        h_pt = (b["y_end"] - b["y_start"]) / scale
        if 45.0 <= h_pt <= 150.0:
            target_card = b
            break
    if not target_card and card_bounds:
        target_card = card_bounds[0]
    if not target_card:
        return empty_res

    y0, y1 = target_card["y_start"], target_card["y_end"]
    card_h = y1 - y0
    roi_size = int(round(min(card_h * 0.45, 64 * scale)))
    if roi_size < 10:
        return empty_res

    # 对比度分析：检查卡片中心与背景的颜色差异
    center_y = (y0 + y1) // 2
    center_x = (left_x + right_x) // 2
    card_center_color = img[center_y, center_x]
    color_diff = float(np.max(np.abs(card_center_color.astype(np.int16) - np.array(bg, dtype=np.int16))))
    is_subtle_tint = color_diff < 35  # 低对比度微光表面 (灰阶差 < 35)

    thresh_low = max(3, int(color_diff * 0.15))
    thresh_high = max(8, int(color_diff * 0.5))

    # ── 1. 多角采样构建 ────────────────────────────────────
    img_h, img_w = img.shape[:2]
    candidate_rois = {
        "TL": (img[max(0, y0 - 5) : min(img_h, y0 + roi_size), max(0, left_x - 5) : min(img_w, left_x + roi_size)], "TL"),
        "TR": (img[max(0, y0 - 5) : min(img_h, y0 + roi_size), max(0, right_x - roi_size) : min(img_w, right_x + 5)], "TR"),
        "BR": (img[max(0, y1 - roi_size) : min(img_h, y1 + 5), max(0, right_x - roi_size) : min(img_w, right_x + 5)], "BR"),
        "BL": (img[max(0, y1 - roi_size) : min(img_h, y1 + 5), max(0, left_x - 5) : min(img_w, left_x + roi_size)], "BL")
    }

    # ── 2. 纯度评分与无遮挡角选择 ────────────────────────────
    corner_scores = {}
    valid_corners = {}
    for c_name, (roi_block, _) in candidate_rois.items():
        if roi_block.shape[0] < 20 or roi_block.shape[1] < 20:
            continue
        g = cv2.cvtColor(roi_block, cv2.COLOR_RGB2GRAY)
        h_r, w_r = g.shape
        inner_core = g[int(h_r * 0.35) : int(h_r * 0.65), int(w_r * 0.35) : int(w_r * 0.65)]
        var = float(np.var(inner_core)) if inner_core.size > 0 else 9999.0
        
        bl = cv2.GaussianBlur(g, (3, 3), 0)
        ed = cv2.Canny(bl, thresh_low, thresh_high)
        ed_pts = np.sum(ed > 0)
        
        corner_scores[c_name] = round(var, 2)
        if ed_pts >= 12:
            valid_corners[c_name] = (var, roi_block)

    if not valid_corners:
        empty_res["is_subtle_tint"] = is_subtle_tint
        empty_res["corner_variances"] = corner_scores
        return empty_res

    # 选取方差最小（最纯净、无内部图标文字遮挡）的候选角
    best_corner = min(valid_corners.keys(), key=lambda k: valid_corners[k][0])
    best_roi = valid_corners[best_corner][1]

    # ── 3. 亚像素边缘提取与坐标统一映射 ───────────────────────
    gray = cv2.cvtColor(best_roi, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, thresh_low, thresh_high)
    pts = np.argwhere(edges > 0)

    if len(pts) < 12:
        empty_res["is_subtle_tint"] = is_subtle_tint
        empty_res["corner_selected"] = best_corner
        empty_res["corner_variances"] = corner_scores
        return empty_res

    gx = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=3)
    modG = np.sqrt(gx**2 + gy**2)

    sub_xs, sub_ys = [], []
    h_roi, w_roi = blurred.shape
    for py, px in pts:
        if 1 <= px < w_roi - 1 and 1 <= py < h_roi - 1:
            g_abs_x, g_abs_y = abs(gx[py, px]), abs(gy[py, px])
            if g_abs_x >= g_abs_y:
                a = modG[py, px - 1]
                b = modG[py, px]
                c = modG[py, px + 1]
                denom = a - 2.0 * b + c
                offset = 0.5 * (a - c) / denom if abs(denom) > 1e-5 else 0.0
                offset = np.clip(offset, -0.6, 0.6)
                sub_xs.append(px + offset)
                sub_ys.append(py)
            else:
                a = modG[py - 1, px]
                b = modG[py, px]
                c = modG[py + 1, px]
                denom = a - 2.0 * b + c
                offset = 0.5 * (a - c) / denom if abs(denom) > 1e-5 else 0.0
                offset = np.clip(offset, -0.6, 0.6)
                sub_xs.append(px)
                sub_ys.append(py + offset)
        else:
            sub_xs.append(px)
            sub_ys.append(py)

    sub_xs = np.array(sub_xs, dtype=float)
    sub_ys = np.array(sub_ys, dtype=float)

    # 规范化坐标系变换：统一映射为以卡片拐角顶点为 (0, 0) 的第一象限坐标
    pad_box = 5.0
    if best_corner == "TR":
        c_xs = (w_roi - pad_box) - sub_xs
        c_ys = sub_ys - pad_box
    elif best_corner == "BR":
        c_xs = (w_roi - pad_box) - sub_xs
        c_ys = (h_roi - pad_box) - sub_ys
    elif best_corner == "BL":
        c_xs = sub_xs - pad_box
        c_ys = (h_roi - pad_box) - sub_ys
    else:  # TL
        c_xs = sub_xs - pad_box
        c_ys = sub_ys - pad_box

    corner_mask = (c_xs >= 0) & (c_ys >= 0) & (c_xs < roi_size * 0.95) & (c_ys < roi_size * 0.95)
    c_xs = c_xs[corner_mask]
    c_ys = c_ys[corner_mask]

    if len(c_xs) < 10:
        empty_res["is_subtle_tint"] = is_subtle_tint
        empty_res["corner_selected"] = best_corner
        empty_res["corner_variances"] = corner_scores
        return empty_res

    # ── 4. 传统圆拟合 (Circle Fitting, G1 标称半径) ─────────────
    trad_pt = None
    comp_pt = None
    try:
        A = np.column_stack([c_xs, c_ys, np.ones(len(c_xs))])
        B = -(c_xs**2 + c_ys**2)
        res_c, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
        D, E, F = res_c
        r_sq = D**2/4 + E**2/4 - F
        if r_sq > 0:
            fit_r_px = np.sqrt(r_sq)
            trad_pt = round(fit_r_px / scale, 1)
            comp_pt = round(trad_pt * 1.18, 1) if is_subtle_tint else trad_pt
    except Exception:
        pass

    # ── 5. 超椭圆连续曲率拟合 (Superellipse Fitting, G2/G3 方程与指数) ──
    superellipse_data = {
        "shape_exponent_n": None,
        "radius_a_pt": None,
        "radius_b_pt": None,
        "curve_style": None,
        "exact_formula": None,
        "figma_corner_smoothing": None
    }
    if trad_pt is not None:
        try:
            init_r = trad_pt * scale
            def loss_superellipse(params):
                cx, cy, a, b, n = params
                dx = np.abs((cx - c_xs) / a)
                dy = np.abs((cy - c_ys) / b)
                return (dx**n + dy**n) - 1.0

            p0 = [init_r, init_r, init_r, init_r, 2.0]
            bounds = ([init_r*0.5, init_r*0.5, init_r*0.5, init_r*0.5, 1.8],
                      [init_r*1.8, init_r*1.8, init_r*1.8, init_r*1.8, 6.0])

            res_s = least_squares(loss_superellipse, p0, bounds=bounds, loss='soft_l1', f_scale=0.1)
            _, _, a, b, n = res_s.x
            a_pt = round(a / scale, 1)
            b_pt = round(b / scale, 1)
            n_val = round(float(n), 2)

            if abs(n_val - 2.0) <= 0.25:
                style = "circular_standard"
                smoothing = 0.0
            elif 2.25 < n_val <= 3.3:
                style = "superellipse_hyperos"
                smoothing = 0.4
            else:
                style = "continuous_apple_squircle"
                smoothing = 0.6

            superellipse_data = {
                "shape_exponent_n": n_val,
                "radius_a_pt": a_pt,
                "radius_b_pt": b_pt,
                "curve_style": style,
                "exact_formula": f"|x / {a_pt}|^{n_val} + |y / {b_pt}|^{n_val} = 1",
                "figma_corner_smoothing": smoothing
            }
        except Exception:
            pass

    return {
        "traditional_circle": {
            "radius_pt": trad_pt,
            "compensated_radius_pt": comp_pt if is_subtle_tint else None
        },
        "superellipse": superellipse_data,
        "is_subtle_tint": is_subtle_tint,
        "confidence": "high" if (trad_pt and superellipse_data["shape_exponent_n"]) else "medium",
        "corner_selected": best_corner,
        "corner_variances": corner_scores
    }
