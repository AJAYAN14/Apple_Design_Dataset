#!/usr/bin/env python3
"""
colors.py — 色彩采样、量化聚类与伪彩诊断染色图生成模块
"""

from collections import Counter
from pathlib import Path
import numpy as np
import cv2

COLOR_QUANT = 4         # 色值量化步长，抗锯齿 / 压缩噪声
COLOR_MATCH = 6         # 量化后色值匹配容差（±6 per channel）
BG_DIFF_THRESH = 5      # 最小通道差：低于此值视为"与背景同色"（支持白卡片 #FFFFFF 与浅灰底 #F5F6F8 的微反差）


def rgb_to_hex(rgb: tuple) -> str:
    """将 RGB 三元组转换为规范大写六位十六进制字符串 #RRGGBB。"""
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _most_frequent_color(pixels: np.ndarray) -> tuple:
    """量化聚类后取最高频色，再回算匹配像素的真实均值以提高精度。"""
    quantized = (pixels // COLOR_QUANT) * COLOR_QUANT
    counts = Counter(map(tuple, quantized.tolist()))
    top_q = np.array(counts.most_common(1)[0][0])

    mask = np.all(np.abs(pixels.astype(int) - top_q) <= COLOR_MATCH, axis=1)
    if mask.sum() == 0:
        return tuple(int(c) for c in top_q)
    avg = np.round(pixels[mask].mean(axis=0)).astype(int)
    return tuple(int(c) for c in avg)


def sample_background(img: np.ndarray) -> tuple:
    """从屏幕四周边缘窄条采样，提取主体背景色。

    取顶部 2% 横条 + 左右各 2% 竖条的像素集合做频率统计。
    """
    h, w = img.shape[:2]
    sw = max(2, int(w * 0.02))   # 竖条宽度
    sh = max(2, int(h * 0.02))   # 横条高度

    strips = [
        img[:sh, :],              # 顶部横条
        img[:, :sw],              # 左侧竖条
        img[:, w - sw:],          # 右侧竖条
    ]
    pixels = np.vstack([s.reshape(-1, 3) for s in strips])
    return _most_frequent_color(pixels)


def find_candidate_surface_color(img: np.ndarray, bg: tuple) -> dict:
    """在中央区域寻找与背景色差异 >= BG_DIFF_THRESH 的最高频非背景色。

    遍历量化色频表前 30 名，取第一个与 bg 有足够差异的色值。
    注意：此结果仅为候选值，可能来自大图、图表或插画，不必然是卡片表面。
    仅当下游验证矩形边界和足够面积后才应视为 card_surface。

    返回 dict:
      color       — (R, G, B) 元组
      color_hex   — "#RRGGBB"
      area_ratio  — 该色在中央区域占比 (0.0~1.0)
      confidence  — 置信度: "high" / "medium" / "low"
    """
    h, w = img.shape[:2]
    center = img[int(h * 0.15):int(h * 0.85),
                 int(w * 0.05):int(w * 0.95)]
    pixels = center.reshape(-1, 3)
    total_pixels = len(pixels)
    quantized = (pixels // COLOR_QUANT) * COLOR_QUANT
    counts = Counter(map(tuple, quantized.tolist()))
    bg_arr = np.array(bg)

    for color_q, freq in counts.most_common(30):
        if np.max(np.abs(np.array(color_q) - bg_arr)) >= BG_DIFF_THRESH:
            # 回算真实均值
            match_mask = np.all(
                np.abs(pixels.astype(int) - np.array(color_q)) <= COLOR_MATCH,
                axis=1,
            )
            matched_count = int(match_mask.sum())
            if matched_count > 0:
                avg = np.round(pixels[match_mask].mean(axis=0)).astype(int)
                color = tuple(int(c) for c in avg)
            else:
                color = tuple(int(c) for c in color_q)
                matched_count = freq

            area_ratio = round(matched_count / total_pixels, 4)
            diff = int(np.max(np.abs(np.array(color) - bg_arr)))
            if area_ratio > 0.15 and diff > 30:
                confidence = "high"
            elif area_ratio > 0.05 and diff > 15:
                confidence = "medium"
            else:
                confidence = "low"

            return {
                "color": color,
                "color_hex": rgb_to_hex(color),
                "area_ratio": area_ratio,
                "confidence": confidence,
            }

    # 所有高频色都接近背景 → 回退
    fallback = _most_frequent_color(pixels)
    return {
        "color": fallback,
        "color_hex": rgb_to_hex(fallback),
        "area_ratio": None,
        "confidence": "low",
    }


def generate_diagnostic_color_maps(img: np.ndarray, folder: Path, mode: str) -> dict:
    """根据智能驾驶与计算机视觉算法，生成辅助调试与多模态视觉审视的预处理染色图：
    1. {mode}_gradient_rainbow.png: 梯度法向 HSV 彩虹伪彩染色图
    2. {mode}_enhanced_clahe.png: CLAHE 自适应局部对比度增强图 (将 0.06 微光反差放大)
    """
    res = {}
    try:
        # 1. 梯度方向彩虹伪彩染色图
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        mag, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)

        # 映射到 HSV：色相 Hue 0~180 (角度/2), 饱和度 Saturation 255, 亮度 Value 增强梯度幅值
        h = (angle / 2.0).astype(np.uint8)
        v = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        s = np.full_like(h, 255)
        # 背景平坦无边缘区域压暗
        s[v < 18] = 0
        v[v < 18] = 15

        hsv = cv2.merge([h, s, v])
        rainbow_bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        rainbow_path = folder / f"{mode}_gradient_rainbow.png"
        cv2.imwrite(str(rainbow_path), rainbow_bgr)
        res["rainbow"] = str(rainbow_path)

        # 2. CLAHE 局部自适应对比度增强图 (强化 Alpha 0.06 微光卡片边界)
        lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced_lab = cv2.merge((cl, a, b))
        enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        clahe_path = folder / f"{mode}_enhanced_clahe.png"
        cv2.imwrite(str(clahe_path), enhanced_bgr)
        res["clahe"] = str(clahe_path)
    except Exception:
        pass
    return res
