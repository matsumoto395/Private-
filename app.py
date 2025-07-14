# スマホ買取代行マネージャー – β9 (HTML 直スキャン対応)
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
sess.mount("https://", HTTPAdapter(
    max_retries=Retry(total=3, backoff_factor=1.0,
                      status_forcelist=[429,502,503,504])))

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

UPLOAD_DIR = "uploads"; os.makedirs(UPLOAD_DIR, exist_ok=True)
if "records" not in st.session_state: st.session_state.records = []

# ---------- メルカリ平均価格 ----------
UA_MOBILE = ("Mozilla/5.0 (Linux; Android 12; Pixel 6) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/125.0 Mobile Safari/537.36")
UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/125.0 Safari/537.36")

NEXT_JS_RE   = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', re.DOTALL)
PRELOAD_RE   = re.compile(r'window\.__PRELOADED_STATE__\s?=\s?({.*?});</script>', re.DOTALL)
PRICE_RE     = re.compile(r'¥\s?([0-9,]{3,})')        # HTML 直接抽出用

def quote_kw(kw:str)->str:
    return requests.utils.quote(kw.replace(" ", "+"))

def _api_try(keyword:str):
    api = (f"https://api.mercari.jp/v1/search?"
           f"keyword={quote_kw(keyword)}&status=on_sale&limit=10")
    r = sess.get(api, headers={"User-Agent": UA_MOBILE,
                               "Accept-Language": "ja-JP"},
                 timeout=10)
    st.write("API status:", r.status_code)
    if r.status_code != 200: return None
    items = r.json().get("data", {}).get("items", [])
    return [int(i["price"]) for i in items if i.get("price")]

def _parse_html(html:str):
    # --- Next.js JSON ---
    m = NEXT_JS_RE.search(html)
    if m:
        try:
            d = json.loads(m.group(1))
            items = (d["props"]["pageProps"]
                       .get("searchResults", {})
                       .get("items", []))
            prices=[int(i["price"]) for i in items if i.get("price")]
            if prices: return prices
        except Exception as e:
            st.write("NEXT_DATA parse error:", e)

    # --- 旧 window.__PRELOADED_STATE__ ---
    m = PRELOAD_RE.search(html)
    if m:
        try:
            st_json=json.loads(m.group(1))
            items=st_json["search"]["items"]["data"]["items"]
            prices=[int(i["price"]) for i in items if i.get("price")]
            if prices: return prices
        except Exception as e:
            st.write("PRELOADED parse error:", e)

    # --- BeautifulSoup + 正規表現 (最後の砦) ---
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    prices = [int(p.replace(",","")) for p in PRICE_RE.findall(text)]
    return prices[:20] if prices else None

def _html_try(keyword:str, use_proxy=False):
    url = f"https://jp.mercari.com/search?keyword={quote_kw(keyword)}"
    if use_proxy:
        url = "https://r.jina.ai/http://" + url.lstrip("https://")
    r = sess.get(url, headers={"User-Agent": UA_WEB}, timeout=20)
    st.write("HTML status:", r.status_code, "(proxy)" if use_proxy else "")
    if r.status_code != 200: return None
    return _parse_html(r.text)

def get_mercari_price(keyword:str):
    for fetch in (_api_try,
                  lambda kw:_html_try(kw, False),
                  lambda kw:_html_try(kw, True)):
        prices = fetch(keyword)
        if prices:
            return sum(prices)//len(prices)
        time.sleep(random.uniform(0.8,1.2))
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
            price = get_mercari_price(item_name)
            if price:
                st.success(f"平均価格: ¥{price:,}")
                expect = price
            else:
                st.error("取得失敗（ヒット 0 件 or API エラー）")

        actual   = st.number_input("実売却価格 (円)", step=100)
        fee_rate = st.slider("手数料率 (%)",0,100,20)
        img_file = st.file_uploader("商品画像", type=["jpg","png"])
        submit   = st.form_submit_button("📥 登録")

    if submit:
        fee  = int(actual*fee_rate/100)
        back = actual-fee
        path = None
        if img_file:
            path=os.path.join(UPLOAD_DIR,img_file.name)
            with open(path,"wb") as f: f.write(img_file.getbuffer())

        st.session_state.records.append({
            "登録日":datetime.date.today().isoformat(),
            "商品名":item_name,"依頼者":client_name,
            "想定売却":expect,"実売却":actual,
            "手数料率":fee_rate,"手数料":fee,"返金額":back,
            "画像パス":path
        })
        st.success("✅ 登録しました！")

with tab_hist:
    if st.session_state.records:
        df=pd.DataFrame(st.session_state.records)
        st.dataframe(df,use_container_width=True)
        for rec in st.session_state.records:
            if rec["画像パス"]:
                st.image(rec["画像パス"],width=240,caption=rec["商品名"])
    else:
        st.info("まだ登録がありません。")

# ---------- LINE Webhook ----------
if line_bot_api and parser:
    from streamlit.web.server.fastapi import add_fastapi_middleware
    from fastapi import FastAPI, Request, HTTPException
    app_fastapi=FastAPI()

    @add_fastapi_middleware(app_fastapi)
    @app_fastapi.post("/line-webhook")
    async def line_webhook(req: Request):
        sig=req.headers.get("X-Line-Signature","")
        body=await req.body()
        try:
            events=parser.parse(body.decode("utf-8"),sig)
        except Exception:
            raise HTTPException(status_code=400,detail="signature error")
        for ev in events:
            if isinstance(ev,MessageEvent) and isinstance(ev.message,TextMessage):
                st.session_state.records.append({
                    "登録日":datetime.date.today().isoformat(),
                    "商品名":ev.message.text,
                    "依頼者":f"LINE:{ev.source.user_id}",
                    "想定売却":0,"実売却":0,
                    "手数料率":0,"手数料":0,"返金額":0,
