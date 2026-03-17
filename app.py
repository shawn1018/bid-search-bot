import streamlit as st
import asyncio
import pandas as pd
import re
import subprocess
import nest_asyncio

# 1. 確保雲端環境安裝 Playwright 瀏覽器
try:
    subprocess.run(["playwright", "install", "chromium"], check=True)
    subprocess.run(["playwright", "install-deps", "chromium"], check=True)
except Exception as e:
    st.error(f"瀏覽器安裝失敗: {e}")

# 2. 環境設定
nest_asyncio.apply()
from playwright.async_api import async_playwright

# --- 爬蟲邏輯 ---
async def search_keyword(page, keyword):
    try:
        await page.goto("https://www.taiwanbuying.com.tw/Query_Keyword.ASP")
        await page.fill('input[name="keyword"], input[name="txtKeyword"]', keyword)
        await page.click('input[type="submit"], input[name="Submit"]')
        await asyncio.sleep(6) # 給網頁時間載入
        
        full_text = await page.inner_text("body")
        lines = full_text.split('\n')
        
        results = []
        # 正規表達式：抓取 序號. 內容 (日期)
        pattern = re.compile(r'^(\d+)[.\s]*(.*?)\s*\((.*?)\)')
        
        for line in lines:
            line = line.strip()
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
        st.error(f"搜尋 {keyword} 時發生錯誤: {e}")
        return []

# --- Streamlit 網頁介面 ---
st.set_page_config(page_title="標案搜尋系統", layout="wide")
st.title("🚀 標案自動化搜尋系統")

# 關鍵字輸入
keywords_input = st.text_area("請輸入關鍵字 (一行一個):", height=150, value="文物")

if st.button("開始搜尋"):
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("請至少輸入一個關鍵字！")
    else:
        all_data = []
        progress = st.progress(0)
        
        async def run_all():
            async with async_playwright() as p:
                # 雲端必須使用 headless 模式
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                for i, kw in enumerate(keywords):
                    data = await search_keyword(page, kw)
                    all_data.extend(data)
                    progress.progress((i + 1) / len(keywords))
                await browser.close()
        
        # 執行爬蟲
        with st.spinner('正在從網站抓取資料，請稍候...'):
            asyncio.run(run_all())
        
        # 整理並顯示資料
        if all_data:
            df = pd.DataFrame(all_data)
            df = df.drop_duplicates(subset=['內容'], keep='first')
            df = df.reset_index(drop=True)
            df['序號'] = df.index + 1
            
            st.success(f"搜尋完成！共找到 {len(df)} 筆不重複資料。")
            st.dataframe(df)
            
            # Excel 下載按鈕
            towrite = pd.io.excel.ExcelWriter('標案總匯總.xlsx', engine='xlsxwriter')
            df.to_excel(towrite, index=False)
            towrite.close()
            with open('標案總匯總.xlsx', 'rb') as f:
                st.download_button("下載結果 Excel", f, "標案總匯總.xlsx")
        else:
            st.error("沒有抓到資料，請確認網頁是否正常回應。")
