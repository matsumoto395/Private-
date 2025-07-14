# スマホ買取代行マネージャー – β5-fixed
# ----------------------------------------------------------
# 依存パッケージ:
#   streamlit
#   pandas
#   requests
#   beautifulsoup4
#   pillow
#   line-bot-sdk  ← LINE 連携を使う場合のみ
# ----------------------------------------------------------

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

# ---------- メルカリ平均価格 (API → HTML フォールバック) ----------
UA_MOBILE = "Mercari/3.0.0 (Android)"
UA_WEB    = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/123.0 Safari/537.36")

import re, json

def _api_try(keyword: str):
    api = (
        "https://api.mercari.jp/v1/search?"
        f"keyword={requests.utils.quote(keyword)}"
        "&status=on_sale&limit=10"
    )
    r = requests.get(api, headers={"User-Agent": UA_MOBILE}, timeout=8)
    if r.status_code != 200:
        return None
    items = r.json().get("data", {}).get("items", [])
    return [int(i["price"]) for i in items if i.get("price")]

def _html_try(keyword: str):
    url = f"https://jp.mercari.com/search?keyword={requests.utils.quote(keyword)}"
    html = requests.get(url, headers={"User-Agent": UA_WEB}, timeout=8).text
    m = re.search(r'window\.__PRELOADED_STATE__\s?=\s?({.*?});</script>', html)
    if not m:
        return None
    state = json.loads(m.group(1))
    items = state["search"]["items"]["data"]["items"]
    return [int(it["price"]) for it in items[:10]]

def get_mercari_price(keyword: str):
    """API が失敗したら HTML 解析にフォールバックして平均価格を返す"""
    for fetch in (_api_try, _html_try):
        prices = fetch(keyword)
        if prices:
            return sum(prices) // len(prices)
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
        st.success("✅ 登録しました！")

with tab_hist:
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records)
        st.dataframe(df, use_container_width=True)
        for rec in st.session_state.records:
            if rec["画像パス"]:
                st.image(rec["画像パス"], width=240, caption=rec["商品名"])
    else:
        st.info("まだ登録がありません。")

# ---------- LINE Webhook (任意) ----------
if line_bot_api and parser:
    from streamlit.web.server.fastapi import add_fastapi_middleware
    from fastapi import FastAPI, Request, HTTPException
    app_fastapi = FastAPI()

    @add_fastapi_middleware(app_fastapi)
    @app_fastapi.post("/line-webhook")
    async def line_webhook(request: Request):
        signature = request.headers.get("X-Line-Signature", "")
        body = await request.body()
        try:
            events = parser.parse(body.decode("utf-8"), signature)
        except Exception:
            raise HTTPException(status_code=400, detail="signature error")

        for event in events:
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
                st.session_state.records.append({
                    "登録日": datetime.date.today().isoformat(),
                    "商品名": event.message.text,
                    "依頼者": f"LINE:{event.source.user_id}",
                    "想定売却": 0,
                    "実売却": 0,
                    "手数料率": 0,
                    "手数料": 0,
                    "返金額": 0,
                    "画像パス": None
                })
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="商品名を登録しました！")
                )
        return {"status": "ok"}
