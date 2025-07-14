# スマホ買取代行マネージャー – β2 (Cookie 不要版)
# ----------------------------------------------------------
# 依存パッケージ:
#   streamlit
#   requests
#   beautifulsoup4
#   pandas
#   pillow
#   line-bot-sdk  ← LINE 連携を使う場合
# ----------------------------------------------------------

import os, datetime, re, requests
from io import BytesIO
from PIL import Image
import pandas as pd
import streamlit as st

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
if LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN:
    from linebot import LineBotApi, WebhookParser
    from linebot.models import MessageEvent, TextMessage
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    parser = WebhookParser(LINE_CHANNEL_SECRET)
else:
    line_bot_api = None
    parser = None

st.set_page_config(page_title="不用品買取代行マネージャー", layout="centered")
UPLOAD_DIR = "uploads"; os.makedirs(UPLOAD_DIR, exist_ok=True)
if "records" not in st.session_state: st.session_state.records = []

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
def get_mercari_price(keyword:str):
    url=f"https://jp.mercari.com/search?keyword={keyword}&sort_order=&status_on_sale=1"
    try: html=requests.get(url,headers=HEADERS,timeout=10).text
    except Exception: return None
    prices=[int(p.replace(',','')) for p in re.findall(r"¥([0-9,]+)</div>",html)][:10]
    return sum(prices)//len(prices) if prices else None

st.title("📦 不用品買取代行マネージャー (Cookie 不要版)")
tab_form,tab_hist=st.tabs(["📋 登録フォーム","📖 履歴"])

with tab_form:
    with st.form("reg"):
        item=st.text_input("商品名")
        client=st.text_input("依頼者名")
        exp_price=st.number_input("想定売却価格 (円)",step=100)
        if st.form_submit_button("🔍 メルカリ平均価格を取得") and item:
            p=get_mercari_price(item)
            st.success(f"平均価格: ¥{p:,}" if p else "取得失敗")
            if p: exp_price=p
        act_price=st.number_input("実売却価格 (円)",step=100)
        fee_rate=st.slider("手数料率 (%)",0,100,20)
        img=st.file_uploader("商品画像",type=["jpg","png"])
        if st.form_submit_button("📥 登録"):
            fee=int(act_price*fee_rate/100); pay=act_price-fee
            img_path=None
            if img:
                img_path=os.path.join(UPLOAD_DIR,img.name)
                with open(img_path,"wb") as f:f.write(img.getbuffer())
            st.session_state.records.append(
                {"登録日":datetime.date.today().isoformat(),"商品名":item,
                 "依頼者":client,"想定売却":exp_price,"実売却":act_price,
                 "手数料率":fee_rate,"手数料":fee,"返金額":pay,"画像パス":img_path})
            st.success("✅ 登録しました！")

with tab_hist:
    if st.session_state.records:
        df=pd.DataFrame(st.session_state.records); st.dataframe(df,use_container_width=True)
        for r in st.session_state.records:
            if r["画像パス"]: st.image(r["画像パス"],width=250,caption=r["商品名"])
    else: st.info("まだ登録がありません。")

if line_bot_api and parser:
    from streamlit.web.server.fastapi import add_fastapi_middleware
    from fastapi import FastAPI, Request, HTTPException
    app=FastAPI()
    @add_fastapi_middleware(app)
    @app.post("/line-webhook")
    async def webhook(req:Request):
        sig=req.headers.get("X-Line-Signature",""); body=await req.body()
        try: ev=parser.parse(body.decode(),sig)
        except Exception: raise HTTPException(status_code=400,detail="sig error")
        for e in ev:
            if isinstance(e,MessageEvent) and isinstance(e.message,TextMessage):
                st.session_state.records.append({"登録日":datetime.date.today().isoformat(),
                    "商品名":e.message.text,"依頼者":f\"LINE:{e.source.user_id}\",
                    "想定売却":0,"実売却":0,"手数料率":0,"手数料":0,"返金額":0,"画像パス":None})
                line_bot_api.reply_message(e.reply_token,TextMessage(text="商品名を登録しました！"))
        return {"status":"ok"}
