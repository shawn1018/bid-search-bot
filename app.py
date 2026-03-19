import streamlit as st
import httpx
import pandas as pd
import re
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import google.generativeai as genai

# --- 1. 配置 Gemini AI ---
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.sidebar.error(f"AI 配置失敗: {e}")

# --- 2. 自動同步關鍵字邏輯 ---
def get_initial_keywords_from_file():
    try:
        with open("keywords.txt", "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else "文物\n整飭\n書畫"
    except:
        return "文物\n整飭\n書畫"

# --- 3. 同步版：搜尋官方連結與 AI 摘要 ---
def ai_analyze_tender_sync(tender_name):
    try:
        # 搜尋官方網址
        official_url = None
        with DDGS() as ddgs:
            query = f"{tender_name} site:web.pcc.gov.tw"
            results = list(ddgs.text(query, max_results=3))
            if results:
                official_url = results[0]['href']
        
        if not official_url:
            return f"❌ 無法找到「{tender_name}」的官方公開網頁。"

        # 抓取內容 (同步模式)
        headers = {"User-Agent": "Mozilla/5.0"}
        with httpx.Client() as client:
            resp = client.get(official_url, headers=headers, timeout=15.0)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            raw_text = soup.get_text(separator=" ", strip=True)
            
            prompt = f"""
            你是一位專業的政府標案分析官。請為我摘要以下內容：
            標案名稱：{tender_name}
            原始內容：{raw_text[:4000]}
            摘要要求：1.預算金額 2.截標時間 3.資格要求 4.工作重點 5.AI建議。
            使用繁體中文 Markdown。
            """
            response = model.generate_content(prompt)
            return f"🔗 **官方來源**: [點我開啟]({official_url})\n\n" + response.text
    except Exception as e:
        return f"AI 處理時出錯: {e}"

# --- 4. 同步版：核心標案列表搜尋邏輯 ---
def search_keyword_sync(keyword):
    url = "https://www.taiwanbuying.com.tw/Query_KeywordAction.ASP"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
    }
    data = {"txtKeyword": keyword, "keyword": keyword}
    
    with httpx.Client() as client:
        try:
            resp = client.post(url, data=data, headers=headers, timeout=15.0)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            blocks = soup.find_all(['tr', 'li'])
            pattern = re.compile(r'(\d+)\.?\s*(.*?)\s*\((.*?)\)')
            
            for block in blocks:
                text = block.get_text(separator=" ").strip()
                if re.search(r'\d{4}/\d{1,2}/\d{1,2}', text) and "Copyright" not in text and 10 < len(text) < 300:
                    match = pattern.search(text)
                    if match:
                        results.append({
                            '序號': match.group(1),
                            '內容': match.group(2).strip(),
                            '日期': match.group(3).strip(),
                            '關鍵字': keyword
                        })
            return results
        except Exception as e:
            st.error(f"搜尋 '{keyword}' 錯誤: {e}")
            return []

# --- 5. Streamlit 網頁介面 ---
st.set_page_config(page_title="標案 AI 搜尋系統", layout="wide")
st.title("🚀 標案 AI 自動化搜尋與智慧分析")

if "df" not in st.session_state:
    st.session_state.df = None

# 初始化關鍵字
init_kw = get_initial_keywords_from_file()
keywords_input = st.text_area("請輸入關鍵字 (一行一個):", value=init_kw, height=150)

# --- 按鈕：開始搜尋 ---
if st.button("🔍 開始搜尋並同步"):
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    if keywords:
        with st.spinner('正在從伺服器抓取資料...'):
            all_data = []
            for kw in keywords:
                # 直接呼叫同步函數，不再需要 loop 或 await
                data = search_keyword_sync(kw)
                all_data.extend(data)
                
        if all_data:
            df = pd.DataFrame(all_data)
            df['日期_tmp'] = pd.to_datetime(df['日期'].str.extract(r'(\d{4}/\d{1,2}/\d{1,2})')[0], errors='coerce')
            df = df.sort_values(by='日期_tmp', ascending=False)
            df = df.drop_duplicates(subset=['內容']).reset_index(drop=True)
            df['序號'] = df.index + 1
            df = df.drop(columns=['日期_tmp'])
            st.session_state.df = df
        else:
            st.session_state.df = None
            st.error("找不到符合條件的標案。")

# --- 顯示結果與分析 ---
if st.session_state.df is not None and not st.session_state.df.empty:
    df = st.session_state.df
    st.success(f"🎉 找到 {len(df)} 筆不重複標案。")
    st.dataframe(df, use_container_width=True)

    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 下載總匯總 (CSV)", csv, "標案匯總.csv", "text/csv")

    st.markdown("---")
    st.subheader("🧠 Gemini AI 標案智慧分析官")
    selected_tender = st.selectbox("選擇要分析的標案:", options=df['內容'].tolist())
    
    if st.button("🚀 啟動 AI 全網搜尋與內容摘要"):
        with st.spinner('AI 正在搜尋官網並分析中...'):
            # 同樣改為同步呼叫
            analysis = ai_analyze_tender_sync(selected_tender)
            st.markdown(analysis)

    st.markdown("---")
    st.subheader("🤖 LINE 群組一鍵推播")
    if st.button("🚀 傳送當前清單到 LINE 群組"):
        try:
            line_token = st.secrets["LINE_TOKEN"]
            user_id = st.secrets["USER_ID"]
            msg = f"\n🔍 標案搜尋結果 (共 {len(df)} 筆)：\n" + "-"*15 + "\n"
            for _, row in df.head(15).iterrows():
                msg += f"📌 {row['內容']}\n📅 {row['日期']} | 🔑 {row['關鍵字']}\n\n"
            
            payload = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
            headers = {"Authorization": f"Bearer {line_token}", "Content-Type": "application/json"}
            
            # 使用同步的 httpx 傳送 LINE
            with httpx.Client() as client:
                r = client.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
                if r.status_code == 200:
                    st.success("✅ 已傳送至 LINE 群組！")
                    st.balloons()
        except:
            st.error("請檢查 Streamlit Secrets 中的 LINE 設定。")
