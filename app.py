import streamlit as st
import httpx
import pandas as pd
import re
import asyncio

# --- 核心搜尋邏輯 (無需瀏覽器) ---
async def search_keyword_async(keyword):
    url = "https://www.taiwanbuying.com.tw/Query_KeywordAction.ASP"
    
    # 模擬瀏覽器行為的 Header
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.taiwanbuying.com.tw/Query_Keyword.ASP"
    }
    
    # 對應網站的表單欄位名稱
    data = {"txtKeyword": keyword}
    
    async with httpx.AsyncClient() as client:
        try:
            # 發送 POST 請求
            resp = await client.post(url, data=data, headers=headers, timeout=10.0)
            resp.encoding = 'big5'
            
            # 使用簡單的字串搜尋，不再依賴 HTML 結構渲染
            lines = resp.text.split('\n')
            results = []
            
            # Regex 解析
            pattern = re.compile(r'(\d+)[.\s]*(.*?)\s*\((.*?)\)')
            for line in lines:
                if "202" in line and len(line) > 10:
                    match = pattern.search(line)
                    if match:
                        results.append({
                            '序號': match.group(1),
                            '內容': match.group(2).strip(),
                            '日期': match.group(3).strip(),
                            '關鍵字': keyword
                        })
            return results
        except Exception as e:
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
