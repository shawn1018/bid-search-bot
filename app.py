import streamlit as st
import httpx
import pandas as pd
import re
import asyncio

# --- 核心搜尋邏輯 (無需瀏覽器) ---
async def search_keyword_async(keyword):
    url = "https://www.taiwanbuying.com.tw/Query_KeywordAction.ASP"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
    }
    
    # 這裡我們嘗試同時送出這兩個名稱，以免 ASP 網站挑剔欄位名稱
    data = {"txtKeyword": keyword, "keyword": keyword}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, data=data, headers=headers, timeout=10.0)
            resp.encoding = 'big5'
            
            # --- 關鍵偵錯 ---
            # 把它抓到的原始 HTML 片段印出來給你看
            st.write(f"搜尋 {keyword} 的結果原始碼前 500 字:")
            st.code(resp.text[:500]) 
            # ----------------
            
            # 嘗試用更寬鬆的方式解析 (不強求固定格式)
            lines = resp.text.split('\n')
            results = []
            for line in lines:
                line = line.strip()
                # 只要這行有日期，且長度夠長，就當作它是標案
                if "202" in line and len(line) > 10:
                    results.append({
                        '序號': '1', # 先暫時給固定值
                        '內容': line,
                        '日期': '請查看內容',
                        '關鍵字': keyword
                    })
            return results
        except Exception as e:
            st.error(f"請求錯誤: {e}")
            return []

# --- 網頁介面 ---
st.title("🚀 輕量化標案搜尋系統")
keywords_input = st.text_area("請輸入關鍵字:", value="文物")

if st.button("開始搜尋"):
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    with st.spinner('正在從伺服器抓取資料...'):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        all_data = []
        for kw in keywords:
            data = loop.run_until_complete(search_keyword_async(kw))
            all_data.extend(data)
            
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=['內容'])
        st.success(f"搜尋完成！找到 {len(df)} 筆。")
        st.dataframe(df)
        
        # 下載
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("下載結果 CSV", csv, "標案.csv")
    else:
        st.error("沒有抓到資料，請檢查關鍵字。")
