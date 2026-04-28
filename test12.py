# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 01:47:35 2026

@author: skaaa
"""

import streamlit as st
import cv2
import numpy as np
from PIL import Image

def run_debug_analyzer():
    st.title("🛠️ 画像解析デバッガー")
    st.write("どの工程でカードが消えているかを視覚的に特定します。")

    uploaded_file = st.file_uploader("検証する画像をアップロード", type=["png", "jpg", "jpeg", "webp"])

    if uploaded_file is not None:
        # 画像の読み込み
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        h_img, w_img, _ = img.shape
        img_area = h_img * w_img

        # --- STEP 1: エッジ検出の確認 ---
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        kernel = np.ones((3,3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=1)

        # --- STEP 2: 全ての輪郭を抽出（フィルタリング前） ---
        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        all_rects_img = img_rgb.copy()
        raw_rects = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # 全ての枠を一旦描画（緑色）
            cv2.rectangle(all_rects_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
            
            # カードらしい比率とサイズのものだけ選別
            aspect_ratio = w / float(h) if h > 0 else 0
            area = w * h
            if 0.45 < aspect_ratio < 0.85 and (img_area * 0.005 < area < img_area * 0.2):
                raw_rects.append((x, y, w, h))

        # --- STEP 3: 重複排除後の結果 ---
        filtered_rects_img = img_rgb.copy()
        unique_rects = []
        for r in raw_rects:
            x, y, w, h = r
            is_duplicate = False
            for ux, uy, uw, uh in unique_rects:
                # 🔴 ここがクク竜消失の最有力候補ロジック
                if abs(x - ux) < w/2 and abs(y - uy) < h/2:
                    is_duplicate = True; break
            if not is_duplicate:
                unique_rects.append(r)
                # 残った枠を描画（赤色）
                cv2.rectangle(filtered_rects_img, (x, y), (x+w, y+h), (255, 0, 0), 3)

        # --- 結果の表示 ---
        st.subheader("1. エッジ検出（カードがくっついていないか？）")
        st.image(dilated, caption="白い線が繋がって1つの四角形に見えていたら、カード同士が合体しています。")

        st.subheader("2. 抽出された全候補（緑枠）")
        st.image(all_rects_img, caption="ここにクク竜の枠が2つあれば、形状認識までは成功しています。")

        st.subheader("3. 重複排除・最終結果（赤枠）")
        st.image(filtered_rects_img, caption="ここでクク竜が1つ消えていたら、重複排除ロジックが原因です。")

        # 数値データの表示
        st.info(f"検出された枠の総数: {len(unique_rects)} 枚")
        
        with st.expander("詳細な座標データを見る"):
            for i, (x, y, w, h) in enumerate(unique_rects):
                st.write(f"Card {i+1}: x={x}, y={y}, w={w}, h={h}, Aspect={round(w/h, 2)}")

# アプリの実行
if __name__ == "__main__":
    run_debug_analyzer()