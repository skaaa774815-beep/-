# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 01:47:35 2026

@author: skaaa
"""

import cv2
import numpy as np
from PIL import Image

def identify_card_process(roi_img, db_hashes):
    """
    roi_img: 切り出したカード1枚分の画像 (OpenCV形式)
    db_hashes: { "カード名": ハッシュ値 } の辞書
    """
    
    # --- STEP 1: 正規化 (Normalization) ---
    # サイズや色味のバラつきを抑えるため、決まった形に整えます
    # ハッシュ関数(get_image_hash)内部で行われる処理を可視化
    roi_rgb = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(roi_rgb)
    
    # --- STEP 2: 特徴抽出 (Hashing) ---
    # 画像を非常に小さくし、色の濃淡を「0」と「1」のビット列に変換します
    # これがいわゆる「画像の指紋」になります
    target_hash = get_image_hash(pil_img) # 既存の関数を使用
    
    # --- STEP 3: 全データとの総当たり比較 ---
    # データベースにある全カードの指紋と、今のカードの指紋を1つずつ比べます
    results = []
    for name, db_hash in db_hashes.items():
        # ハミング距離の計算：2つのビット列が何箇所違うかを数える
        # np.count_nonzero(target_hash != db_hash)
        diff = np.count_nonzero(target_hash != db_hash)
        results.append((name, diff))
    
    # --- STEP 4: 最も似ているものを探す (Best Match) ---
    # 違い（diff）が最も少ないものを「正解」の候補とします
    results.sort(key=lambda x: x[1])
    best_match, min_diff = results[0]
    
    # --- STEP 5: 信頼度判定 (Thresholding) ---
    # あまりに似ていない（diffが大きすぎる）場合は「不明」として弾きます
    # この「80」という数値が判定の厳しさを決めます
    if min_diff < 80:
        return best_match, min_diff
    else:
        return "Unknown", min_diff

# --- 検証用：判定の様子を出力 ---
def debug_identification(roi_img, db_hashes):
    name, score = identify_card_process(roi_img, db_hashes)
    print(f"【判定結果】")
    print(f"特定された名前: {name}")
    print(f"不一致スコア: {score} (低いほど正確)")
    
    # 上位3つの候補を表示してみる
    # (内部でどう迷っているかが見える)