# スマホ買取代行マネージャー – β9-fix  (括弧・波括弧 完全整合版)
# ----------------------------------------------------------
# streamlit, pandas, requests, beautifulsoup4, pillow, line-bot-sdk
# ----------------------------------------------------------

import os, datetime, re, json, time, random, requests
from requests.adapters import Retry, HTTPAdapter
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# ---------- 共通セッション ----------
sess = requests.Session()
sess.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(total=3, backoff_factor=1.0,
                          status_forcelist=[429, 502, 503, 504])
    )
)

# ---------- LINE SDK (任意) ----------
LINE_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_TOKEN  = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
if LINE_SECRET and LINE_TOKEN:
    from linebot import LineBotApi, WebhookParser
    from linebot.models import MessageEvent, TextMessage, TextSendMessage
    line_bot_api = LineBotApi(LINE_TOKEN)
    parser = WebhookParser(LINE_SECRET)
else:
    line_bot_api = None
    parser = None

# ---------- Streamlit ----------
st.set_page_config(page_title="不用品買取代行マネージャー", layout="centered")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
if "records" not in st.session_state:
    st.session_state.records = []

# ---------- メルカリ平均価格 ----------
UA_MOBILE = ("Mozilla/5.0 (Linux; Android 12; Pixel 6) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/125.0 Mobile Safari/537.36")
UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/125.0 Safari/537.36")

NEXT_RE   = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', re.DOTALL)
STATE_RE  = re.compile(r'window\.__PRELOADED_STATE__\s?=\s?({.*?});</script>', re.DOTALL)
PRICE_RE  = re.compile(r'¥\s?([0-9,]{3,})')

def q(kw: str) -> str:
    return requests.utils.quote(kw.replace(" ", "+"))

def api_try(kw: str):
    url = f"https://api.mercari.jp/v1/search?keyword={q(kw)}&status=on_sale&limit=10"
    r = sess.get(url, headers={"User-Agent": UA_MOBILE, "Accept-Language": "ja-JP"}, timeout=10)
    st.write("API status:", r.status_code)
    if r.status_code != 200:
        return None
    items = r.json().get("data", {}).get("items", [])
    return [int(i["price"]) for i in items if i.get("price")]

def parse_html(html: str):
    m = NEXT_RE.search(html)
    if m:
        try:
            d = json.loads(m.group(1))
            items = (d["props"]["pageProps"].get("searchResults", {})
                     .get("items", []))
            prices = [int(i["price"]) for i in items if i.get("price")]
            if prices:
                return prices
        except Exception as e:
            st.write("NEXT_DATA error:", e)

    m = STATE_RE.search(html)
    if m:
        try:
            s = json.loads(m.group(1))
            items = s["search"]["items"]["data"]["items"]
            prices = [int(i["price"]) for i in items if i.get("price")]
            if prices:
                return prices
        except Exception as e:
            st.write("PRELOADED error:", e)

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    prices = [int(p.replace(",", "")) for p in PRICE_RE.findall(text)]
    return prices[:20] if prices else None

def html_try(kw: str, proxy=False):
    url = f"https://jp.mercari.com/search?keyword={q(kw)}"
    if proxy:
        url = "https://r.jina.ai/http://" + url.lstrip("https://")
    r = sess.get(url, headers={"User-Agent": UA_WEB}, timeout=20)
    st.write("HTML status:", r.status_code, "(proxy)" if proxy else "")
    if r.status_code != 200:
        return None
    return parse_html(r.text)

def get_price(kw: str):
    for fn in (api_try,
               lambda x: html_try(x, False),
               lambda x: html_try(x, True)):
        prices = fn(kw)
        if prices:
            return sum(prices)//len(prices)
        time.sleep(random.uniform(0.8, 1.2))
    return None

# ---------- UI ----------
st.title("📦 不用品買取代行マネージャー (Cookie 不要版)")

tab_form, tab_hist = st.tabs(["📋 登録フォーム", "📖 履歴"])

with tab_form:
    with st.form("reg"):
        item_name   = st.text_input("商品名")
        client_name = st.text_input("依頼者名")
        expect      = st.number_input("想定売却価格 (円)", step=100)

        if st.form_submit_button("🔍 メルカリ平均価格を取得") and item_name:
            price = get_price(item_name)
            if price:
                st.success(f"平均価格: ¥{price:,}")
                expect = price
            else:
                st.error("取得失敗（ヒット 0 件 or API エラー）")

        actual   = st.number_input("実売却価格 (円)", step=100)
        fee_rate = st.slider("手数料率 (%)", 0, 100, 20)
        img_file = st.file_uploader("商品画像", type=["jpg", "png"])
        submit   = st.form_submit_button("📥 登録")

    if submit:
        fee  = int(actual * fee_rate / 100)
        back = actual - fee
        path = None
        if img_file:
            path = os.path.join(UPLOAD_DIR, img_file.name)
            with open(path, "wb") as f:
                f.write(img_file.getbuffer())

        st.session_state.records.append({
            "登録日": datetime.date.today().isoformat(),
            "商品名": item_name,
            "依頼者": client_name,
            "想定売却": expect,
            "実売却": actual,
            "手数料率": fee_rate,
            "手数料": fee,
            "返金額": back,
            "画像パス": path
        })
        st.success("✅ 登録しました！")

with tab_hist:
    if st.session_state.records:
        st.dataframe(pd.DataFrame(st.session_state.records), use_container_width=True)
        for rec in st.session_state.records:
            if rec["画像パス"]:
                st.image(rec["画像パス"], width=240, caption=rec["商品名"])
    else:
        st.info("まだ登録がありません。")

# ---------- LINE Webhook ----------
if line_bot_api and parser:
    from streamlit.web.server.fastapi import add_fastapi_middleware
    from fastapi import FastAPI, Request, HTTPException
    app_fastapi = FastAPI()

    @add_fastapi_middleware(app_fastapi)
    @app_fastapi.post("/line-webhook")
    async def line_webhook(req: Request):
        sig  = req.headers.get("X-Line-Signature", "")
        body = await req.body()
        try:
            events = parser.parse(body.decode("utf-8"), sig)
        except Exception:
            raise HTTPException(status_code=400, detail="signature error")

        for ev in events:
            if isinstance(ev, MessageEvent) and isinstance(ev.message, TextMessage):
                st.session_state.records.append({
                    "登録日": datetime.date.today().isoformat(),
                    "商品名": ev.message.text,
                    "依頼者": f"LINE:{ev.source.user_id}",
                    "想定売却": 0,
                    "実売却": 0,
                    "手数料率": 0,
                    "手数料": 0,
                    "返金額": 0,
                    "画像パス": None
                })
                line_bot_api.reply_message(
                    ev.reply_token,
                    TextSendMessage(text="商品名を登録しました！")
                )
        return {"status": "ok"}
