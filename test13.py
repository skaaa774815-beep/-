# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 02:45:50 2026

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
/* ========== 1. デッキ作成タブ（HTML画像）をスマホで4列に強制 ========== */
@media (max-width: 640px) {
    /* カラムの親要素を横並び(Flex)に固定 */
    div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: wrap !important;
        gap: 4px !important;
    }

    /* 各カラムの幅を約24%に強制（4列） */
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        width: 23% !important; 
        flex: 0 0 23% !important;
        min-width: 23% !important;
        padding: 0 !important;
    }

    /* 独自HTML(render_image_html)の画像サイズを枠に合わせる */
    div[data-testid="stMarkdownContainer"] img {
        width: 100% !important;
        height: auto !important;
        display: block;
    }

    /* ボタンを4列の幅に収める */
    div[data-testid="stButton"] button {
        width: 100% !important;
        font-size: 10px !important;
        padding: 0 !important;
        min-height: 28px !important;
    }
}

/* ========== 2. アップロードタブなどの「巨大化」を防止 ========== */
/* st.image で表示される画像が、広い画面で100%にならないように制限 */
div[data-testid="stImage"] {
    max-width: 300px; /* アップロードプレビューなどはこのサイズ以下になる */
    margin: 0 auto;
}

/* ただし、カラム（横並び）の中にある st.image は枠いっぱいに広げる */
div[data-testid="column"] div[data-testid="stImage"] {
    max-width: 100% !important;
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
    <div style="width: 100%; aspect-ratio: 140 / 240; margin: 0 auto 5px auto; overflow: hidden; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.3); background-color: #333;">
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
# タブ3：デッキ作成
# ==========================================
with tab_build:
    st.title("🛠️ デッキ作成")
    
    st.markdown("### 📝 現在のデッキ")
    col_status1, col_status2, col_status3 = st.columns([2, 2, 1])
    with col_status1: st.metric("キャラカード", f"{len(st.session_state.deck_chars)} / 3枚")
    with col_status2: st.metric("アクションカード", f"{len(st.session_state.deck_actions)} / 30枚")
    with col_status3:
        if st.button("🗑️ デッキをすべてクリア", type="primary"):
            clear_deck()
            st.rerun()

    st.markdown("#### 👤 キャラクター")
    if not st.session_state.deck_chars: st.info("キャラカードが選ばれていません。")
    else:
        cols = st.columns(8)
        for i, char_name in enumerate(st.session_state.deck_chars):
            card_info = next((c for c in st.session_state.cards_db if c["name"] == char_name), None)
            if card_info:
                with cols[i % 8]:
                    st.markdown(render_image_html(get_image_base64(card_info["path_or_url"], card_info["name"])), unsafe_allow_html=True)
                    st.button("➖ 外す", key=f"rm_char_{i}_{char_name}", on_click=remove_from_deck, args=(char_name, True))

    st.markdown("#### 🃏 アクションカード")
    if not st.session_state.deck_actions: st.info("アクションカードが選ばれていません。")
    else:
        action_counts = {}
        for a in st.session_state.deck_actions: action_counts[a] = action_counts.get(a, 0) + 1
        
        cols = st.columns(8)
        idx = 0
        for action_name, count in action_counts.items():
            card_info = next((c for c in st.session_state.cards_db if c["name"] == action_name), None)
            if card_info:
                with cols[idx % 8]:
                    st.markdown(render_image_html(get_image_base64(card_info["path_or_url"], card_info["name"])), unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align:center; font-weight:bold;'>{count}枚</div>", unsafe_allow_html=True)
                    
                    b_col1, b_col2 = st.columns(2)
                    with b_col1:
                        st.button("➖", key=f"rm_act_{idx}_{action_name}", on_click=remove_from_deck, args=(action_name, False), help="1枚外す")
                    with b_col2:
                        can_add_more = False
                        if len(st.session_state.deck_actions) < 30:
                            if is_arcane_card(action_name): can_add_more = count < 1
                            else: can_add_more = count < 2
                        
                        main_g = st.session_state.custom_main_genres.get(action_name, card_info["main_genre"])
                        st.button("➕", key=f"add_act_{idx}_{action_name}", on_click=add_to_deck, args=(action_name, main_g), disabled=not can_add_more, help="1枚追加")
                idx += 1

    st.markdown("---")
    st.markdown("### 📋 デッキレシピテキスト（コピー用）")
    
    if not st.session_state.deck_chars and not st.session_state.deck_actions:
        st.info("デッキが空です。カードを追加してください。")
    else:
        counts_for_text = {}
        for char in st.session_state.deck_chars: counts_for_text[char] = 1
        for act in st.session_state.deck_actions: counts_for_text[act] = counts_for_text.get(act, 0) + 1
            
        current_deck_text = generate_deck_recipe_text(counts_for_text)
        st.code(current_deck_text, language="text")

    st.markdown("---")
    st.markdown("### 🔍 カードを探して追加する")
    col_search1, col_search2, col_search3, col_search4 = st.columns(4)
    
    filtered_db = st.session_state.cards_db
    
    with col_search1: build_search_q = st.text_input("名前で検索", key="build_search")
    if build_search_q: filtered_db = [c for c in filtered_db if build_search_q in c["name"]]
        
    available_main_genres = sorted(list(set([st.session_state.custom_main_genres.get(c["name"], c["main_genre"]) for c in filtered_db])))
    with col_search2: build_genre_filter = st.selectbox("大分類", ["すべて"] + available_main_genres)
    if build_genre_filter != "すべて":
        filtered_db = [c for c in filtered_db if st.session_state.custom_main_genres.get(c["name"], c["main_genre"]) == build_genre_filter]
        
    available_subs = sorted(list(set([st.session_state.custom_subgroups.get(c["name"], c["default_sub"]) for c in filtered_db])))
    with col_search3: build_sub_filter = st.selectbox("小分類", ["すべて"] + available_subs)
    if build_sub_filter != "すべて":
        filtered_db = [c for c in filtered_db if st.session_state.custom_subgroups.get(c["name"], c["default_sub"]) == build_sub_filter]

    available_build_tags = set()
    for c in filtered_db:
        t_str = ", ".join(st.session_state.custom_tags.get(c["name"], []))
        if t_str:
            for t in t_str.split(", "):
                if t: available_build_tags.add(t)
                
    with col_search4: build_tag_filter = st.multiselect("タグ", options=get_sorted_tags(available_build_tags), key="build_tag_multiselect")
    if build_tag_filter:
        for t in build_tag_filter:
            filtered_db = [c for c in filtered_db if t in st.session_state.custom_tags.get(c["name"], [])]

    if not filtered_db: 
        st.warning("条件に一致するカードがありません。")
    else:
        st.write(f"{len(filtered_db)}枚のカードが見つかりました。")
        # --- ここを8から6に変更 ---
        cols = st.columns(8) 
        for i, card in enumerate(filtered_db):
            main_g = st.session_state.custom_main_genres.get(card["name"], card["main_genre"])
            # --- ここも6に合わせる ---
            with cols[i % 8]: 
                st.markdown(render_image_html(get_image_base64(card["path_or_url"], card["name"])), unsafe_allow_html=True)
                
                can_add = False
                if main_g == "キャラカード":
                    if len(st.session_state.deck_chars) < 3 and card["name"] not in st.session_state.deck_chars: can_add = True
                else:
                    if len(st.session_state.deck_actions) < 30:
                        if is_arcane_card(card["name"]):
                            if st.session_state.deck_actions.count(card["name"]) < 1: can_add = True
                        else:
                            if st.session_state.deck_actions.count(card["name"]) < 2: can_add = True
                
                if can_add: st.button("➕ 追加", key=f"add_{i}_{card['name']}", on_click=add_to_deck, args=(card["name"], main_g))
                else: st.button("上限です", key=f"max_{i}_{card['name']}", disabled=True)
                
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