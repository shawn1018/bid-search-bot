import streamlit as st
import httpx
import pandas as pd
import re
import asyncio
import nest_asyncio
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import google.generativeai as genai

# 初始化非同步環境
nest_asyncio.apply()

# --- 1. 配置 Gemini AI ---
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        st.sidebar.warning("⚠️ 未設定 GEMINI_API_KEY，AI 分析功能將無法使用。")
except Exception as e:
    st.sidebar.error(f"AI 配置失敗: {e}")

# --- 2. 自動同步關鍵字邏輯 ---
def get_initial_keywords_from_file():
    filename = "keywords.txt"
    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else "文物\n整飭\n書畫"
    except:
        return "文物\n整飭\n書畫"

# --- 3. 搜尋官方連結與 AI 摘要邏輯 ---
def find_official_url(tender_name):
    """利用 DuckDuckGo 搜尋政府電子採購網的原始網址"""
    try:
        with DDGS() as ddgs:
            # 鎖定政府官方網域：web.pcc.gov.tw
            query = f"{tender_name} site:web.pcc.gov.tw"
            results = list(ddgs.text(query, max_results=3))
            if results:
                return results[0]['href']
    except:
        return None

async def ai_analyze_tender(tender_name):
    """搜尋官網、抓取資料並由 AI 摘要"""
    official_url = find_official_url(tender_name)
    if not official_url:
        return f"❌ 無法在全網找到「{tender_name}」的官方公開網頁。建議手動至政府電子採購網查詢。"

    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(official_url, headers=headers, timeout=15.0)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 抓取官方網頁文字
            raw_text = soup.get_text(separator=" ", strip=True)
            
            prompt = f"""
            你是一位專業的政府標案分析官。請閱讀以下來自『政府電子採購網』的公開資訊，為我整理標案重點：
            標案名稱：{tender_name}
            原始內容：{raw_text[:4000]}
            
            請依序摘要：
            1. **預算金額** (若有提到)
            2. **截標日期與時間**
            3. **廠商投標資格關鍵要求**
            4. **標案工作重點 (3點條列)**
            5. **AI 建議 (投標風險或機會)**
            使用繁體中文，Markdown 格式。
            """
            response = model.generate_content(prompt)
            return f"🔗 **官方來源連結**: [點我開啟官網]({official_url})\n\n" + response.text
        except Exception as e:
            return f"AI 處理時出錯: {e}"

# --- 4. 核心標案列表搜尋邏輯 ---
async def search_keyword_async(keyword):
    url = "https://www.taiwanbuying.com.tw/Query_KeywordAction.ASP"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
    }
    data = {"txtKeyword": keyword, "keyword": keyword}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, data=data, headers=headers, timeout=15.0)
            resp.encoding = 'utf-8' # 使用 UTF-8 解碼
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            blocks = soup.find_all(['tr', 'li'])
            pattern = re.compile(r'(\d+)\.?\s*(.*?)\s*\((.*?)\)')
            
            for block in blocks:
                text = block.get_text(separator=" ").strip()
                # 篩選包含日期的行
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
            st.error(f"搜尋 '{keyword}' 發生連線錯誤: {e}")
            return []

# --- 5. Streamlit 網頁介面 ---
st.set_page_config(page_title="標案 AI 搜尋系統", layout="wide")
st.title("🚀 標案 AI 自動化搜尋與智慧分析")

if "df" not in st.session_state:
    st.session_state.df = None

# 初始化關鍵字 (同步 GitHub keywords.txt)
init_kw = get_initial_keywords_from_file()
keywords_input = st.text_area("請輸入關鍵字 (一行一個):", value=init_kw, height=150)

# --- 按鈕：開始搜尋 ---
if st.button("🔍 開始搜尋並同步"):
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    if keywords:
        with st.spinner('正在從伺服器抓取資料，請稍候...'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            all_data = []
            for kw in keywords:
                data = loop.run_until_complete(search_keyword_async(kw))
                all_data.extend(data)
                
        if all_data:
            df = pd.DataFrame(all_data)
            # 日期排序 (最新往舊)
            df['日期_tmp'] = pd.to_datetime(df['日期'].str.extract(r'(\d{4}/\d{1,2}/\d{1,2})')[0], errors='coerce')
            df = df.sort_values(by='日期_tmp', ascending=False)
            df = df.drop_duplicates(subset=['內容']).reset_index(drop=True)
            df['序號'] = df.index + 1
            df = df.drop(columns=['日期_tmp'])
            st.session_state.df = df
        else:
            st.session_state.df = None
            st.error("找不到符合條件的標案。")

# --- 顯示結果與 AI 分析功能 ---
if st.session_state.df is not None and not st.session_state.df.empty:
    df = st.session_state.df
    st.success(f"🎉 找到 {len(df)} 筆不重複標案 (已按日期排序)。")
    st.dataframe(df, use_container_width=True)

    # 下載按鈕
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 下載總匯總 (CSV)", csv, "標案匯總.csv", "text/csv")

    st.markdown("---")
    
    # AI 智慧分析區
    st.subheader("🧠 Gemini AI 標案智慧分析官")
    selected_tender = st.selectbox("請選擇想讓 AI 深度分析的標案:", options=df['內容'].tolist())
    
    if st.button("🚀 啟動 AI 全網搜尋與內容摘要"):
        with st.spinner(f'AI 正在為您搜尋官網並讀取內容...'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            analysis = loop.run_until_complete(ai_analyze_tender(selected_tender))
            st.markdown(analysis)

    st.markdown("---")
    
    # LINE 推播區
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
            
            with httpx.Client() as client:
                r = client.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
                if r.status_code == 200:
                    st.success("✅ 已傳送至 LINE 群組！")
                    st.balloons()
                else:
                    st.error(f"發送失敗: {r.text}")
        except:
            st.error("請檢查 Streamlit Secrets 中的 LINE 設定。")
