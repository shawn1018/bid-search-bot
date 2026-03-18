import streamlit as st
import httpx
import pandas as pd
import re
import asyncio
from bs4 import BeautifulSoup

# --- 1. 自動讀取關鍵字檔案邏輯 ---
def get_initial_keywords_from_file():
    filename = "keywords.txt"
    try:
        # 優先嘗試 UTF-8
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else "文物\n整飭\n書畫"
    except UnicodeDecodeError:
        # 如果失敗，嘗試 Big5
        try:
            with open(filename, "r", encoding="big5") as f:
                content = f.read().strip()
                return content if content else "文物\n整飭\n書畫"
        except:
            return "文物\n整飭\n書畫"
    except FileNotFoundError:
        # 如果檔案不存在，使用預設值
        return "文物\n整飭\n書畫"

# --- 2. 核心搜尋邏輯 ---
async def search_keyword_async(keyword):
    url = "https://www.taiwanbuying.com.tw/Query_KeywordAction.ASP"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
    }
    data = {"txtKeyword": keyword, "keyword": keyword}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, data=data, headers=headers, timeout=15.0)
            resp.encoding = 'utf-8' # 網站使用 UTF-8
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

# --- 3. 網頁介面設定 ---
st.set_page_config(page_title="標案搜尋系統", layout="wide")
st.title("🚀 標案自動化搜尋系統")

# 初始化 Session State (記憶搜尋結果)
if "df" not in st.session_state:
    st.session_state.df = None

# 【同步關鍵】：從檔案讀取初始關鍵字，放入文字區塊的預設值
init_val = get_initial_keywords_from_file()
keywords_input = st.text_area("請輸入關鍵字 (一行一個):", value=init_val, height=150)

# --- 4. 搜尋動作 ---
if st.button("開始搜尋"):
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("請至少輸入一個關鍵字！")
    else:
        with st.spinner('正在從伺服器抓取資料，請稍候...'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            all_data = []
            for kw in keywords:
                # 修正 loop 調用筆誤
                data = loop.run_until_complete(search_keyword_async(kw))
                all_data.extend(data)
                
        if all_data:
            df = pd.DataFrame(all_data)
            
            # 【排序邏輯】：將日期轉換為時間物件，由新到舊排
            df['日期_tmp'] = pd.to_datetime(df['日期'].str.extract(r'(\d{4}/\d{1,2}/\d{1,2})')[0], errors='coerce')
            df = df.sort_values(by='日期_tmp', ascending=False)
            
            # 去除重複
            df = df.drop_duplicates(subset=['內容'], keep='first')
            df = df.reset_index(drop=True)
            df['序號'] = df.index + 1
            df = df.drop(columns=['日期_tmp']) # 移除暫時排序欄位
            
            st.session_state.df = df
        else:
            st.session_state.df = pd.DataFrame()
            st.error("沒有抓到符合格式的資料，請檢查關鍵字。")

# --- 5. 結果顯示與 LINE 發送 ---
if st.session_state.df is not None and not st.session_state.df.empty:
    df = st.session_state.df
    st.success(f"🎉 搜尋完成！共找到 {len(df)} 筆不重複資料 (依日期由新到舊排序)。")
    st.dataframe(df)
    
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 下載結果 (CSV)", csv, "標案總匯總.csv", "text/csv")
    
    st.markdown("---")
    st.subheader("🤖 一鍵發送至 LINE 機器人 (群組)")
    
    if st.button("🚀 傳送標案結果到我的 LINE"):
        try:
            # 從 Streamlit Secrets 讀取金鑰
            line_token = st.secrets["LINE_TOKEN"]
            user_id = st.secrets["USER_ID"] # 這裡是你的 Group ID
            
            msg = f"\n🔍 標案搜尋結果 (共 {len(df)} 筆)：\n"
            msg += "-" * 20 + "\n"
            for index, row in df.head(15).iterrows():
                msg += f"📌 {row['內容']}\n📅 {row['日期']} | 🔑 {row['關鍵字']}\n\n"
            
            if len(df) > 15:
                msg += f"...等其他 {len(df)-15} 筆，請至系統查看。"

            url = "https://api.line.me/v2/bot/message/push"
            headers = {"Authorization": f"Bearer {line_token}", "Content-Type": "application/json"}
            payload = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
            
            with httpx.Client() as client:
                r = client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    st.success("✅ 成功發送到 LINE 群組囉！")
                    st.balloons()
                else:
                    st.error(f"❌ 發送失敗！錯誤碼: {r.status_code}\n{r.text}")
        except Exception as e:
            st.error(f"LINE 金鑰讀取失敗，請確認 Streamlit Secrets 設定。")
