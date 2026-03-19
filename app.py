import streamlit as st
import httpx
import pandas as pd
import re
import asyncio
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS # 用於搜尋官方連結

# --- 1. 搜尋官方連結的函數 ---
def find_official_url(tender_name):
    """利用標案名稱搜尋政府電子採購網的原始網址"""
    with DDGS() as ddgs:
        # 強制搜尋政府官方網域
        query = f"{tender_name} site:web.pcc.gov.tw"
        results = list(ddgs.text(query, max_results=3))
        if results:
            return results[0]['href']
    return None

# --- 2. 抓取官方網頁內容並讓 AI 整理 (模擬 AI 處理邏輯) ---
async def ai_gather_and_summarize(tender_name):
    official_url = find_official_url(tender_name)
    
    if not official_url:
        return f"❌ 找不到官方公開資料。建議手動至政府電子採購網搜尋：{tender_name}"

    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient() as client:
        try:
            # 抓取官方頁面 (官方頁面是公開免費的)
            resp = await client.get(official_url, headers=headers, timeout=15.0)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 這裡抓取官方頁面的所有文字
            raw_text = soup.get_text(separator=" ", strip=True)
            
            # --- AI 整理區 (這裡你之後可以串接 OpenAI 或 Gemini API) ---
            # 目前我們先用 Python 邏輯進行關鍵資訊提取，模擬 AI 整理結果
            budget = re.search(r"預算金額[:：]\s*([\d,]+)", raw_text)
            deadline = re.search(r"截止投標[:：]\s*(\d{3}/\d{2}/\d{2})", raw_text)
            
            summary = f"""
            ### 🤖 AI 搜集結果
            *   **官方連結**: [點我開啟官方原始網頁]({official_url})
            *   **預算金額**: {budget.group(1) if budget else "需進入官網確認"}
            *   **截止日期**: {deadline.group(1) if deadline else "需進入官網確認"}
            
            #### 📋 標案需求摘要 (AI 分析中):
            1. 本案屬於「{tender_name}」相關採購。
            2. 官方資料庫偵測到此案位於政府電子採購網。
            3. AI 建議重點：請確認廠商資格是否具備相關專業證明文件。
            
            *(註：若要更精準的 AI 摘要，可在此串接 ChatGPT API 將上述原始文字進行總結)*
            """
            return summary
        except Exception as e:
            return f"讀取官方資料時出錯: {e}"

# --- 3. 網頁介面 (其餘搜尋邏輯維持不變) ---
st.title("🚀 標案 AI 自動化搜尋與分析系統")

# ... (中間的搜尋與列表顯示代碼與之前相同) ...

if st.session_state.df is not None:
    df = st.session_state.df
    st.dataframe(df)

    st.markdown("---")
    st.subheader("🧠 AI 深度商機分析")
    
    selected_tender = st.selectbox("請選擇想深入了解的標案:", options=df['內容'].tolist())
    
    if st.button("執行 AI 全網搜集與整理"):
        with st.spinner(f'AI 正在網路上搜尋「{selected_tender}」的官方詳細資料...'):
            # 執行非同步搜集
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            analysis_result = loop.run_until_complete(ai_gather_and_summarize(selected_tender))
            
            # 顯示結果
            st.markdown(analysis_result)

    # --- LINE 發送 ---
    # ... (原本的 LINE 發送代碼) ...
