# -*- coding: utf-8 -*-
"""
Created on Tue Apr 21 19:05:05 2026

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
import cloudinary
import cloudinary.uploader
import cloudinary.api
from collections import Counter

# Cloudinaryの初期設定
if "cloudinary" in st.secrets:
    cloudinary.config(
        cloud_name = st.secrets["cloudinary"]["cloud_name"],
        api_key = st.secrets["cloudinary"]["api_key"],
        api_secret = st.secrets["cloudinary"]["api_secret"],
        secure = True
    )

# --- ページ設定 ---
st.set_page_config(page_title="七聖召喚デッキ解析ツール", layout="wide", initial_sidebar_state="expanded")

# --- スマホ・PC両対応の列制御CSS（スマート4列バージョン） ---
st.markdown("""
<style>
/* ========== 全体設定 ========== */
div[data-testid="stImage"] {
    margin: 0 auto !important;
    overflow: hidden !important;
    border-radius: 8px !important;
    background-color: transparent !important;
}

/* ========== タブ2: データベースの画像ギャラリー ========== */
.responsive-gallery { 
    display: grid; 
    grid-template-columns: repeat(4, 1fr) !important; /* スマホでは絶対に4列 */
    gap: 8px; 
    margin-bottom: 20px; 
}
@media (min-width: 768px) {
    .responsive-gallery {
        grid-template-columns: repeat(8, 1fr) !important; /* PCでは8列 */
    }
}
.gallery-item { display: flex; flex-direction: column; align-items: center; }
.gallery-item img { 
    width: 100%; 
    aspect-ratio: 140 / 240; 
    object-fit: cover; 
    border-radius: 8px; 
    box-shadow: 0 2px 5px rgba(0,0,0,0.3); 
}
.gallery-item-title { 
    text-align: center; font-size: 0.75em; margin-top: 5px; 
    font-weight: bold; line-height: 1.2; word-break: break-word; 
}

/* ========== タブ3: デッキ作成用のStreamlit列レスポンシブ化 ========== */
/* 基本は強制横並び・折り返し */
div[data-testid="columns"]:has(.card-img-wrapper) {
    flex-direction: row !important;
    flex-wrap: wrap !important;
    gap: 8px 0 !important;
}

/* スマホ用（4列）: 1列あたり約24%の幅 */
div[data-testid="column"]:has(.card-img-wrapper) {
    width: 24% !important;
    flex: 0 0 24% !important;
    min-width: 24% !important;
    padding: 0 4px !important;
}

/* PC用（8列）: 768px以上なら1列あたり約12%の幅 */
@media (min-width: 768px) {
    div[data-testid="column"]:has(.card-img-wrapper) {
        width: 12% !important;
        flex: 0 0 12% !important;
        min-width: 12% !important;
    }
}

