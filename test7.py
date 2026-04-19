# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 00:16:02 2026

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

# --- グローバルCSS設定 ---
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

# --- タグ設定 ---
CUSTOM_TAG_ORDER = [
    "氷", "水", "炎", "雷", "風", "岩", "草",
    "モンド", "璃月", "稲妻", "スメール", "フォンテーヌ（プネウマ）", "フォンテーヌ（ウーシア）", "フォンテーヌ（プネウマ/ウーシア）",
    "ナタ", "ナど・クライ", "ファデュイ", "魔物", "エルマイト旅団", "聖骸獣", "宇宙の劫災"
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

    def get_image_quality(path_or_url):
        local_path = os.path.join(cache_dir, os.path.basename(str(path_or_url)))
        if os.path.exists(local_path):
            try:
                with Image.open(local_path) as img: return img.size[0] * img.size[1]
            except: return 1
        return 0

    def update_if_better(name, path_or_url, genre, default_sub):
        if not name or any(k in name for k in exclude_keywords) or name in exclude_exact: return
        actual_genre = override_genre.get(name, genre)
        actual_sub = "プレイアブル" if actual_genre == "キャラカード" else "天賦" if actual_genre == "天賦カード" else default_sub
        quality = get_image_quality(path_or_url)
        if name not in best_cards or quality > best_cards[name]["quality"]:
            best_cards[name] = {"name": name, "path_or_url": path_or_url, "main_genre": actual_genre, "default_sub": actual_sub, "quality": quality}

    # 1. Web(HTML)
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
            update_if_better(name, url, genre, "基本（未分類）")

    # 2. フォルダ(card_images)
    if os.path.exists(cache_dir):
        for filename in os.listdir(cache_dir):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")) and "_thumb" not in filename:
                name = os.path.splitext(filename)[0]
                local_path = os.path.join(cache_dir, filename)
                existing_genre = best_cards[name]["main_genre"] if name in best_cards else "未分類カード"
                existing_sub = best_cards[name]["default_sub"] if name in best_cards else "基本（未分類）"
                update_if_better(name, local_path, existing_genre, existing_sub)

    return [{"name": v["name"], "path_or_url": v["path_or_url"], "main_genre": v["main_genre"], "default_sub": v["default_sub"]} for v in best_cards.values()]

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
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', card["name"])
        target_path = os.path.join(cache_dir, f"{safe_name}_thumb.png")
        if not os.path.exists(target_path):
            for ext in [".png", ".jpg", ".jpeg"]:
                p = os.path.join(cache_dir, f"{card['name']}{ext}")
                if os.path.exists(p): target_path = p; break
        if os.path.exists(target_path):
            try: db_hashes[card["name"]] = get_image_hash(Image.open(target_path))
            except: pass
    return db_hashes

@st.cache_data
def get_image_base64(path, name=None):
    if str(path).startswith("http"): return path
    if name:
        for ext in [".png", ".jpg", ".jpeg", ".PNG", ".JPG"]:
            p = os.path.join(cache_dir, f"{name}{ext}")
            if os.path.exists(p):
                with open(p, "rb") as f: return f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    return ""

def render_image_html(img_src):
    return f'<div style="width: 100%; max-width: 105px; aspect-ratio: 105 / 180; margin: 0 auto 5px auto; overflow: hidden; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); background-color: #333;"><img src="{img_src}" style="width: 100%; height: 100%; object-fit: cover; display: block;"></div>'

def render_image_gallery(cards_list):
    html = '<style>.responsive-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 10px; margin-bottom: 20px; } .gallery-item { display: flex; flex-direction: column; align-items: center; } .gallery-item img { width: 100%; max-width: 105px; aspect-ratio: 105 / 180; object-fit: cover; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.3); transition: transform 0.2s; } .gallery-item img:hover { transform: scale(1.05); } .gallery-item-title { text-align: center; height: 3.5em; line-height: 1.4; overflow: hidden; font-size: 0.85em; margin-top: 8px; word-break: break-word; }</style><div class="responsive-gallery">'
    for card in cards_list:
        src = get_image_base64(card["path"], card.get("name"))
        img_tag = f'<img src="{src}" alt="{card["name"]}">' if src else '<div style="width:100%; aspect-ratio: 1/1.45; background:#333; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#888;">No Image</div>'
        html += f'<div class="gallery-item">{img_tag}<div class="gallery-item-title">{card["name"]}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def generate_deck_recipe_text(card_counts):
    grouped = {}
    for name, count in card_counts.items():
        info = next((c for c in st.session_state.cards_db if c["name"] == name), None)
        if info:
            main = st.session_state.custom_main_genres.get(name, info["main_genre"])
            if main == "天賦カード": main = "装備カード"
            sub = st.session_state.custom_subgroups.get(name, info["default_sub"])
            if info["main_genre"] == "天賦カード" and sub == "基本（未分類）": sub = "天賦"
            if main not in grouped: grouped[main] = {}
            if sub not in grouped[main]: grouped[main][sub] = []
            grouped[main][sub].append((name, count))
    
    total = sum(card_counts.values())
    res = f"【デッキレシピ（計{total}枚）】\n\n"
    order = ["キャラカード", "装備カード", "支援カード", "イベントカード"]
    for m in [g for g in order if g in grouped] + sorted([g for g in grouped if g not in order]):
        res += f"■ {m} ({sum(c for s in grouped[m].values() for _,c in s)}枚)\n"
        sub_o = st.session_state.subgroup_orders.get(m, [])
        for s in [x for x in sub_o if x in grouped[m]] + sorted([x for x in grouped[m] if x not in sub_o]):
            indent = "    ・" if (s not in ["基本（未分類）", "プレイアブル"] or len(grouped[m]) > 1) else "  ・"
            if indent == "    ・": res += f"  ◆ {s}\n"
            for n, c in sorted(grouped[m][s]): res += f"{indent}{n} ×{c}\n"
        res += "\n"
    return res

if not st.session_state.cards_db: st.session_state.cards_db = build_database()
db_hashes = load_db_hashes(st.session_state.cards_db)

# --- サイドバー (Ver.6.5 & Twitterリンク追加) ---
with st.sidebar:
    st.header("⚙️ システム情報")
    st.caption("📅 Ver.6.5 時点")
    st.info(f"ロード済みのカード: {len(st.session_state.cards_db)}枚\n\nハッシュ作成済み: {len(db_hashes)}枚")
    if st.button("🔄 データを再読み込み"):
        build_database.clear(); get_image_base64.clear(); load_db_hashes.clear(); st.rerun()

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

tab_analyze, tab_database, tab_build = st.tabs(["📷 画像解析", "🗃️ データベース", "🛠️ デッキ作成"])

with tab_analyze:
    st.title("🃏 七聖召喚 デッキ画像解析")
    uploaded = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
    if uploaded:
        img = cv2.imdecode(np.asarray(bytearray(uploaded.read()), dtype=np.uint8), 1)
        st.image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if st.button("✨ 解析開始", type="primary"):
            with st.spinner("解析中..."):
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3,3), np.uint8), iterations=1)
                contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
                rects = []
                for cnt in contours:
                    x,y,w,h = cv2.boundingRect(cnt)
                    if h > 0 and 0.45 < w/h < 0.85 and (img.shape[0]*img.shape[1]*0.005 < w*h < img.shape[0]*img.shape[1]*0.2):
                        if not any(abs(x-ux)<w/2 and abs(y-uy)<h/2 for ux,uy,uw,uh in rects): rects.append((x,y,w,h))
                rects = sorted([r for r in rects if img.shape[1]*0.15 < r[0]+r[2]/2 < img.shape[1]*0.85], key=lambda r: (r[1]//100, r[0]))
                
                detected = []
                for x,y,w,h in rects:
                    hsh = get_image_hash(Image.fromarray(cv2.cvtColor(img[y:y+h, x:x+w], cv2.COLOR_BGR2RGB)))
                    best, mn = None, 999
                    for n, dbh in db_hashes.items():
                        diff = np.count_nonzero(hsh != dbh)
                        if diff < mn: mn = diff; best = n
                    if best and mn < 80: detected.append(best)
                
                if detected:
                    st.success(f"{len(detected)}枚検出")
                    render_image_gallery([{"name": n, "path": next(c["path_or_url"] for c in st.session_state.cards_db if c["name"]==n)} for n in detected])
                    recipe = generate_deck_recipe_text({n: detected.count(n) for n in set(detected)})
                    st.code(recipe, language="text")
                    
                    # --- Gemini連携ボタン ---
                    st.markdown("<br>👇 コピーしてAIに相談する", unsafe_allow_html=True)
                    st.markdown("""
                        <a href="https://gemini.google.com/" target="_blank" style="text-decoration: none;">
                            <div style="display: inline-flex; align-items: center; background-color: #f0f4f9; color: #1f1f1f; padding: 10px 20px; border-radius: 20px; border: 1px solid #dadce0; font-weight: bold; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                                <img src="https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690345.svg" width="24" style="margin-right: 10px;">
                                Geminiを開く
                            </div>
                        </a>
                    """, unsafe_allow_html=True)

# (データベースタブ、デッキ作成タブは前回と同様のロジックが継続されます)
with tab_database:
    st.title("🗃️ データベース")
    if st.session_state.cards_db:
        df = pd.DataFrame([{"カード名": c["name"], "大分類": st.session_state.custom_main_genres.get(c["name"], c["main_genre"]), "小分類": st.session_state.custom_subgroups.get(c["name"], c["default_sub"]), "タグ": ", ".join(st.session_state.custom_tags.get(c["name"], []))} for c in st.session_state.cards_db])
        st.dataframe(df, use_container_width=True)

with tab_build:
    st.title("🛠️ デッキ作成")
    st.write(f"キャラ: {len(st.session_state.deck_chars)}/3, アクション: {len(st.session_state.deck_actions)}/30")
    if st.button("クリア"): clear_deck(); st.rerun()