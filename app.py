import streamlit as st
import pandas as pd
import httpx
import re
from bs4 import BeautifulSoup
import google.generativeai as genai

# --- 1. 配置 Gemini AI (2026 最新版: Gemini 2.5 Flash) ---
model = None

try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        
        # 使用 2026 年最新的 gemini-2.5-flash 模型
        # 啟用最新版 google_search 引擎連動功能
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            tools=[{"google_search": {}}] 
        )
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

# --- 3. AI 智慧分析函數 ---
def ai_analyze_tender_with_google_search(tender_name):
    if model is None:
        return "❌ AI 模型尚未初始化，請檢查 Secrets 設定。"

    # 清理標案名稱，增加搜尋命中率
    clean_name = tender_name.split(":")[-1].split("：")[-1].strip()

    prompt = f"""
    請使用 Google 搜尋引擎詳細搜尋並專業分析以下台灣政府標案：
    標案名稱：「{tender_name}」
    
    請利用你的 Grounding 能力，為我整理出該標案最精確的內容：
    1. **預算金額** (請務必查出具體新台幣金額，若為 0 或未公開請說明)
    2. **截標與開標日期時間**
    3. **標案案號**
    4. **案件背景與詳細脈絡** (包含相關新聞報導、捐贈資訊或機關歷史)
    5. **廠商投標資格關鍵要求** (例如專業證照、實績要求)
    6. **標案工作核心重點 (詳細 3-5 點條列)**
    7. **AI 商業評估建議** (包含投標風險、競爭強度預測或商機價值)
    
    請使用『繁體中文』，以專業且美觀的 Markdown 格式回覆。
    """
    
    try:
        # 執行 2.5 Flash 世代生成
        response = model.generate_content(prompt)
        
        # 提取 Google 搜尋來源
        source_info = ""
        try:
            if hasattr(response.candidates[0], 'grounding_metadata'):
                metadata = response.candidates[0].grounding_metadata
                if hasattr(metadata, 'search_entry_point') and metadata.search_entry_point:
                    source_info = "\n\n--- \n📚 **資料參考來源 (Google Search)：**\n" + metadata.search_entry_point.rendered_content
        except:
            pass
            
        return response.text + source_info
    except Exception as e:
        return f"AI 搜尋分析時發生錯誤: {e}\n(可能原因：模型權限限制或 Google Search API 呼叫額度問題)"

# --- 4. 標案清單抓取邏輯 (同步穩定版) ---
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

# --- 5. Streamlit 網頁介面 ---
st.set_page_config(page_title="標案 AI 搜尋系統 v2.5", layout="wide")
st.title("🚀 標案 AI 搜尋與 Google 2.5 實時分析")

if "df" not in st.session_state:
    st.session_state.df = None

# 初始化關鍵字 (自動與 GitHub keywords.txt 同步)
init_kw = get_initial_keywords_from_file()
keywords_input = st.text_area("🔧 管理關鍵字 (修改後請按開始搜尋):", value=init_kw, height=150)

if st.button("🔍 開始搜尋並同步清單"):
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    if keywords:
        with st.spinner('📡 正在從伺服器抓取最新標案清單...'):
            all_data = []
            for kw in keywords:
                data = search_keyword_sync(kw)
                all_data.extend(data)
        if all_data:
            df = pd.DataFrame(all_data)
            # 依日期最新往舊排序
            df['日期_tmp'] = pd.to_datetime(df['日期'].str.extract(r'(\d{4}/\d{1,2}/\d{1,2})')[0], errors='coerce')
            df = df.sort_values(by='日期_tmp', ascending=False)
            df = df.drop_duplicates(subset=['內容']).reset_index(drop=True)
            df['序號'] = df.index + 1
            df = df.drop(columns=['日期_tmp'])
            st.session_state.df = df
        else:
            st.session_state.df = None
            st.error("找不到符合條件的標案。")

# --- 6. 顯示結果與 AI 分析功能 ---
if st.session_state.df is not None:
    df = st.session_state.df
    st.success(f"✅ 找到 {len(df)} 筆標案。")
    st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("🧠 Gemini 2.5 × Google 實時深度分析")
    st.write("利用最新 2.5 Flash 模型連動 Google 搜尋，查出標案背景與預算。")
    selected_tender = st.selectbox("請選擇想分析的標案:", options=df['內容'].tolist())
    
    if st.button("🚀 執行 AI 深度分析 (含全網預算查詢)"):
        with st.spinner('Gemini 2.5 正在調用 Google 搜尋引擎分析中...'):
            analysis = ai_analyze_tender_with_google_search(selected_tender)
            st.markdown(analysis)

    st.markdown("---")
    st.subheader("🤖 LINE 群組一鍵推播")
    if st.button("🚀 傳送清單到 LINE 群組"):
        try:
            line_token = st.secrets["LINE_TOKEN"]
            user_id = st.secrets["USER_ID"]
            msg = f"\n🔍 標案搜尋結果 (共 {len(df)} 筆)：\n" + "-"*15 + "\n"
            # 發送前 15 筆避免 LINE 訊息過長
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
            st.error("❌ 金鑰設定錯誤，請檢查 Streamlit Secrets。")
