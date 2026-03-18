import streamlit as st
import httpx
import pandas as pd
import re
import asyncio
from bs4 import BeautifulSoup

# --- 核心搜尋邏輯 ---
async def search_keyword_async(keyword):
    url = "https://www.taiwanbuying.com.tw/Query_KeywordAction.ASP"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
    }
    
    data = {"txtKeyword": keyword, "keyword": keyword}
    
    async with httpx.AsyncClient() as client:
        try:
            # 發送請求
            resp = await client.post(url, data=data, headers=headers, timeout=15.0)
            
            # 【UTF-8 解碼】：解決問號亂碼
            resp.encoding = 'utf-8'
            
            # 使用 BeautifulSoup 解析 HTML
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            results =[]
            # 標案通常在 <li> 或 <tr> 裡面
            blocks = soup.find_all(['tr', 'li'])
            
            # 正規表達式：抓取 "1. 機關:名稱 (日期)"
            pattern = re.compile(r'(\d+)\.?\s*(.*?)\s*\((.*?)\)')
            
            for block in blocks:
                # 取得乾淨的文字，並把多餘的換行空白拿掉
                text = block.get_text(separator=" ").strip()
                
                # 過濾：必須包含年份(202)，過濾掉版權宣告，且長度必須在 10 到 300 字之間
                if "202" in text and "Copyright" not in text and 10 < len(text) < 300:
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
            st.error(f"搜尋 '{keyword}' 時發生連線錯誤: {e}")
            return[]

# --- 網頁介面與狀態管理 ---
st.set_page_config(page_title="標案搜尋系統", layout="wide")
st.title("🚀 標案自動化搜尋系統")

# 初始化 Session State，用來記憶搜尋結果，防止畫面刷新資料不見
if "df" not in st.session_state:
    st.session_state.df = None

keywords_input = st.text_area("請輸入關鍵字 (一行一個):", value="文物\n整飭\n書畫", height=150)

# --- 搜尋區塊 ---
if st.button("開始搜尋"):
    keywords =[k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("請至少輸入一個關鍵字！")
    else:
        with st.spinner('正在從伺服器抓取資料，請稍候...'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            all_data =[]
            for kw in keywords:
                # 【修正】：這裡改為 loop.run_until_complete
                data = loop.run_until_complete(search_keyword_async(kw))
                all_data.extend(data)
                
        if all_data:
            df = pd.DataFrame(all_data)
            
            # 【關鍵修改】：將日期字串轉換為真正的日期格式，方便排序
            # 我們先用正規表達式提取日期部分（避免“更新”等字眼干擾）
            df['日期_tmp'] = pd.to_datetime(df['日期'].str.extract(r'(\d{4}/\d{1,2}/\d{1,2})')[0], errors='coerce')
            
            # 依照日期排序：ascending=False 代表由新到舊
            df = df.sort_values(by='日期_tmp', ascending=False)
            
            # 去除重複（保留日期最新的那一筆）
            df = df.drop_duplicates(subset=['內容'], keep='first')
            
            # 重新編排序號 (1, 2, 3...)
            df = df.reset_index(drop=True)
            df['序號'] = df.index + 1
            
            # 移除暫時的日期排序欄位，保持畫面乾淨
            df = df.drop(columns=['日期_tmp'])
            
            # 將結果存入暫存
            st.session_state.df = df

# --- 結果顯示與 LINE 發送區塊 ---
# 只要暫存裡面有資料，就把結果跟 LINE 按鈕顯示出來
if st.session_state.df is not None and not st.session_state.df.empty:
    df = st.session_state.df
    
    st.success(f"🎉 搜尋完成！共找到 {len(df)} 筆不重複資料。")
    st.dataframe(df)
    
    # 提供 CSV 下載
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下載結果 (CSV)",
        data=csv,
        file_name="標案總匯總.csv",
        mime="text/csv"
    )
    
    # --- LINE Messaging API 推播邏輯 ---
    st.markdown("---")
    st.subheader("🤖 一鍵發送至 LINE 機器人")
    
    if st.button("🚀 傳送標案結果到我的 LINE"):
        try:
            # 從 Streamlit 保險箱自動讀取金鑰
            line_token = st.secrets["LINE_TOKEN"]
            user_id = st.secrets["USER_ID"]
            
            # 1. 整理訊息內容 (取前 15 筆避免洗版)
            msg = f"\n🔍 標案搜尋結果 (共 {len(df)} 筆)：\n"
            msg += "-" * 20 + "\n"
            
            for index, row in df.head(15).iterrows():
                msg += f"📌 {row['內容']}\n📅 {row['日期']} | 🔑 {row['關鍵字']}\n\n"
            
            if len(df) > 15:
                msg += f"...等其他 {len(df)-15} 筆，請至系統查看完整清單。"

            # 2. 呼叫 LINE Messaging API
            url = "https://api.line.me/v2/bot/message/push"
            headers = {
                "Authorization": f"Bearer {line_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "to": user_id,
                "messages":[
                    {
                        "type": "text",
                        "text": msg
                    }
                ]
            }
            
            # 發送請求
            with httpx.Client() as client:
                r = client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    st.success("✅ 成功發送到 LINE 囉！請檢查你的手機。")
                    st.balloons()
                else:
                    st.error(f"❌ 發送失敗！錯誤碼: {r.status_code}")
                    st.write(r.text)
        except KeyError:
            st.error("❌ 找不到金鑰！請確定你有在 Streamlit Secrets 裡面設定 LINE_TOKEN 和 USER_ID。")
        except Exception as e:
            st.error(f"發生錯誤: {e}")
