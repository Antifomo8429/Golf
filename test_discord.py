#!/usr/bin/env python3
"""
Discord Webhook 連線測試

用法：
  python test_discord.py <你的 Discord Webhook URL>

或設定環境變數後直接執行：
  export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
  python test_discord.py
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

def main():
    url = None
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.environ.get("DISCORD_WEBHOOK_URL", "")

    if not url:
        print("請提供 Discord Webhook URL：")
        print("  python test_discord.py https://discord.com/api/webhooks/...")
        print("  或設定環境變數 DISCORD_WEBHOOK_URL")
        sys.exit(1)

    now = datetime.now(tz=ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "username": "TWSE 競價拍賣通知",
        "avatar_url": "https://www.twse.com.tw/favicon.ico",
        "content": "🔔 **連線測試成功！**",
        "embeds": [
            {
                "title": "✅ Discord Webhook 已正確連線",
                "color": 0x22C55E,
                "description": "TWSE 競價拍賣行事曆的 Discord 通知功能運作正常。\n當拍賣資料有任何變動時，會自動在此頻道發送通知。",
                "fields": [
                    {"name": "測試時間", "value": now, "inline": True},
                    {"name": "通知類型", "value": "新增 / 更新 / 移除", "inline": True},
                ],
                "footer": {"text": "TWSE 競價拍賣行事曆"},
            }
        ],
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 204:
            print("✅ 測試訊息已成功送出！請到 Discord 頻道查看。")
        else:
            print(f"❌ 送出失敗：HTTP {resp.status_code}")
            print(f"   回應內容：{resp.text[:300]}")
            sys.exit(1)
    except requests.RequestException as e:
        print(f"❌ 連線錯誤：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
