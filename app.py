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
        # ----------------
        
        # 為了除錯，我們可以把解碼後的文字先印出來檢查
        # st.code(resp.text[:500]) # 如果確認正常了，這行之後可以刪掉
        
        # 使用 BeautifulSoup 來解析 HTML (比單純 split 更穩健)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 根據你剛剛的截圖，內容被包在 <td> 標籤中
        # 我們抓取所有的 <td>
        results = []
        rows = soup.find_all('tr') # 標案通常是整行 row
        
        for row in rows:
            text = row.get_text().strip()
            if "202" in text and len(text) > 20: # 確保抓到的是有內容的標案行
                results.append({
                    '序號': '1', # 你可以寫一個邏輯抓出確切序號
                    '內容': text.replace('\n', ' '), # 把換行符號拿掉
                    '日期': '2026/3/17', # 這裡之後可以用 regex 抓取
                    '關鍵字': keyword
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
