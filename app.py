#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 17 14:25:16 2026

@author: shawn
"""
import streamlit as st
import asyncio
import pandas as pd
import re
from playwright.async_api import async_playwright
import nest_asyncio

nest_asyncio.apply()

# --- 爬蟲邏輯 (跟之前一樣，但包裝給網頁使用) ---
async def search_keyword(page, keyword):
    await page.goto("https://www.taiwanbuying.com.tw/Query_Keyword.ASP")
    await page.fill('input[name="keyword"], input[name="txtKeyword"]', keyword)
    await page.click('input[type="submit"], input[name="Submit"]')
    await asyncio.sleep(5)
    
    full_text = await page.inner_text("body")
    lines = full_text.split('\n')
    
    results = []
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

# --- Streamlit 網頁介面 ---
st.title("🚀 標案自動化搜尋系統")
st.write("請在下方輸入關鍵字，每行一個。")

keywords_input = st.text_area("關鍵字輸入區 (例如: 文物, 整飭, 書畫)", height=150)

if st.button("開始搜尋"):
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("請至少輸入一個關鍵字！")
    else:
        all_data = []
        progress_bar = st.progress(0)
        
        async def run_all():
            async with async_playwright() as p:
                browser = await p.chromium.launch() # 雲端建議用 headless
                page = await browser.new_page()
                for i, kw in enumerate(keywords):
                    data = await search_keyword(page, kw)
                    all_data.extend(data)
                    progress_bar.progress((i + 1) / len(keywords))
                await browser.close()
        
        asyncio.run(run_all())
        
        if all_data:
            df = pd.DataFrame(all_data)
            df = df.drop_duplicates(subset=['內容'], keep='first')
            st.success(f"搜尋完成！共找到 {len(df)} 筆資料。")
            st.dataframe(df)
            
            # 提供 Excel 下載
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("下載結果 (CSV)", csv, "標案匯總.csv", "text/csv")
        else:
            st.error("沒有抓到資料，請確認關鍵字是否有誤。")