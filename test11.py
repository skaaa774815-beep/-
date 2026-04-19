# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 01:18:48 2026

@author: skaaa
"""

# -*- coding: utf-8 -*-
import streamlit as st
import cv2
import numpy as np
import pandas as pd
from PIL import Image
import os
import requests
from bs4 import BeautifulSoup
import re
import json
import base64
from io import BytesIO

# --- ページ設定 ---
st.set_page_config(page_title="七聖召喚デッキ解析ツール", layout="wide", initial_sidebar_state="expanded")

# --- グローバルCSS設定（サイズ140px固定） ---
st.markdown("""
<style>
div[data-testid="stImage"] {
    width: 100% !important;
    max-width: 140px !important; 
    aspect-ratio: 140 / 240 !important;
    margin: 0 auto !important;
    overflow: hidden !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    background-color: #333 !important;
}
div[data-testid="stImage"] img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
}
</style>
""", unsafe_allow_html=True)

# --- 設定ファイルの読み書き ---
def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

# --- 状態管理 ---
if "cards_db" not in st.session_state: st.session_state.cards_db = []
if "custom_main_genres" not in st.session_state: st.session_state.custom_main_genres = load_json("custom_main_genres.json")
if "custom_subgroups" not in st.session_state: st.session_state.custom_subgroups = load_json("custom_subgroups.json")
if "subgroup_orders" not in st.session_state: st.session_state.subgroup_orders = load_json("subgroup_orders.json")
if "custom_tags" not in st.session_state: st.session_state.custom_tags = load_json("custom_tags.json")

if "deck_chars" not in st.session_state: st.session_state.deck_chars = []
if "deck_actions" not in st.session_state: st.session_state.deck_actions = []

cache_dir = "card_images"
if not os.path.exists(cache_dir): os.makedirs(cache_dir)

# --- 画像ハッシュ生成（いたずら防止用） ---
def get_image_hash(pil_img):
    w, h = pil_img.size
    cropped = pil_img.crop((w*0.1, h*0.1, w*0.9, h*0.9))
    resized = cropped.convert("L").resize((16, 16), Image.Resampling.LANCZOS)
    pixels = np.array(resized.getdata()).reshape((16, 16))
    return pixels > pixels.mean()

@st.cache_data
def load_db_hashes(db):
    db_hashes = {}
    for card in db:
        target_path = None
        for ext in [".png", ".jpg", ".jpeg"]:
            p = os.path.join(cache_dir, f"{card['name']}{ext}")
            if os.path.exists(p): target_path = p; break
        if target_path:
            try: db_hashes[card["name"]] = get_image_hash(Image.open(target_path))
            except: pass
    return db_hashes

# --- データベース構築 ---
@st.cache_data
def build_database():
    best_cards = {}
    exclude_keywords = ["一覧", "まとめ", "攻略", "掲示板"]
    
    def get_image_quality(path_or_url):
        if str(path_or_url).startswith("http"): return 1
        if os.path.exists(path_or_url):
            try:
                with Image.open(path_or_url) as img: return img.size[0] * img.size[1]
            except: return 1
        return 0

    files_web = {"1.html": "キャラカード", "2.html": "装備カード", "3.html": "イベントカード", "4.html": "支援カード"}
    for filename, genre in files_web.items():
        if not os.path.exists(filename): continue
        with open(filename, "r", encoding="utf-8") as f: soup = BeautifulSoup(f.read(), "html.parser")
        for td in soup.find_all('td'):
            img = td.find('img'); a_tag = td.find('a')
            if not a_tag or not img: continue
            name = a_tag.get_text().strip(); url = img.get('data-original') or img.get('src', '')
            if not name or not url or ".svg" in url.lower() or any(k in name for k in exclude_keywords): continue
            if url.startswith('//'): url = 'https:' + url
            q = get_image_quality(url)
            if name not in best_cards or q > best_cards[name]["quality"]:
                best_cards[name] = {"name": name, "path_or_url": url, "main_genre": genre, "default_sub": "基本（未分類）", "quality": q}

    if os.path.exists(cache_dir):
        for filename in os.listdir(cache_dir):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")) and "_thumb" not in filename:
                name = os.path.splitext(filename)[0]
                local_path = os.path.join(cache_dir, filename)
                q = get_image_quality(local_path)
                if name not in best_cards or q > best_cards[name]["quality"]:
                    best_cards[name] = {"name": name, "path_or_url": local_path, "main_genre": best_cards.get(name, {}).get("main_genre", "未分類カード"), "default_sub": "基本（未分類）", "quality": q}
    return [{"name": v["name"], "path_or_url": v["path_or_url"], "main_genre": v["main_genre"], "default_sub": v["default_sub"]} for v in best_cards.values()]

@st.cache_data
def get_image_base64(path_or_url, name=None):
    if str(path_or_url).startswith("http"): return path_or_url
    if name:
        for ext in [".png", ".jpg", ".jpeg"]:
            p = os.path.join(cache_dir, f"{name}{ext}")
            if os.path.exists(p):
                with open(p, "rb") as f: return f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    return ""

def render_image_html(img_src):
    return f'<div style="width: 140px; aspect-ratio: 140 / 240; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 8px rgba(0,0,0,0.3);"><img src="{img_src}" style="width: 100%; height: 100%; object-fit: cover;"></div>'

def render_image_gallery(cards_list):
    html = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(135px, 1fr)); gap: 15px;">'
    for card in cards_list:
        src = get_image_base64(card["path_or_url"], card.get("name"))
        html += f'<div style="text-align: center;"><img src="{src}" style="width: 140px; aspect-ratio: 140/240; object-fit: cover; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.4);"><div style="font-size: 0.85em; margin-top: 5px; font-weight: bold;">{card["name"]}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# DB初期化
if not st.session_state.cards_db: st.session_state.cards_db = build_database()
db_hashes = load_db_hashes(st.session_state.cards_db)

# --- UIタブ ---
tab_analyze, tab_database, tab_build, tab_update = st.tabs(["📷 画像解析", "🗃️ データベース", "🛠️ デッキ作成", "🆙 画像更新"])

# タブ1: 解析
with tab_analyze:
    st.title("📷 画像解析")
    uploaded = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="analyze_up")
    if uploaded:
        img = cv2.imdecode(np.asarray(bytearray(uploaded.read()), dtype=np.uint8), 1)
        st.image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if st.button("✨ 解析開始"):
            # 簡易解析ロジック
            st.info("解析中...")
            # (ここに既存の解析処理を入れるか、一旦プレースホルダー)

# タブ2: DB
with tab_database:
    st.title("🗃️ データベース")
    df = pd.DataFrame([{"カード名": c["name"], "分類": c["main_genre"]} for c in st.session_state.cards_db])
    st.dataframe(df, use_container_width=True)

# タブ3: デッキ作成
with tab_build:
    st.title("🛠️ デッキ作成")
    cols = st.columns(6)
    for i, card in enumerate(st.session_state.cards_db[:30]):
        with cols[i % 6]:
            st.markdown(render_image_html(get_image_base64(card["path_or_url"], card["name"])), unsafe_allow_html=True)
            st.button("追加", key=f"btn_{card['name']}")

# タブ4: 画像更新（ここを独立させました！）
with tab_update:
    st.title("🆙 画像アップグレード")
    st.write("ファイル名（カード名.png）と画像の中身をチェックして更新します。")
    uploaded_files = st.file_uploader("高画質画像をアップロード", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="updater")

    if uploaded_files:
        db_names = [c["name"] for c in st.session_state.cards_db]
        for uploaded_file in uploaded_files:
            card_name = os.path.splitext(uploaded_file.name)[0]
            
            if card_name not in db_names:
                st.error(f"❌ '{card_name}' はDBに存在しません。")
                continue

            new_img = Image.open(uploaded_file).convert("RGB")
            new_hash = get_image_hash(new_img)
            
            # いたずら防止：ハッシュ一致チェック
            if card_name in db_hashes:
                diff = np.count_nonzero(new_hash != db_hashes[card_name])
                if diff > 85:
                    st.error(f"🚨 拒否: '{card_name}' と画像の中身が一致しません。")
                    continue

            # 画質判定と保存
            save_path = os.path.join(cache_dir, f"{card_name}.png")
            new_q = new_img.size[0] * new_img.size[1]
            curr_q = 0
            if os.path.exists(save_path):
                with Image.open(save_path) as ci: curr_q = ci.size[0] * ci.size[1]
            
            if new_q > curr_q:
                new_img.save(save_path)
                st.success(f"✅ {card_name} を更新しました！")
            else:
                st.info(f"ℹ️ {card_name} は現在の画像が最高画質です。")

# サイドバー
with st.sidebar:
    st.header("👤 製作者")
    st.markdown(f'<img src="https://unavatar.io/twitter/S_Ka774" style="width:40px; border-radius:50%;"> **skaaa**', unsafe_allow_html=True)
    if st.button("🔄 データを再読み込み"):
        st.cache_data.clear(); st.rerun()