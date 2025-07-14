# スマホ買取代行マネージャー – β5 (公式 JSON API 版 / Cookie 不要)
# ------------------------------------------------------------------
# 依存パッケージ:
#   streamlit
#   pandas
#   requests
#   beautifulsoup4
#   pillow
#   line-bot-sdk     ← LINE 連携を使う場合のみ
# ------------------------------------------------------------------

import os, datetime, requests
import pandas as pd
import streamlit as st

# ---------- LINE SDK (任意) ----------
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
if LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN:
    from linebot import LineBotApi, WebhookParser
    from linebot.models import MessageEvent, TextMessage, TextSendMessage
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    parser = WebhookParser(LINE_CHANNEL_SECRET)
else:
    line_bot_api = None
    parser = None

# ---------- Streamlit config ----------
st.set_page_config(page_title="不用品買取代行マネージャー", layout="centered")

# ---------- データ保存 ----------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
if "records" not in st.session_state:
    st.session_state.records = []

# ---------- メルカリ平均価格　(公式 JSON API) ----------
HEADERS = {"User-Agent": "Mercari/3.0.0 (Android)"}

def get_mercari_price(keyword: str):
    """
    メルカリアプリが利用する検索 API を呼び、
    上位10件の平均価格を返す。
    """
    try:
        api = (
            "https://api.mercari.jp/v1/search?"
            f"keyword={requests.utils.quote(keyword)}"
            "&status=on_sale&limit=10"
        )
        obj = requests.get(api, headers=HEADERS, timeout=10).json()
        items = obj.get("data", {}).get("items", [])
        prices = [int(item["price"]) for item in items if item.get("price")]
        return sum(prices)//len(prices) if prices else None
    except Exception as e:
        st.warning(f"Mercari API error: {e}")
        return None

# ---------- UI ----------
st.title("📦 不用品買取代行マネージャー (Cookie 不要版)")

tab_form, tab_hist = st.tabs(["📋 登録フォーム", "📖 履歴"])

with tab_form:
    with st.form("reg_form"):
        item_name   = st.text_input("商品名")
        client_name = st.text_input("依頼者名")
        expected_price = st.number_input("想定売却価格 (円)", step=100)

        if st.form_submit_button("🔍 メルカリ平均価格を取得") and item_name:
            price = get_mercari_price(item_name)
            if price:
                st.success(f"平均価格: ¥{price:,}")
                expected_price = price
            else:
                st.error("取得失敗（ヒット 0 件 or API エラー）")

        actual_price = st.number_input("実売却価格 (円)", step=100)
        fee_rate     = st.slider("手数料率 (%)", 0, 100, 20)
        img_file     = st.file_uploader("商品画像", type=["jpg", "png"])
        submitted    = st.form_submit_button("📥 登録")

    if submitted:
        fee      = int(actual_price * fee_rate / 100)
        pay_back = actual_price - fee
        img_path = None
        if img_file:
            img_path = os.path.join(UPLOAD_DIR, img_file.name)
            with open(img_path, "wb") as f:
                f.write(img_file.getbuffer())

        st.session_state.records.append({
            "登録日":   datetime.date.today().isoformat(),
            "商品名":   item_name,
            "依頼者":   client_name,
            "想定売却": expected_price,
            "実売却":   actual_price,
            "手数料率": fee_rate,
            "手数料":   fee,
            "返金額":   pay_back,
            "画像パス": img_path
        })
        st.success("✅
