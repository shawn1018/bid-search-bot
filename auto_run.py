import os
import httpx
import pandas as pd
import re
import asyncio
from bs4 import BeautifulSoup

# --- 1. 核心搜尋邏輯 (抓取單一關鍵字) ---
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
            
            results = []
            blocks = soup.find_all(['tr', 'li'])
            pattern = re.compile(r'(\d+)\.?\s*(.*?)\s*\((.*?)\)')
            
            for block in blocks:
                text = block.get_text(separator=" ").strip()
                if "202" in text and "Copyright" not in text and 10 < len(text) < 300:
                    match = pattern.search(text)
                    if match:
                        results.append({
                            '內容': match.group(2).strip(),
                            '日期': match.group(3).strip(),
                            '關鍵字': keyword
                        })
            return results
        except Exception as e:
            print(f"搜尋 '{keyword}' 發生錯誤: {e}")
            return []

# --- 2. 主程式 ---
def main():
    print("🚀 啟動自動化標案搜尋機器人...")
    
    # 讀取關鍵字檔案
    try:
        with open("keywords.txt", "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]
    except:
        print("❌ 找不到 keywords.txt")
        return

    # 【第一步：全部搜完】
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    all_raw_data = []
    for kw in keywords:
        print(f"正在搜尋關鍵字: {kw}")
        data = loop.run_until_complete(search_keyword_async(kw))
        all_raw_data.extend(data)
    
    # 【第二步：刪除重複與整理】
    if not all_raw_data:
        print("今日無符合資料。")
        return

    df = pd.DataFrame(all_raw_data)
    df = df.drop_duplicates(subset=['內容'], keep='first').reset_index(drop=True)
    total_bids = len(df)
    print(f"搜尋結束，共找到 {total_bids} 筆不重複標案。")

    # 【第三步：分批發送 LINE (這段必須在關鍵字迴圈外面)】
    line_token = os.environ.get("LINE_TOKEN")
    user_id = os.environ.get("USER_ID")
    
    if not line_token or not user_id:
        print("❌ 找不到 LINE 金鑰。")
        return

    # 每 15 筆分裝成一則訊息，避免字數過長
    batch_size = 15 
    for i in range(0, total_bids, batch_size):
        chunk = df.iloc[i:i+batch_size]
        
        msg = f"\n🔍 標案搜尋結果 ({i+1}~{min(i+batch_size, total_bids)} / 共 {total_bids} 筆)：\n"
        msg += "-" * 20 + "\n"
        
        for index, row in chunk.iterrows():
            msg += f"📌 {row['內容']}\n📅 {row['日期']} | 🔑 {row['關鍵字']}\n\n"

        # 發送當前這一批
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Authorization": f"Bearer {line_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": msg}]
        }
        
        with httpx.Client() as client:
            r = client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                print(f"✅ 成功發送第 {i+1} 批次")
            else:
                print(f"❌ 第 {i+1} 批次發送失敗: {r.text}")

if __name__ == "__main__":
    main()
