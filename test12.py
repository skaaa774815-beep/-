# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 01:47:35 2026

@author: skaaa
"""

import cv2
import numpy as np
from PIL import Image
import os

# --- 1. 元のプログラムから抽出した基幹ロジック ---

def get_image_hash(pil_img):
    """画像から指紋（ハッシュ）を作成する"""
    w, h = pil_img.size
    # 枠線の影響を抑えるため中央80%をカット
    cropped = pil_img.crop((w*0.1, h*0.1, w*0.9, h*0.9))
    # 16x16のグレースケールに縮小
    resized = cropped.convert("L").resize((16, 16), Image.Resampling.LANCZOS)
    pixels = np.array(resized.getdata()).reshape((16, 16))
    avg = pixels.mean()
    return pixels > avg

def verify_analysis(image_path, db_hashes):
    """判定プロセスを詳細に表示して検証する"""
    # 画像読み込み
    img = cv2.imread(image_path)
    if img is None:
        print("エラー: 画像が読み込めません。")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_w = img.shape[1]
    img_area = img.shape[0] * img.shape[1]

    # --- 形状認識 (元の黄金比パラメータ) ---
    edges = cv2.Canny(gray, 94, 101)
    kernel = np.ones((8, 8), np.uint8) 
    edges = cv2.dilate(edges, kernel, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    potential_rects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if h == 0: continue
        aspect_ratio = w / float(h)
        area = w * h
        if 0.45 < aspect_ratio < 0.85 and (img_area * 0.005 < area < img_area * 0.2):
            potential_rects.append((x, y, w, h))

    unique_rects = []
    for r in potential_rects:
        x, y, w, h = r
        is_duplicate = False
        for ux, uy, uw, uh in unique_rects:
            if abs(x - ux) < w/2 and abs(y - uy) < h/2:
                is_duplicate = True; break
        if not is_duplicate: unique_rects.append(r)

    final_rects = [r for r in unique_rects if (img_w * 0.10 < (r[0] + r[2]/2) < img_w * 0.90)]
    final_rects.sort(key=lambda r: (r[1]//100, r[0]))

    # --- 判定検証のメインループ ---
    print(f"--- 解析開始: 検出枠数 {len(final_rects)} ---")
    
    for i, (x, y, w, h) in enumerate(final_rects):
        # 1枚分の画像を切り出し
        roi = img[y:y+h, x:x+w]
        roi_pil = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        target_hash = get_image_hash(roi_pil)
        
        # データベースとの総当たり比較
        match_details = []
        for name, db_hash in db_hashes.items():
            diff = np.count_nonzero(target_hash != db_hash)
            match_details.append((name, diff))
        
        # スコア順にソート（diffが小さい＝似ている）
        match_details.sort(key=lambda x: x[1])
        
        best_name, min_diff = match_details[0]
        
        # 結果表示
        status = "✅ OK" if min_diff < 80 else "❓ 不明"
        print(f"[{i+1:02d}] 座標({x},{y}) | 判定: {best_name:15s} | スコア: {min_diff:3d} | {status}")
        
        # 誤判定が疑わしい場合（次点候補との差が小さい等）のデバッグ用
        if 0 < len(match_details) > 1:
            runner_up_name, runner_up_diff = match_details[1]
            if runner_up_diff - min_diff < 10:
                print(f"     ⚠️ 僅差の候補: {runner_up_name} (スコア: {runner_up_diff})")

# --- 実行方法 ---
# db_hashes = st.session_state.db_hashes  # すでに存在する辞書データ
# verify_analysis("test_image.png", db_hashes)