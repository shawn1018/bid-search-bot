#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 17 14:25:16 2026

@author: shawn
"""
import os
import httpx
import pandas as pd
import re
import asyncio
from bs4 import BeautifulSoup

# --- 核心搜尋邏輯 (與網頁版相同) ---
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
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            results =[]
            blocks = soup.find_all(['tr', 'li'])
            pattern = re.compile(r'(\d+)\.?\s*(.*?)\s*\((.*?)\)')
            
            for block in blocks:
                text = block.get_text(separator=" ").strip()
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
            print(f"搜尋 '{keyword}' 發生錯誤: {e}")
            return[]

# --- 自動化主程式 ---
def main():
    print("啟動自動化標案搜尋機器人...")
    
    # 1. 讀取關鍵字 (從你原本的 keywords.txt)
    try:
        with open("keywords.txt", "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]
    except:
        print("找不到 keywords.txt，終止執行。")
        return

    # 2. 執行搜尋
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    all_data =[]
    for kw in keywords:
        print(f"正在搜尋: {kw}...")
        data = loop.run_until_complete(search_keyword_async(kw))
        all_data.extend(data)
        
    # 3. 整理與發送 LINE
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=['內容'], keep='first')
        
        # 【關鍵】：從 GitHub 的環境變數讀取金鑰
        line_token = os.environ.get("LINE_TOKEN")
        user_id = os.environ.get("USER_ID")
        
        if not line_token or not user_id:
            print("錯誤：找不到 LINE 金鑰，無法發送！")
            return
            
        msg = f"\n🤖 【每日自動推播】標案搜尋結果 (共 {len(df)} 筆)：\n"
        msg += "-" * 20 + "\n"
        for index, row in df.head(15).iterrows():
            msg += f"📌 {row['內容']}\n📅 {row['日期']} | 🔑 {row['關鍵字']}\n\n"
        if len(df) > 15:
            msg += f"...等其他 {len(df)-15} 筆，請至系統查看。"

        url = "https://api.line.me/v2/bot/message/push"
        headers = {"Authorization": f"Bearer {line_token}", "Content-Type": "application/json"}
        payload = {"to": user_id, "messages":[{"type": "text", "text": msg}]}
        
        with httpx.Client() as client:
            r = client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                print("✅ 成功發送 LINE 通知！")
            else:
                print(f"❌ LINE 發送失敗: {r.text}")
    else:
        print("今日無符合關鍵字的標案。")

if __name__ == "__main__":
    main()