/* ➖➕ボタンの横並び調整 */
div[data-testid="column"]:has(.card-img-wrapper) button {
    padding: 2px !important;
    font-size: 12px !important;
    min-height: 32px !important;
    width: 100% !important;
    margin-top: 2px !important;
}
div[data-testid="column"]:has(.card-img-wrapper) div[data-testid="columns"] {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 2px !important;
}
div[data-testid="column"]:has(.card-img-wrapper) div[data-testid="columns"] > div[data-testid="column"] {
    width: 48% !important;
    flex: 0 0 48% !important;
    min-width: 48% !important;
    padding: 0 !important;
}
</style>
""", unsafe_allow_html=True)

# --- グローバルCSS設定 ---
st.markdown("""
<style>
div[data-testid="stImage"] {
    width: 100% !important;
    max-width: 140px !important; /* 105から140へ拡大 */
    aspect-ratio: 140 / 240 !important;
    margin: 0 auto !important;
    overflow: hidden !important;
    border-radius: 10px !important; /* 角丸を少し強調 */
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
/* デッキ作成画面のカード名ラベル調整 */
.card-label {
    font-size: 0.85em;
    text-align: center;
    margin-top: 5px;
    height: 2.8em;
    overflow: hidden;
    line-height: 1.2;
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

def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

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

@st.cache_data(ttl=3600) # 1時間キャッシュしてAPI制限を防ぐ
def get_cloudinary_urls():
    urls = {}
    if "cloudinary" not in st.secrets: return urls
    try:
        # tcg_cards フォルダ内の画像を最大500枚取得
        res = cloudinary.api.resources(type="upload", prefix="tcg_cards/", max_results=500)
        for item in res.get('resources', []):
            name = item['public_id'].split('/')[-1] # "tcg_cards/カード名" から名前を抽出
            urls[name] = item['secure_url']
    except Exception as e:
        print("Cloudinary fetch error:", e)
    return urls

# --- タグ設定 ---
CUSTOM_TAG_ORDER = [
    "氷", "水", "炎", "雷", "風", "岩", "草",
    "モンド", "璃月", "稲妻", "スメール", "フォンテーヌ（プネウマ）", "フォンテーヌ（ウーシア）", "フォンテーヌ（プネウマ/ウーシア）",
    "ナタ", "ナド・クライ", "ファデュイ", "魔物", "エルマイト旅団", "聖骸獣", "宇宙の劫災"
]

def get_sorted_tags(tags_iterable):
    def sort_key(tag):
        if tag in CUSTOM_TAG_ORDER: return (0, CUSTOM_TAG_ORDER.index(tag))
        return (1, tag)
    return sorted(list(set(tags_iterable)), key=sort_key)

def is_arcane_card(card_name):
    tags = st.session_state.custom_tags.get(card_name, [])
    sub = st.session_state.custom_subgroups.get(card_name, "")
    return "秘伝" in tags or "秘伝" in sub

# --- デッキ操作 ---
def add_to_deck(card_name, main_genre):
    if main_genre == "キャラカード":
        if len(st.session_state.deck_chars) < 3 and card_name not in st.session_state.deck_chars:
            st.session_state.deck_chars.append(card_name)
    else:
        if len(st.session_state.deck_actions) < 30:
            if is_arcane_card(card_name):
                if st.session_state.deck_actions.count(card_name) < 1: st.session_state.deck_actions.append(card_name)
            elif st.session_state.deck_actions.count(card_name) < 2:
                st.session_state.deck_actions.append(card_name)

def remove_from_deck(card_name, is_char):
    if is_char and card_name in st.session_state.deck_chars: st.session_state.deck_chars.remove(card_name)
    elif not is_char and card_name in st.session_state.deck_actions: st.session_state.deck_actions.remove(card_name)

def clear_deck():
    st.session_state.deck_chars = []
    st.session_state.deck_actions = []

# --- データベース構築（画質比較機能付き） ---
@st.cache_data
def build_database():
    best_cards = {}
    exclude_keywords = ["一覧", "まとめ", "攻略", "ランキング", "最強", "リセマラ", "戻る", "掲示板", "上げ方", "場所", "TOP", "デッキレシピ", "Twitter", "熟練度", "プレイヤーランク"]
    exclude_exact = ["キャラカード", "装備カード", "支援カード", "イベントカード", "天賦カード"]
    override_genre = {
        "羅網の針": "装備カード", "プクプク獣": "装備カード", "レピーヌ・ポーリーン": "支援カード",
        "元素変幻・開花の祝福": "イベントカード", "元素変幻・炎と岩の祝福": "イベントカード",
        "元素変幻・超電導の祝福": "イベントカード", "元素変幻・蒸発の祝福": "イベントカード",
        "月兆・満照": "イベントカード", "月と故郷": "イベントカード", "お掃除の時間": "イベントカード"
    }

    # 画質（総画素数）を取得する関数
    def get_image_quality(path_or_url):
        local_path = os.path.join(cache_dir, os.path.basename(str(path_or_url)))
        if os.path.exists(local_path):
            try:
                with Image.open(local_path) as img: return img.size[0] * img.size[1]
            except: return 1
        elif not str(path_or_url).startswith("http") and os.path.exists(str(path_or_url)):
            try:
                with Image.open(str(path_or_url)) as img: return img.size[0] * img.size[1]
            except: return 1
        return 0

    # より高画質なら登録/上書きする関数
    def update_if_better(name, path_or_url, genre, default_sub):
        if not name or any(k in name for k in exclude_keywords) or name in exclude_exact:
            return
        
        actual_genre = override_genre.get(name, genre)
        actual_sub = "プレイアブル" if actual_genre == "キャラカード" else "天賦" if actual_genre == "天賦カード" else default_sub
        quality = get_image_quality(path_or_url)
        
        if name not in best_cards or quality > best_cards[name]["quality"]:
            best_cards[name] = {
                "name": name,
                "path_or_url": path_or_url,
                "main_genre": actual_genre,
                "default_sub": actual_sub,
                "quality": quality
            }

    # 1. Web(HTML)からの取得
    files_web = {"1.html": "キャラカード", "2.html": "装備カード", "3.html": "イベントカード", "4.html": "支援カード"}
    for filename, genre in files_web.items():
        if not os.path.exists(filename): continue
        with open(filename, "r", encoding="utf-8") as f: soup = BeautifulSoup(f.read(), "html.parser")
        for td in soup.find_all('td'):
            img = td.find('img'); a_tag = td.find('a')
            if not a_tag or not img: continue
            name = a_tag.get_text().strip(); url = img.get('data-original') or img.get('src', '')
            if not name or not url or ".svg" in url.lower(): continue
            if url.startswith('//'): url = 'https:' + url
            update_if_better(name, url, genre if genre != "天賦カード" else "装備カード", "基本（未分類）")

    # 2. ローカルHTML(genshin_page.html)からの取得
    file_local = "genshin_page.html"
    if os.path.exists(file_local):
        with open(file_local, "r", encoding="utf-8") as f: soup = BeautifulSoup(f.read(), "html.parser")
        ver_text_node = soup.find(string=re.compile("Ver\.6\.5.*追加")) or soup.find(string=re.compile("Ver\.6\.5"))
        if ver_text_node:
            for table in ver_text_node.find_all_next('table', limit=2):
                current_genre = "未分類カード"
                for tr in table.find_all('tr'):
                    th = tr.find('th')
                    if th and "カード" in th.get_text():
                        current_genre = th.get_text().strip(); continue
                    tds = tr.find_all('td')
                    if len(tds) == 1 and not tds[0].find('img'):
                        text = tds[0].get_text().strip()
                        if "カード" in text or "調整" in text: current_genre = text; continue
                    for td in tds:
                        img = td.find('img')
                        if img:
                            name = td.get_text().strip() or img.get('alt', '').strip()
                            img_path = img.get('src', '').replace('./', '')
                            update_if_better(name, img_path, current_genre, "基本（未分類）")

    # 3. フォルダ(card_images)からの直接取得
    if os.path.exists(cache_dir):
        for filename in os.listdir(cache_dir):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")) and "_thumb" not in filename:
                name = os.path.splitext(filename)[0]
                local_path = os.path.join(cache_dir, filename)
                existing_genre = best_cards[name]["main_genre"] if name in best_cards else "未分類カード"
                existing_sub = best_cards[name]["default_sub"] if name in best_cards else "基本（未分類）"
                update_if_better(name, local_path, existing_genre, existing_sub)

    # 4. 【追加】Cloudinaryからの取得（最強画質として上書き！）
    cloud_urls = get_cloudinary_urls()
    for name, url in cloud_urls.items():
        if name in best_cards:
            best_cards[name]["path_or_url"] = url
            best_cards[name]["quality"] = float('inf') # クラウドの画像を最高画質として扱う
        else:
            best_cards[name] = {"name": name, "path_or_url": url, "main_genre": "未分類", "default_sub": "基本（未分類）", "quality": float('inf')}

    # 最終的なリスト（辞書から配列）に変換
    db = []
    for card_info in best_cards.values():
        db.append({
            "name": card_info["name"],
            "path_or_url": card_info["path_or_url"],
            "main_genre": card_info["main_genre"],
            "default_sub": card_info["default_sub"]
        })
    return db

def get_image_hash(pil_img):
    w, h = pil_img.size
    cropped = pil_img.crop((w*0.1, h*0.1, w*0.9, h*0.9))
    resized = cropped.convert("L").resize((16, 16), Image.Resampling.LANCZOS)
    pixels = np.array(resized.getdata()).reshape((16, 16))
    avg = pixels.mean()
    return pixels > avg

@st.cache_data
def load_db_hashes(db):
    db_hashes = {}
    for card in db:
        name = card["name"]
        path_or_url = card["path_or_url"]
        local_p = os.path.join(cache_dir, f"{name}.png")
        
        # 1. ローカルに画像があればハッシュ化
        if os.path.exists(local_p):
            try: db_hashes[name] = get_image_hash(Image.open(local_p))
            except: pass
        # 2. クラウドにしかない場合は、ダウンロードしてローカルに保存してからハッシュ化
        elif str(path_or_url).startswith("http"):
            try:
                response = requests.get(path_or_url)
                img = Image.open(BytesIO(response.content))
                img.save(local_p)
                db_hashes[name] = get_image_hash(img)
            except: pass
    return db_hashes

# ==========================================
# 共通設定・ヘルパー関数（スクリプトの上部に配置）
# ==========================================
import pandas as pd
from collections import Counter

# --- 並び順の固定ルール ---
MAIN_ORDER = ["キャラカード", "アクションカード"]
SUB_ORDER = [
    "プレイアブルキャラ", "その他", "天賦", "武器", "聖遺物", 
    "特技", "元素共鳴", "基本（未分類）", "国家共鳴", "料理", 
    "秘伝", "フィールド", "仲間", "アイテム", "元素変幻"
]

# --- 並び替え用の共通関数 ---
def get_sort_key(item, order_list):
    try:
        return order_list.index(item)
    except ValueError:
        return 999
# ==========================================

# --- 画像表示用（名前を優先してローカルを探す最強仕様） ---
@st.cache_data
def get_image_base64(path, name=None):
    if str(path).startswith("http"): return path
    
    # 1. まず「カード名.png」等で card_images フォルダを探す
    if name:
        for ext in [".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"]:
            target_path = os.path.join(cache_dir, f"{name}{ext}")
            if os.path.exists(target_path):
                try:
                    with open(target_path, "rb") as f:
                        return f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
                except: pass

    # 2. 見つからなければ、HTMLに書いてあったファイル名（card_570.pngなど）で探す
    filename = os.path.basename(str(path).replace("\\", "/").replace("./", ""))
    fallback_path = os.path.join(cache_dir, filename)
    if os.path.exists(fallback_path):
        try:
            with open(fallback_path, "rb") as f:
                return f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
        except: pass
            
    return ""

def render_image_html(img_src):
    return f'''
    <div class="card-img-wrapper" style="width: 100%; aspect-ratio: 140 / 240; margin: 0 auto 5px auto; overflow: hidden; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.3); background-color: #333;">
        <img src="{img_src}" style="width: 100%; height: 100%; object-fit: cover; display: block;">
    </div>
    '''

def render_image_gallery(cards_list):
    html = '<div class="responsive-gallery">'
    for card in cards_list:
        src = get_image_base64(card["path"], card.get("name"))
        img_tag = f'<img src="{src}">' if src else '<div style="width:100%; aspect-ratio: 140 / 240; background:#333; border-radius:8px;"></div>'
        html += f'<div class="gallery-item">{img_tag}<div class="gallery-item-title">{card["name"]}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def generate_deck_recipe_text(card_counts):
    grouped = {}
    total_count = sum(card_counts.values())

    for card_name, count in card_counts.items():
        card_info = next((c for c in st.session_state.cards_db if c["name"] == card_name), None)
        if card_info:
            main_genre = st.session_state.custom_main_genres.get(card_name, card_info["main_genre"])
            if main_genre == "天賦カード": main_genre = "装備カード"
            
            sub_genre = st.session_state.custom_subgroups.get(card_name, card_info["default_sub"])
            if card_info["main_genre"] == "天賦カード" and sub_genre == "基本（未分類）": sub_genre = "天賦"

            if main_genre not in grouped: grouped[main_genre] = {}
            if sub_genre not in grouped[main_genre]: grouped[main_genre][sub_genre] = []
            grouped[main_genre][sub_genre].append((card_name, count))

    result_text = f"【デッキレシピ（計{total_count}枚）】\n\n"
    genre_order = ["キャラカード", "装備カード", "支援カード", "イベントカード"]
    sorted_genres = [g for g in genre_order if g in grouped] + sorted([g for g in grouped if g not in genre_order])

    for main_genre in sorted_genres:
        genre_total = sum(count for sub in grouped[main_genre].values() for _, count in sub)
        result_text += f"■ {main_genre} ({genre_total}枚)\n"
        sub_dict = grouped[main_genre]
        
        order = st.session_state.subgroup_orders.get(main_genre, [])
        subs = list(sub_dict.keys())
        sorted_subs = [s for s in order if s in subs] + sorted([s for s in subs if s not in order])

        for sub_genre in sorted_subs:
            if sub_genre not in ["基本（未分類）", "プレイアブル"] or len(sorted_subs) > 1:
                result_text += f"  ◆ {sub_genre}\n"
                indent = "    ・"
            else:
                indent = "  ・"
            
            for name, count in sorted(sub_dict[sub_genre], key=lambda x: x[0]):
                result_text += f"{indent}{name} ×{count}\n"
        result_text += "\n"
    
    return result_text

if not st.session_state.cards_db:
    with st.spinner("データベースを構築中..."):
        st.session_state.cards_db = build_database()

db_hashes = load_db_hashes(st.session_state.cards_db)

with st.sidebar:
    st.header("⚙️ システム情報")
    st.caption("📅 Ver.6.5 時点")
    st.info(f"ロード済みのカード: {len(st.session_state.cards_db)}枚\n\nハッシュ作成済み: {len(db_hashes)}枚")
    if st.button("🔄 データを再読み込み"):
        build_database.clear()
        get_image_base64.clear()
        load_db_hashes.clear()
        st.rerun()

    # --- ここから作者情報を追加 ---
    st.markdown("---")
    st.header("👤 製作者・お問い合わせ")
    
    # プロフィールをカード形式で表示
    st.markdown(
        """
        <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; border: 1px solid #333; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <img src="https://unavatar.io/twitter/S_Ka774" style="width: 50px; height: 50px; border-radius: 50%; margin-right: 12px; border: 2px solid #555;">
                <div>
                    <div style="color: #fff; font-weight: bold; font-size: 1.1em;">skaaa</div>
                    <div style="color: #888; font-size: 0.9em;">@S_Ka774</div>
                </div>
            </div>
            <div style="color: #ddd; font-size: 0.85em; line-height: 1.4; margin-bottom: 12px;">
                バグや検出違い（カードが認識されない等）があれば、お気軽にDMまでご連絡ください！
            </div>
            <a href="https://twitter.com/S_Ka774" target="_blank" style="text-decoration: none;">
                <div style="background-color: #fff; color: #000; padding: 8px 12px; border-radius: 20px; text-align: center; font-weight: bold; font-size: 0.9em; transition: 0.3s;">
                    𝕏 (Twitter) でDMを送る
                </div>
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )

tab_analyze, tab_database, tab_build, tab_update = st.tabs(["📷 画像解析", "🗃️ データベース", "🛠️ デッキ作成","🆙 画像更新"])

# ==========================================
# タブ1：デッキ画像解析
# ==========================================
with tab_analyze:
    st.title("🃏 七聖召喚 デッキ画像解析 Webツール")
    uploaded_file = st.file_uploader("デッキのスクリーンショットをアップロードしてください", type=["png", "jpg", "jpeg"])

    if uploaded_file is not None:
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        st.image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), caption="アップロードされた画像")
        
        if st.button("✨ 画像を解析する", type="primary"):
            with st.spinner("画像を解析中..."):
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                img_area = img.shape[0] * img.shape[1]
                img_w = img.shape[1]
                
                edges = cv2.Canny(gray, 50, 150)
                kernel = np.ones((3,3), np.uint8)
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
                
                final_rects = [r for r in unique_rects if (img_w * 0.15 < (r[0] + r[2]/2) < img_w * 0.85)]
                final_rects.sort(key=lambda r: (r[1]//100, r[0]))
                
                if not final_rects:
                    st.error("カードの枠を検出できませんでした。別の画像を試してください。")
                elif not db_hashes:
                    st.error("比較用のカード画像がありません。")
                else:
                    detected_cards_list = []
                    for x, y, w, h in final_rects:
                        roi = img[y:y+h, x:x+w]
                        target_hash = get_image_hash(Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)))
                        
                        best_match, min_diff = None, float('inf')
                        for name, db_hash in db_hashes.items():
                            diff = np.count_nonzero(target_hash != db_hash)
                            if diff < min_diff:
                                min_diff = diff; best_match = name
                        
                        if best_match and min_diff < 80:
                            detected_cards_list.append(best_match)

                    if detected_cards_list:
                        st.success(f"解析成功！ {len(detected_cards_list)}枚のカードを検出しました。")
                        st.markdown("### 🎴 検出されたカード")
                        display_detected = []
                        for name in detected_cards_list:
                            card_info = next((c for c in st.session_state.cards_db if c["name"] == name), None)
                            display_detected.append({"name": name, "path": card_info["path_or_url"] if card_info else ""})
                        render_image_gallery(display_detected)
                        st.markdown("---")
                        
                        counts = {}
                        for name in detected_cards_list: counts[name] = counts.get(name, 0) + 1
                        recipe_text = generate_deck_recipe_text(counts)

                        st.markdown("### 📋 解析結果テキスト")
                        st.code(recipe_text, language="text")
                        
                        # --- ここからGeminiへのリンクを追加 ---
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.markdown("👇 テキストをコピーしてAIにデッキの相談をする")
                        st.markdown(
                            """
                            <a href="https://gemini.google.com/" target="_blank" style="text-decoration: none;">
                                <div style="display: inline-flex; align-items: center; background-color: #f0f4f9; color: #1f1f1f; padding: 10px 20px; border-radius: 20px; border: 1px solid #dadce0; font-weight: bold; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                                    <img src="https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690345.svg" width="24" style="margin-right: 10px;">
                                    Geminiを開く（別タブ）
                                </div>
                            </a>
                            """,
                            unsafe_allow_html=True
                        )

# ==========================================
# タブ2：カードデータベース一覧
# ==========================================
with tab_database:
    st.title("🗃️ 完全版カードデータベース")
    if len(st.session_state.cards_db) > 0:
        display_data = []
        for card in st.session_state.cards_db:
            name = card["name"]
            main = st.session_state.custom_main_genres.get(name, card["main_genre"])
            if main == "天賦カード": main = "装備カード"
            sub = st.session_state.custom_subgroups.get(name, card["default_sub"])
            tags = ", ".join(st.session_state.custom_tags.get(name, []))
            display_data.append({"画像パス": card["path_or_url"], "カード名": name, "大分類": main, "小分類": sub, "タグ": tags})

        df = pd.DataFrame(display_data)

        # --- 検索・フィルターUI ---
        st.markdown("#### 🔍 絞り込み検索")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1: search_q = st.text_input("名前で検索", "")
        if search_q: df = df[df["カード名"].str.contains(search_q)]
        
        with col2: genre_filter = st.multiselect("大分類", options=df["大分類"].unique())
        if genre_filter: df = df[df["大分類"].isin(genre_filter)]
        
        with col3: sub_filter = st.multiselect("小分類", options=df["小分類"].unique())
        if sub_filter: df = df[df["小分類"].isin(sub_filter)]
        
        with col4:
            all_tags = set()
            for t_str in df["タグ"]:
                if t_str:
                    for t in t_str.split(", "): 
                        if t: all_tags.add(t)
            tag_filter = st.multiselect("タグ", options=get_sorted_tags(all_tags))
            
        if tag_filter:
            for t in tag_filter: df = df[df["タグ"].str.contains(t, na=False)]

        st.markdown("---")
        view_mode = st.radio("表示形式を選択", ["🖼️ 画像ギャラリーで見る", "📋 表で見る"], horizontal=True)
        st.markdown("---")

        if view_mode == "📋 表で見る":
            st.dataframe(df.drop(columns=["画像パス"]), use_container_width=True, height=600)
        else:
            for main_genre in df["大分類"].unique():
                group_df = df[df["大分類"] == main_genre]
                if not group_df.empty:
                    st.subheader(f"■ {main_genre}")
                    for sub_g in group_df["小分類"].unique():
                        sub_df = group_df[group_df["小分類"] == sub_g]
                        st.markdown(f"**📂 {sub_g}**")
                        render_image_gallery([{"name": r["カード名"], "path": r["画像パス"]} for _, r in sub_df.iterrows()])

# ==========================================
# タブ3：デッキ作成（並び順固定・カテゴリ統合版）
# ==========================================
with tab_build:
    from collections import Counter
    import pandas as pd

    # --- 0. CSS設定：枚数カウントを画面上部に固定 ---
    st.markdown("""
    <style>
    /* ステータスバーを固定する設定 */
    [data-testid="stMetricContainer"] {
        background-color: rgba(28, 31, 46, 0.9); /* 背景色(少し透過) */
        padding: 10px;
        border-radius: 10px;
        border: 1px solid #4a4a4a;
    }
    /* スクロール時に上部に張り付くコンテナ */
    .sticky-header {
        position: sticky;
        top: 2.8rem;
        z-index: 100;
        background-color: #0e1117; /* アプリの背景色に合わせて調整 */
        padding: 10px 0;
        border-bottom: 2px solid #333;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("🛠️ オリジナルデッキ構築")

    # --- 1. 固定ステータスバー ---
    char_count = len(st.session_state.deck_chars)
    action_count = len(st.session_state.deck_actions)
    
    # 🌟 追加：画面に常に追従するフローティングバー（CSS + HTML）
    st.markdown(f"""
    <style>
    /* =========================================
       1. 追従バー（PC/スマホ共通）
       ========================================= */
    .floating-deck-status {{
        position: fixed;
        bottom: 30px; /* 下から少し浮かせ、Manage app等との重なりを防ぐ */
        right: 30px;
        background: rgba(15, 17, 26, 0.9);
        color: white;
        padding: 10px 20px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        z-index: 10000; /* 十分に高い数値 */
        font-size: 14px;
        border: 1px solid #444;
        backdrop-filter: blur(8px);
        pointer-events: none; /* バー自体がクリックを邪魔しないように設定 */
    }}

    /* =========================================
       2. スマホ専用設定 (幅768px以下)
       ========================================= */
    @media (max-width: 768px) {{
        
        /* 📱 追従バー：スマホでは中央上部に配置（操作の邪魔にならない位置） */
        .floating-deck-status {{
            bottom: auto !important;
            top: 60px !important; /* 画面の一番上、ヘッダーの下あたり */
            left: 50% !important;
            right: auto !important;
            transform: translateX(-50%) !important;
            width: 90% !important;
            max-width: 350px !important;
            display: flex !important;
            justify-content: space-around !important;
            padding: 8px !important;
            font-size: 13px !important;
        }}

        /* 📱 画像の強制横3列：最優先で上書き */
        /* Streamlitの全カラムコンテナを対象 */
        [data-testid="stHorizontalBlock"] {{
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap !important;
            gap: 5px !important;
        }}

        /* カラム1つずつの幅を31%程度に固定 */
        [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            width: calc(33% - 5px) !important;
            min-width: calc(33% - 5px) !important;
            flex: 0 0 calc(33% - 5px) !important;
            margin-bottom: 5px !important;
        }}

        /* 画像サイズを枠いっぱいにフィットさせる */
        [data-testid="stHorizontalBlock"] img {{
            width: 100% !important;
            height: auto !important;
            object-fit: contain !important;
        }}

        /* ボタンのテキストを小さくしてはみ出し防止 */
        [data-testid="stHorizontalBlock"] button {{
            font-size: 10px !important;
            padding: 0px !important;
            min-height: 25px !important;
        }}
    }}
    </style>
    
    <div class="floating-deck-status">
        <span>👤 キャラ: <span style="color: {'#ff4b4b' if char_count == 3 else '#4ade80'};">{char_count}</span> / 3</span>
        <span>🃏 アクション: <span style="color: {'#ff4b4b' if action_count == 30 else '#4ade80'};">{action_count}</span> / 30</span>
    </div>
    """, unsafe_allow_html=True)

    # --- 2. 📝 デッキレシピのテキスト出力（追加機能） ---
    with st.expander("📝 デッキレシピをテキストで出力"):
        if char_count == 0 and action_count == 0:
            st.warning("カードが選択されていません。")
        else:
            # 出力用テキストの構築
            recipe_text = "【デッキレシピ】\n\n"
            
            # キャラクター
            recipe_text += "■キャラクターカード\n"
            for c in st.session_state.deck_chars:
                recipe_text += f"・{c}\n"
            
            # アクションカード（ジャンル別）
            recipe_text += "\n■アクションカード\n"
            
            # ジャンル分けの準備
            actions_with_info = []
            for name in st.session_state.deck_actions:
                card_info = next((c for c in st.session_state.cards_db if c["name"] == name), None)
                sub = st.session_state.custom_subgroups.get(name, card_info["default_sub"] if card_info else "未分類")
                # 天賦カードの移動ルール適用
                main = st.session_state.custom_main_genres.get(name, card_info["main_genre"] if card_info else "その他")
                if main == "天賦カード": sub = "天賦"
                actions_with_info.append({"name": name, "sub": sub})
            
            df_actions = pd.DataFrame(actions_with_info)
            if not df_actions.empty:
                counts = Counter(st.session_state.deck_actions)
                # 定義したSUB_ORDER順に並べて出力
                SUB_ORDER = ["天賦", "武器", "聖遺物", "特技", "元素共鳴", "国家共鳴", "料理", "秘伝", "フィールド", "仲間", "アイテム", "元素変幻"]
                
                present_subs = [s for s in SUB_ORDER if s in df_actions["sub"].unique()]
                for sub_val in present_subs:
                    recipe_text += f"（{sub_val}）\n"
                    sub_names = sorted(df_actions[df_actions["sub"] == sub_val]["name"].unique())
                    for n in sub_names:
                        recipe_text += f"・{n} x{counts[n]}\n"
            
            st.text_area("以下のテキストをコピーしてください", value=recipe_text, height=300)
            st.caption("※SNSやメモ帳にそのまま貼り付けて使用できます。")

    st.markdown("---")

    # --- 2. 📋 現在の編成エリア ---
    st.subheader("📋 現在の編成")
    # (キャラクター・アクションカードの表示ロジックは前回と同様のため省略可ですが、
    #  秘伝制限などは維持したまま名前順にソートして表示します)
    
    # キャラ表示
    if st.session_state.deck_chars:
        st.markdown("**【キャラクター】**")
        cols_c = st.columns(8)
        for idx, name in enumerate(st.session_state.deck_chars):
            card_info = next((c for c in st.session_state.cards_db if c["name"] == name), None)
            with cols_c[idx % 8]:
                if card_info:
                    st.markdown(render_image_html(get_image_base64(card_info["path_or_url"], name)), unsafe_allow_html=True)
                    st.button("➖", key=f"del_char_{idx}", on_click=remove_from_deck, args=(name, True), use_container_width=True)
    
    # アクション表示
    if st.session_state.deck_actions:
        st.markdown("**【アクションカード】**")
        counts = Counter(st.session_state.deck_actions)
        action_items = sorted(list(counts.items()))
        for i in range(0, len(action_items), 8):
            cols_a = st.columns(8)
            for j, (name, count) in enumerate(action_items[i:i+8]):
                card_info = next((c for c in st.session_state.cards_db if c["name"] == name), None)
                with cols_a[j]:
                    if card_info:
                        st.markdown(render_image_html(get_image_base64(card_info["path_or_url"], name)), unsafe_allow_html=True)
                        st.markdown(f"<div style='text-align:center; font-size:0.8rem; font-weight:bold;'>x{count}</div>", unsafe_allow_html=True)
                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1: st.button("➖", key=f"m_{name}", on_click=remove_from_deck, args=(name, False), use_container_width=True)
                        with btn_c2:
                            is_arcane = "秘伝" in st.session_state.custom_tags.get(name, [])
                            st.button("➕", key=f"p_{name}", on_click=add_to_deck, args=(name, "アクション"), 
                                      disabled=(count >= (1 if is_arcane else 2) or action_count >= 30), use_container_width=True)

    st.markdown("---")

    # --- 3. 🔍 絞り込み検索（カテゴリ移動とソート適用） ---
    st.subheader("🔎 カードを探す")
    
    # データの準備と「天賦カード」の移動処理
    raw_data = []
    for c in st.session_state.cards_db:
        main = st.session_state.custom_main_genres.get(c["name"], c["main_genre"])
        sub = st.session_state.custom_subgroups.get(c["name"], c["default_sub"])
        
        # 【重要】大分類が「天賦カード」なら「アクションカード」の「天賦」へ移動
        if main == "天賦カード":
            main = "アクションカード"
            sub = "天賦"
            
        raw_data.append({
            "path": c["path_or_url"], "name": c["name"], "main": main, "sub": sub,
            "tags": st.session_state.custom_tags.get(c["name"], [])
        })
    df_build = pd.DataFrame(raw_data)

    col1, col2, col3, col4 = st.columns(4)
    with col1: q_name = st.text_input("名前検索", key="b_q_name")
    
    with col2:
        # 大分類を固定順で表示
        q_main_opt = sorted(df_build["main"].unique(), key=lambda x: get_sort_key(x, MAIN_ORDER))
        q_main = st.multiselect("大分類", options=q_main_opt, key="b_q_main")
        
    with col3:
        # 小分類を画像 の順番で表示
        rel_df = df_build[df_build["main"].isin(q_main)] if q_main else df_build
        q_sub_opt = sorted(rel_df["sub"].unique(), key=lambda x: get_sort_key(x, SUB_ORDER))
        q_sub = st.multiselect("小分類", options=q_sub_opt, key="b_q_sub")
        
    with col4:
        # タグの並び替え
        rel_tag_df = rel_df[rel_df["sub"].isin(q_sub)] if q_sub else rel_df
        relevant_tags = set(t for t_list in rel_tag_df["tags"] for t in t_list)
        try: tag_options = get_sorted_tags(relevant_tags)
        except: tag_options = sorted(list(relevant_tags))
        q_tag = st.multiselect("タグ", options=tag_options, key="b_q_tag")

    # フィルタリング
    f_res = df_build
    if q_name: f_res = f_res[f_res["name"].str.contains(q_name)]
    if q_main: f_res = f_res[f_res["main"].isin(q_main)]
    if q_sub: f_res = f_res[f_res["sub"].isin(q_sub)]
    if q_tag:
        for t in q_tag: f_res = f_res[f_res["tags"].apply(lambda x: t in x)]

    # --- 4. 🖼️ 見出し付き画像ギャラリー（並び順反映） ---
    if not f_res.empty:
        # 大分類のループ（固定順）
        sorted_mains = sorted(f_res["main"].unique(), key=lambda x: get_sort_key(x, MAIN_ORDER))
        for main_val in sorted_mains:
            st.subheader(f"■ {main_val}")
            main_df = f_res[f_res["main"] == main_val]
            
            # 小分類のループ（固定順）
            sorted_subs = sorted(main_df["sub"].unique(), key=lambda x: get_sort_key(x, SUB_ORDER))
            for sub_val in sorted_subs:
                st.markdown(f"**📂 {sub_val}**")
                sub_df = main_df[main_df["sub"] == sub_val]
                
                # 8列グリッド表示
                sub_items = sub_df.to_dict('records')
                for i in range(0, len(sub_items), 8):
                    cols = st.columns(8)
                    for j, card in enumerate(sub_items[i:i+8]):
                        with cols[j]:
                            name, tags = card["name"], card["tags"]
                            st.markdown(render_image_html(get_image_base64(card["path"], name)), unsafe_allow_html=True)
                            
                            is_arcane = "秘伝" in tags
                            limit = 1 if is_arcane else 2
                            cur_cnt = st.session_state.deck_actions.count(name) if "キャラ" not in card["main"] else st.session_state.deck_chars.count(name)
                            
                            can_add = False
                            if "キャラ" in card["main"]:
                                if len(st.session_state.deck_chars) < 3 and cur_cnt == 0: can_add = True
                            else:
                                if len(st.session_state.deck_actions) < 30 and cur_cnt < limit: can_add = True
                            
                            st.button("➕" if can_add else "×", key=f"bl_{name}_{i}_{j}", 
                                      on_click=add_to_deck if can_add else None, 
                                      args=(name, card["main"]), disabled=not can_add, use_container_width=True)
    else:
        st.write("条件に一致するカードがありません。")

                
# ==========================================
# タブ4：画像更新
# ==========================================
with tab_update:
    st.title("🆙 カード判定・手動確認アップグレード")
    st.write("画像をアップロードすると、AIがどのカードか判定します。内容を確認して「更新」ボタンを押してください。")

    uploaded_files = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="bulk_update")

    if uploaded_files:
        if not db_hashes:
            st.error("比較対象のデータがありません。先に「データを再読み込み」を行ってください。")
        else:
            st.markdown("### 🔍 判定結果の確認")
            
            for i, uploaded_file in enumerate(uploaded_files):
                # 1. 画像読み込みと特徴抽出
                new_img = Image.open(uploaded_file).convert("RGB")
                new_hash = get_image_hash(new_img)
                
                best_match_name = None
                min_diff = 256
                
                # 全DBと照合
                for card_name, db_h in db_hashes.items():
                    diff = np.count_nonzero(new_hash != db_h)
                    if diff < min_diff:
                        min_diff = diff
                        best_match_name = card_name
                
                # 2. 表示エリアの作成
                with st.container():
                    st.markdown(f"#### 📸 ファイル: {uploaded_file.name}")
                    
                    full_width_msg = st.empty()
                    
                    # 3列で比較表示
                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col1:
                        st.image(new_img, caption="アップロードされた画像", use_container_width=True)
                    
                    # 判定に成功した場合
                    if best_match_name and min_diff < 85: # しきい値は少し緩めに設定
                        match_rate = ((256 - min_diff) / 256) * 100
                        
                        with col2:
                            # 判定されたカードの情報
                            st.info(f"**AI判定: {best_match_name}**")
                            st.write(f"一致度: {match_rate:.1f}%")
                            
                            # 画質チェック用データの準備
                            new_q = new_img.size[0] * new_img.size[1]
                            curr_q = 0
                            local_path = os.path.join(cache_dir, f"{best_match_name}.png")
                            
                            if os.path.exists(local_path):
                                with Image.open(local_path) as ci: curr_q = ci.size[0] * ci.size[1]
                            
                            st.write(f"解像度: {'↑ 向上' if new_q > curr_q else '↓ 低下または維持'}")
                            
                            # --- YES / NO 確認ボタン ---
                            # 個別のボタンにするためkeyにindex(i)を含める
                            confirm_col1, confirm_col2 = st.columns(2)
                            with confirm_col1:
                                if st.button(f"✅ 更新 (Yes)", key=f"yes_{i}_{best_match_name}"):
                                    if new_q > curr_q:
                                        with st.spinner("☁️ クラウドにアップロード中..."):
                                            # 画像をメモリ上のデータに変換
                                            buf = BytesIO()
                                            new_img.save(buf, format="PNG")
                                            
                                            # Cloudinaryへアップロード
                                            cloudinary.uploader.upload(
                                                buf.getvalue(),
                                                folder="tcg_cards", # Cloudinary内のフォルダ名
                                                public_id=best_match_name,
                                                overwrite=True
                                            )
                                            # ローカルにも保存しておく（ハッシュ計算や高速化のため）
                                            new_img.save(local_path)
                                            
                                            # キャッシュをクリアして最新を読み込ませる
                                            get_cloudinary_urls.clear()
                                            build_database.clear()
                                            
                                        full_width_msg.success(f"✅ {best_match_name} をクラウドに保存しました！(全ユーザーに反映されます)")
                                    else:
                                        full_width_msg.warning("画質が低下するため保存をスキップしました。")
                            
                            with confirm_col2:
                                if st.button(f"❌ 違う (No)", key=f"no_{i}_{best_match_name}"):
                                    # 🔴 st.error を full_width_msg.error に変更
                                    full_width_msg.error("更新をキャンセルしました。")

                        with col3:
                            # 現在登録されている画像を表示
                            card_info = next((c for c in st.session_state.cards_db if c["name"] == best_match_name), None)
                            if card_info:
                                current_src = get_image_base64(card_info["path_or_url"], best_match_name)
                                st.image(current_src, caption="現在の登録画像", use_container_width=True)
                    else:
                        with col2:
                            st.error("⚠️ カードを特定できませんでした。")
                    
                    st.divider() # 区切り線

    st.warning("更新を反映させるには、完了後に左側の「データを再読み込み」を押してください。")