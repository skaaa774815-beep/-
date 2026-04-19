# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 00:59:57 2026

@author: skaaa
"""

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

# --- グローバルCSS設定（st.imageのサイズ統一・ガタガタ防止） ---
st.markdown("""
<style>
div[data-testid="stImage"] {
    width: 100% !important;
    max-width: 105px !important;
    aspect-ratio: 105 / 180 !important;
    margin: 0 auto !important;
    overflow: hidden !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2) !important;
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
div[data-testid="column"] {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    margin-bottom: 15px;
}
div.stButton > button {
    width: 100% !important;
    padding: 4px 0px !important;
    margin-top: 5px !important;
}
</style>
""", unsafe_allow_html=True)

# --- 設定ファイルの読み書き関数 ---
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

# --- 状態管理 (Session State) ---
if "cards_db" not in st.session_state:
    st.session_state.cards_db = []
if "custom_main_genres" not in st.session_state:
    st.session_state.custom_main_genres = load_json("custom_main_genres.json")
if "custom_subgroups" not in st.session_state:
    st.session_state.custom_subgroups = load_json("custom_subgroups.json")
if "subgroup_orders" not in st.session_state:
    st.session_state.subgroup_orders = load_json("subgroup_orders.json")
if "custom_tags" not in st.session_state:
    st.session_state.custom_tags = load_json("custom_tags.json")

if "deck_chars" not in st.session_state:
    st.session_state.deck_chars = []
if "deck_actions" not in st.session_state:
    st.session_state.deck_actions = []

cache_dir = "card_images"
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

# --- タグのカスタム並び順設定 ---
CUSTOM_TAG_ORDER = [
    "氷", "水", "炎", "雷", "風", "岩", "草",
    "モンド", "璃月", "稲妻", "スメール", "フォンテーヌ（プネウマ）", "フォンテーヌ（ウーシア）", "フォンテーヌ（プネウマ/ウーシア）",
    "ナタ", "ナド・クライ", "ファデュイ", "魔物", "エルマイト旅団", "聖骸獣", "宇宙の劫災"
]

def get_sorted_tags(tags_iterable):
    def sort_key(tag):
        if tag in CUSTOM_TAG_ORDER:
            return (0, CUSTOM_TAG_ORDER.index(tag))
        return (1, tag)
    return sorted(list(set(tags_iterable)), key=sort_key)

# --- 秘伝カード判定用のヘルパー関数 ---
def is_arcane_card(card_name):
    tags = st.session_state.custom_tags.get(card_name, [])
    sub = st.session_state.custom_subgroups.get(card_name, "")
    return "秘伝" in tags or "秘伝" in sub

# --- デッキ操作用のコールバック関数 ---
def add_to_deck(card_name, main_genre):
    if main_genre == "キャラカード":
        if len(st.session_state.deck_chars) < 3 and card_name not in st.session_state.deck_chars:
            st.session_state.deck_chars.append(card_name)
    else:
        if len(st.session_state.deck_actions) < 30:
            if is_arcane_card(card_name):
                # 秘伝カードは同名1枚まで（別名は追加可能）
                if st.session_state.deck_actions.count(card_name) < 1:
                    st.session_state.deck_actions.append(card_name)
            elif st.session_state.deck_actions.count(card_name) < 2:
                st.session_state.deck_actions.append(card_name)

def remove_from_deck(card_name, is_char):
    if is_char and card_name in st.session_state.deck_chars:
        st.session_state.deck_chars.remove(card_name)
    elif not is_char and card_name in st.session_state.deck_actions:
        st.session_state.deck_actions.remove(card_name)

def clear_deck():
    st.session_state.deck_chars = []
    st.session_state.deck_actions = []

# --- データベース構築処理 ---
@st.cache_data
def build_database():
    db = []
    seen_names = set()
    exclude_keywords = ["一覧", "まとめ", "攻略", "ランキング", "最強", "リセマラ", "戻る", "掲示板", "上げ方", "場所", "TOP", "デッキレシピ", "Twitter", "熟練度", "プレイヤーランク"]
    exclude_exact = ["キャラカード", "装備カード", "支援カード", "イベントカード", "天賦カード"]
    override_genre = {
        "羅網の針": "装備カード", "プクプク獣": "装備カード", "レピーヌ・ポーリーン": "支援カード",
        "元素変幻・開花の祝福": "イベントカード", "元素変幻・炎と岩の祝福": "イベントカード",
        "元素変幻・超電導の祝福": "イベントカード", "元素変幻・蒸発の祝福": "イベントカード",
        "月兆・満照": "イベントカード", "月と故郷": "イベントカード", "お掃除の時間": "イベントカード"
    }

    files_web = {"1.html": "キャラカード", "2.html": "装備カード", "3.html": "イベントカード", "4.html": "支援カード"}
    for filename, genre in files_web.items():
        if not os.path.exists(filename): continue
        with open(filename, "r", encoding="utf-8") as f: soup = BeautifulSoup(f.read(), "html.parser")
        for td in soup.find_all('td'):
            img = td.find('img'); a_tag = td.find('a')
            if not a_tag or not img: continue
            name = a_tag.get_text().strip(); url = img.get('data-original') or img.get('src', '')
            if not name or not url or any(k in name for k in exclude_keywords) or name in exclude_exact or ".svg" in url.lower() or name in seen_names: continue
            if url.startswith('//'): url = 'https:' + url
            
            actual_genre = override_genre.get(name, "装備カード" if genre == "天賦カード" else genre)
            default_sub = "プレイアブル" if actual_genre == "キャラカード" else "天賦" if genre == "天賦カード" else "基本（未分類）"
            db.append({"name": name, "path_or_url": url, "main_genre": actual_genre, "default_sub": default_sub})
            seen_names.add(name)

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
                            if not name or any(x in name for x in exclude_keywords) or name in exclude_exact: continue
                            img_path = img.get('src', '').replace('./', '')
                            
                            target_genre = override_genre.get(name, current_genre)
                            default_sub = "プレイアブル" if target_genre == "キャラカード" else "天賦" if target_genre == "天賦カード" else "基本（未分類）"
                            if name not in seen_names:
                                db.append({"name": name, "path_or_url": img_path, "main_genre": target_genre, "default_sub": default_sub})
                                seen_names.add(name)
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
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', card["name"])
        thumb_path = os.path.join(cache_dir, f"{safe_name}_thumb.png")
        if os.path.exists(thumb_path):
            try:
                pil_img = Image.open(thumb_path)
                db_hashes[card["name"]] = get_image_hash(pil_img)
            except: pass
    return db_hashes

@st.cache_data
def get_image_base64(path):
    if str(path).startswith("http"): 
        return path
    
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/png;base64,{data}"
    except:
        pass
        
    try:
        import urllib.parse  # ←★暗号を解読するツールを呼び出す
        
        filename = os.path.basename(path)
        # ★ここで「%E3%83...」みたいな暗号を「ダリア.png」に戻す！
        decoded_filename = urllib.parse.unquote(filename) 
        
        fallback_path = os.path.join("card_images", decoded_filename)
        with open(fallback_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/png;base64,{data}"
    except Exception as e:
        print(f"🚨画像が見つかりません: {path}")
        return ""

def render_image_html(img_src):
    return f"""
    <div style="width: 100%; max-width: 105px; aspect-ratio: 105 / 180; margin: 0 auto 5px auto; overflow: hidden; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); background-color: #333;">
        <img src="{img_src}" style="width: 100%; height: 100%; object-fit: cover; display: block;">
    </div>
    """
def render_image_gallery(cards_list):
    html = """
    <style>
    .responsive-gallery {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
        gap: 10px;
        margin-bottom: 20px;
    }
    .gallery-item { display: flex; flex-direction: column; align-items: center; }
    .gallery-item img {
        width: 100%; max-width: 105px; aspect-ratio: 105 / 180; object-fit: cover;
        border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.3); transition: transform 0.2s;
    }
    .gallery-item img:hover { transform: scale(1.05); }
    .gallery-item-title {
        text-align: center; height: 3.5em; line-height: 1.4; overflow: hidden;
        font-size: 0.85em; margin-top: 8px; word-break: break-word;
    }
    </style>
    <div class="responsive-gallery">
    """
    for card in cards_list:
        img_src = get_image_base64(card["path"])
        img_tag = f'<img src="{img_src}" alt="{card["name"]}">' if img_src else '<div style="width:100%; aspect-ratio: 1/1.45; background:#333; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#888;">No Image</div>'
        html += f'<div class="gallery-item">{img_tag}<div class="gallery-item-title">{card["name"]}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# デッキレシピテキスト生成関数
def generate_deck_recipe_text(card_counts):
    grouped = {}
    total_count = sum(card_counts.values())

    for card_name, count in card_counts.items():
        card_info = next((c for c in st.session_state.cards_db if c["name"] == card_name), None)
        if card_info:
            main_genre = st.session_state.custom_main_genres.get(card_name, card_info["main_genre"])
            if main_genre == "天賦カード": main_genre = "装備カード"
            
            sub_genre = st.session_state.custom_subgroups.get(card_name, card_info["default_sub"])
            if card_info["main_genre"] == "天賦カード" and sub_genre == "基本（未分類）":
                sub_genre = "天賦"

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
    st.info(f"ロード済みのカード: {len(st.session_state.cards_db)}枚\n\nハッシュ作成済み: {len(db_hashes)}枚")
    if st.button("🔄 データを再読み込み"):
        build_database.clear()
        get_image_base64.clear()
        st.rerun()

tab_analyze, tab_database, tab_build = st.tabs(["📷 画像解析", "🗃️ データベース", "🛠️ デッキ作成"])

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
                    st.error("比較用のカード画像がありません。一度ローカル版ツールで画像を表示させてから実行してください。")
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
        
        with col1: 
            search_q = st.text_input("名前で検索", "")
        if search_q: df = df[df["カード名"].str.contains(search_q)]
        
        with col2: 
            genre_filter = st.multiselect("大分類", options=df["大分類"].unique())
        if genre_filter: df = df[df["大分類"].isin(genre_filter)]
        
        with col3: 
            sub_filter = st.multiselect("小分類", options=df["小分類"].unique())
        if sub_filter: df = df[df["小分類"].isin(sub_filter)]
        
        with col4:
            all_tags = set()
            for t_str in df["タグ"]:
                if t_str:
                    for t in t_str.split(", "): 
                        if t: all_tags.add(t)
            tag_filter = st.multiselect("タグ", options=get_sorted_tags(all_tags))
            
        if tag_filter:
            for t in tag_filter:
                df = df[df["タグ"].str.contains(t, na=False)]

        st.markdown("---")
        view_mode = st.radio("表示形式を選択", ["🖼️ 画像ギャラリーで見る", "📋 表で見る"], horizontal=True)
        st.markdown("---")

        if view_mode == "📋 表で見る":
            st.dataframe(df.drop(columns=["画像パス"]), use_container_width=True, height=600)
        else:
            for main_genre in ["キャラカード", "装備カード", "支援カード", "イベントカード"]:
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
    if not st.session_state.deck_chars:
        st.info("キャラカードが選ばれていません。")
    else:
        cols = st.columns(8)
        for i, char_name in enumerate(st.session_state.deck_chars):
            card_info = next((c for c in st.session_state.cards_db if c["name"] == char_name), None)
            if card_info:
                with cols[i % 8]:
                    st.markdown(render_image_html(get_image_base64(card_info["path_or_url"])), unsafe_allow_html=True)
                    st.button("➖ 外す", key=f"rm_char_{i}_{char_name}", on_click=remove_from_deck, args=(char_name, True))

    st.markdown("#### 🃏 アクションカード")
    if not st.session_state.deck_actions:
        st.info("アクションカードが選ばれていません。")
    else:
        action_counts = {}
        for a in st.session_state.deck_actions:
            action_counts[a] = action_counts.get(a, 0) + 1
        
        cols = st.columns(8)
        idx = 0
        for action_name, count in action_counts.items():
            card_info = next((c for c in st.session_state.cards_db if c["name"] == action_name), None)
            if card_info:
                with cols[idx % 8]:
                    st.markdown(render_image_html(get_image_base64(card_info["path_or_url"])), unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align:center; font-weight:bold;'>{count}枚</div>", unsafe_allow_html=True)
                    
                    b_col1, b_col2 = st.columns(2)
                    with b_col1:
                        st.button("➖", key=f"rm_act_{idx}_{action_name}", on_click=remove_from_deck, args=(action_name, False), help="1枚外す")
                    with b_col2:
                        can_add_more = False
                        if len(st.session_state.deck_actions) < 30:
                            if is_arcane_card(action_name):
                                can_add_more = count < 1 # 秘伝は同名1枚まで
                            else:
                                can_add_more = count < 2
                        
                        main_g = st.session_state.custom_main_genres.get(action_name, card_info["main_genre"])
                        st.button("➕", key=f"add_act_{idx}_{action_name}", on_click=add_to_deck, args=(action_name, main_g), disabled=not can_add_more, help="1枚追加")
                idx += 1

    st.markdown("---")
    st.markdown("### 📋 デッキレシピテキスト（コピー用）")
    
    if not st.session_state.deck_chars and not st.session_state.deck_actions:
        st.info("デッキが空です。カードを追加してください。")
    else:
        counts_for_text = {}
        for char in st.session_state.deck_chars:
            counts_for_text[char] = 1
        for act in st.session_state.deck_actions:
            counts_for_text[act] = counts_for_text.get(act, 0) + 1
            
        current_deck_text = generate_deck_recipe_text(counts_for_text)
        st.code(current_deck_text, language="text")

    st.markdown("---")
    
    st.markdown("### 🔍 カードを探して追加する")
    col_search1, col_search2, col_search3, col_search4 = st.columns(4)
    
    filtered_db = st.session_state.cards_db
    
    with col_search1: 
        build_search_q = st.text_input("名前で検索", key="build_search")
    if build_search_q: 
        filtered_db = [c for c in filtered_db if build_search_q in c["name"]]
        
    available_main_genres = sorted(list(set([st.session_state.custom_main_genres.get(c["name"], c["main_genre"]) for c in filtered_db])))
    with col_search2: 
        build_genre_filter = st.selectbox("大分類", ["すべて"] + available_main_genres)
        
    if build_genre_filter != "すべて":
        filtered_db = [c for c in filtered_db if st.session_state.custom_main_genres.get(c["name"], c["main_genre"]) == build_genre_filter]
        
    available_subs = sorted(list(set([st.session_state.custom_subgroups.get(c["name"], c["default_sub"]) for c in filtered_db])))
    with col_search3: 
        build_sub_filter = st.selectbox("小分類", ["すべて"] + available_subs)

    if build_sub_filter != "すべて":
        filtered_db = [c for c in filtered_db if st.session_state.custom_subgroups.get(c["name"], c["default_sub"]) == build_sub_filter]

    available_build_tags = set()
    for c in filtered_db:
        t_str = ", ".join(st.session_state.custom_tags.get(c["name"], []))
        if t_str:
            for t in t_str.split(", "):
                if t: available_build_tags.add(t)
                
    with col_search4:
        build_tag_filter = st.multiselect("タグ", options=get_sorted_tags(available_build_tags), key="build_tag_multiselect")
        
    if build_tag_filter:
        for t in build_tag_filter:
            filtered_db = [c for c in filtered_db if t in st.session_state.custom_tags.get(c["name"], [])]

    if not filtered_db:
        st.warning("条件に一致するカードがありません。")
    else:
        st.write(f"{len(filtered_db)}枚のカードが見つかりました。")
        cols = st.columns(8)
        for i, card in enumerate(filtered_db):
            main_g = st.session_state.custom_main_genres.get(card["name"], card["main_genre"])
            with cols[i % 8]:
                st.markdown(render_image_html(get_image_base64(card["path_or_url"])), unsafe_allow_html=True)
                
                can_add = False
                if main_g == "キャラカード":
                    if len(st.session_state.deck_chars) < 3 and card["name"] not in st.session_state.deck_chars: can_add = True
                else:
                    if len(st.session_state.deck_actions) < 30:
                        if is_arcane_card(card["name"]):
                            # 秘伝カードの場合、同じカードがまだ入っていなければ追加可能
                            if st.session_state.deck_actions.count(card["name"]) < 1:
                                can_add = True
                        else:
                            if st.session_state.deck_actions.count(card["name"]) < 2:
                                can_add = True
                
                if can_add:
                    st.button("➕ 追加", key=f"add_{i}_{card['name']}", on_click=add_to_deck, args=(card["name"], main_g))
                else:
                    st.button("上限です", key=f"max_{i}_{card['name']}", disabled=True)