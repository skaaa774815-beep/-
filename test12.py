# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 01:47:35 2026

@author: skaaa
"""

import streamlit as st
import cv2
import numpy as np
from PIL import Image

def run_debug_analyzer_v2():
    st.title("🛠️ 画像解析デバッガー（誤検出対策版）")
    st.write("右下の羽ペンなどのノイズを除去し、カードだけを抽出するように調整しました。")

    uploaded_file = st.file_uploader("検証する画像をアップロード", type=["png", "jpg", "jpeg", "webp"])

    if uploaded_file is not None:
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        h_img, w_img, _ = img.shape
        img_area = h_img * w_img

        # --- STEP 1: 画像処理 ---
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        kernel = np.ones((3,3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=1)

        # --- STEP 2: 輪郭抽出とフィルタリング ---
        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        raw_rects = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = w / float(h) if h > 0 else 0
            area = w * h
            
            # 修正ポイント1: 縦横比を少し厳密にする (カードは0.6前後)
            # 修正ポイント2: 画面の下すぎる位置（右下のペン付近）を除外する条件を追加
            # y + h > h_img * 0.95 などの条件で、一番下の端っこをカット
            is_in_deck_area = (y + h < h_img * 0.92) 
            
            if 0.5 < aspect_ratio < 0.75 and (img_area * 0.005 < area < img_area * 0.15) and is_in_deck_area:
                raw_rects.append((x, y, w, h))

        # --- STEP 3: 重複排除 ---
        filtered_rects_img = img_rgb.copy()
        unique_rects = []
        raw_rects.sort(key=lambda r: r[2]*r[3], reverse=True)

        for r in raw_rects:
            x, y, w, h = r
            is_duplicate = False
            for ux, uy, uw, uh in unique_rects:
                # 判定: 枠が重なっているか（IoU的な簡易判定）
                if abs(x - ux) < w/2 and abs(y - uy) < h/2:
                    is_duplicate = True; break
            if not is_duplicate:
                unique_rects.append(r)
                # 最終的な枠を赤色で描画
                cv2.rectangle(filtered_rects_img, (x, y), (x+w, y+h), (255, 0, 0), 3)

        # 結果表示
        st.subheader("最終的な検出結果（赤枠）")
        st.image(filtered_rects_img, caption="右下の羽ペンの枠が消えているか確認してください")
        
        st.write(f"検出されたカード数: {len(unique_rects)} 枚")

if __name__ == "__main__":
    run_debug_analyzer_v2()