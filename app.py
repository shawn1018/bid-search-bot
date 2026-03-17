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
            
            # 【關鍵】：強制使用utf-8 解碼，解決所有的問號亂碼
            resp.encoding = 'utf-8'
            
            # 使用 BeautifulSoup 解析 HTML，把雜亂的標籤清掉
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            results =[]
            # 根據截圖，標案通常在 <li> 或 <tr> (表格行) 裡面
            # 我們同時抓取這兩種標籤
            blocks = soup.find_all(['tr', 'li'])
            
            # 正規表達式：抓取 "1. 機關:名稱 (日期)"
            pattern = re.compile(r'(\d+)\.?\s*(.*?)\s*\((.*?)\)')
            
            for block in blocks:
                # 取得乾淨的文字，並把多餘的換行空白拿掉
                text = block.get_text(separator=" ").strip()
                
                # 過濾：必須包含年份(202)，且不能是網站底部的版權宣告(Copyright)
                if "202" in text and "Copyright" not in text and len(text) > 10:
                    match = pattern.search(text)
                    if match:
                        results.append({
                            '序號': match.group(1),
                            '內容': match.group(2).strip(),
                            '日期': match.group(3).strip(),
                            '關鍵字': keyword
                        })
                    else:
                        # 如果格式長得不一樣但有日期，我們也強制保留下來以免漏掉
                        results.append({
                            '序號': '-',
                            '內容': text,
                            '日期': '格式需手動確認',
                            '關鍵字': keyword
                        })
                        
            return results
            
        except Exception as e:
            st.error(f"搜尋 '{keyword}' 時發生連線錯誤: {e}")
            return[]

# --- 網頁介面 ---
st.set_page_config(page_title="標案搜尋系統", layout="wide")
st.title("🚀 標案自動化搜尋系統")

keywords_input = st.text_area("請輸入關鍵字 (一行一個):", value="文物\n整飭\n書畫", height=150)

if st.button("開始搜尋"):
    keywords =[k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("請至少輸入一個關鍵字！")
    else:
        with st.spinner('正在從伺服器抓取資料，請稍候...'):
            # 執行非同步請求
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            all_data =[]
            for kw in keywords:
                data = loop.run_until_complete(search_keyword_async(kw))
                all_data.extend(data)
                
        # 顯示與匯出資料
        if all_data:
            df = pd.DataFrame(all_data)
            
            # 去除重複的標案 (根據內容欄位)
            df = df.drop_duplicates(subset=['內容'], keep='first')
            
            # 重新整理序號
            df = df.reset_index(drop=True)
            df['序號'] = df.index + 1
            
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
        else:
            st.error("沒有抓到符合格式的資料，請檢查關鍵字。")
