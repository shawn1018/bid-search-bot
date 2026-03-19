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
        model = genai.GenerativeModel('gemini-2.5-flash')
    else:
        st.sidebar.warning("⚠️ 未設定 GEMINI_API_KEY")
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

# --- 3. 搜尋官方連結函數 ---
def find_official_url(tender_name):
    """優化過的搜尋邏輯：嚴格確保只抓取 pcc.gov.tw 的網址"""
    try:
        # 去掉機關名稱，只留純案名
        clean_name = tender_name
        if ":" in tender_name:
            clean_name = tender_name.split(":", 1)[1]
        elif "：" in tender_name:
            clean_name = tender_name.split("：", 1)[1]
        
        # 清除特殊符號
        clean_name = re.sub(r'[^\w\u4e00-\u9fa5]', ' ', clean_name).strip()
        
        with DDGS() as ddgs:
            # 策略：搜尋標案名稱並鎖定官網網域
            query = f'{clean_name} site:web.pcc.gov.tw'
            results = list(ddgs.text(query, max_results=5))
            
            if results:
                for r in results:
                    if "pcc.gov.tw" in r.get('href', ''):
                        return r['href']
    except:
        pass
    return None

# --- 4. AI 全網情報抓取與摘要分析 ---
def ai_analyze_tender_sync(tender_name):
    # (A) 先去全網搜集「新聞與第三方網站摘要」(RAG 模式)
    web_snippets = ""
    try:
        # 去掉機關名稱搜全網
        clean_name = tender_name.split(":")[-1].split("：")[-1].strip()
        with DDGS() as ddgs:
            # 搜尋全網，包含民間採購網或新聞，這能提供預算等背景
            search_results = list(ddgs.text(clean_name, max_results=5))
            for r in search_results:
                web_snippets += f"來源: {r.get('title', '')}\n摘要: {r.get('body', '')}\n\n"
    except:
        web_snippets = "無網路即時情報"

    # (B) 嘗試抓取「官方網頁內容」
    official_url = find_official_url(tender_name)
    raw_text = ""
    if official_url:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            with httpx.Client() as client:
                resp = client.get(official_url, headers=headers, timeout=15.0)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'html.parser')
                raw_text = soup.get_text(separator=" ", strip=True)[:4000] # 截取前4000字
        except:
            raw_text = "官方網頁抓取失敗"

    # (C) 將所有資料餵給 Gemini 分析
    prompt = f"""
    你是一位專業的政府標案分析官。我為你搜集了關於標案「{tender_name}」的網路情報摘要與官方內容：
    
    【全網搜尋情報摘要】：
    {web_snippets}
    
    【官方網頁內容】：
    {raw_text if raw_text else "搜尋引擎尚未收錄官方詳細網頁"}
    
    請綜合以上資料，為我整理出此標案的重點：
    1. **預算金額** (若資料中有提到)
    2. **截標與開標時間**
    3. **案件背景與脈絡** (若有相關新聞背景，如捐款等)
    4. **廠商投標資格關鍵要求**
    5. **標案工作重點 (3點條列)**
    6. **AI 建議 (投標風險或商機評估)**
    
    請使用繁體中文，Markdown 格式回覆。
    """
    
    try:
        response = model.generate_content(prompt)
        prefix = f"🔗 **官方來源連結**:[點我開啟官網]({official_url})\n\n" if official_url else "⚠️ **提示：目前主要依賴全網第三方資料進行 AI 綜合分析。**\n\n"
        return prefix + response.text
    except Exception as e:
        return f"AI 處理時出錯: {e}"

# --- 5. 核心標案列表搜尋邏輯 ---
def search_keyword_sync(keyword):
    url = "https://www.taiwanbuying.com.tw/Query_KeywordAction.ASP"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
    }
    data = {"txtKeyword": keyword, "keyword": keyword}
    try:
        with httpx.Client() as client:
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
    except:
        return []

# --- 6. Streamlit 網頁介面 ---
st.set_page_config(page_title="標案 AI 搜尋系統", layout="wide")
st.title("🚀 標案 AI 自動化搜尋與智慧分析")

if "df" not in st.session_state:
    st.session_state.df = None

# 初始化關鍵字
init_kw = get_initial_keywords_from_file()
keywords_input = st.text_area("請輸入關鍵字 (一行一個):", value=init_kw, height=150)

if st.button("🔍 開始搜尋並同步"):
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    if keywords:
        with st.spinner('正在抓取最新資料...'):
            all_data = []
            for kw in keywords:
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
if st.session_state.df is not None:
    df = st.session_state.df
    st.success(f"🎉 找到 {len(df)} 筆標案。")
    st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("🧠 Gemini AI 全網情報分析")
    selected_tender = st.selectbox("選擇想深入分析的標案:", options=df['內容'].tolist())
    
    if st.button("🚀 啟動 AI 全網情報分析"):
        with st.spinner('AI 正在翻閱全網新聞與官網內容...'):
            analysis = ai_analyze_tender_sync(selected_tender)
            st.markdown(analysis)

    st.markdown("---")
    st.subheader("🤖 LINE 推播")
    if st.button("🚀 傳送清單到 LINE 群組"):
        try:
            line_token = st.secrets["LINE_TOKEN"]
            user_id = st.secrets["USER_ID"]
            msg = f"\n🔍 標案搜尋結果 (共 {len(df)} 筆)：\n" + "-"*15 + "\n"
            for _, row in df.head(15).iterrows():
                msg += f"📌 {row['內容']}\n📅 {row['日期']} | 🔑 {row['關鍵字']}\n\n"
            
            payload = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
            headers = {"Authorization": f"Bearer {line_token}", "Content-Type": "application/json"}
            with httpx.Client() as client:
                r = client.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
                if r.status_code == 200:
                    st.success("✅ 已傳送至 LINE")
                    st.balloons()
                else:
                    st.error(f"發送失敗: {r.text}")
        except:
            st.error("金鑰設定錯誤。")
