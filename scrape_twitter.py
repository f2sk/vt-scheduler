# Twitterスクレイピングスクリプト
# 監視対象アカウントの最新ツイートを取得してJSONで出力する
# 実行方法: python3 scrape_twitter.py
# 出力: twitter.json（GitHub Actionsが読み込む）
# 依存: playwright (pip install playwright)

import asyncio
import json
import os
from datetime import datetime, timezone

COOKIES_PATH = os.path.join(os.path.dirname(__file__), "cookies.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "twitter.json")

TARGETS = [
    {"name": "音乃瀬奏",   "screen_name": "otonosekanade"},
    {"name": "桃鈴ねね",   "screen_name": "momosuzunene"},
    {"name": "しぐれうい", "screen_name": "ui_shig"},
]

MAX_TWEETS = 10


async def scrape_user(page, screen_name: str) -> list[dict]:
    await page.goto(f"https://x.com/{screen_name}", timeout=30000)
    try:
        await page.wait_for_selector('[data-testid="tweetText"]', timeout=15000)
        await page.wait_for_timeout(3000)
    except Exception:
        return []

    # スクロール前に取得する（スクロールすると仮想DOMで上部が消える）
    tweet_els = await page.query_selector_all('[data-testid="tweet"]')
    tweets = []
    seen = set()

    for el in tweet_els[:MAX_TWEETS]:
        time_el = await el.query_selector("time")
        dt = await time_el.get_attribute("datetime") if time_el else None

        # timeタグの親<a>のhrefがツイートのパーマリンク
        url = None
        if time_el:
            href = await time_el.evaluate("el => el.closest('a')?.href")
            if href and "/status/" in href:
                url = href

        text_el = await el.query_selector('[data-testid="tweetText"]')
        text = await text_el.inner_text() if text_el else None

        if not text or text in seen:
            continue
        seen.add(text)

        social_el = await el.query_selector('[data-testid="socialContext"]')
        is_retweet = social_el is not None

        tweets.append({
            "datetime": dt,
            "text": text,
            "is_retweet": is_retweet,
            "url": url,
        })

    return tweets


async def main():
    with open(COOKIES_PATH) as f:
        cookies = json.load(f)

    async with __import__("playwright.async_api", fromlist=["async_playwright"]).async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        result = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "accounts": {},
        }

        for target in TARGETS:
            sn = target["screen_name"]
            print(f"取得中: @{sn}")
            try:
                tweets = await scrape_user(page, sn)
                result["accounts"][sn] = {
                    "name": target["name"],
                    "tweets": tweets,
                }
                print(f"  → {len(tweets)}件取得")
            except Exception as e:
                print(f"  → エラー: {e}")
                result["accounts"][sn] = {
                    "name": target["name"],
                    "tweets": [],
                    "error": str(e),
                }

        await browser.close()

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"保存完了: {OUTPUT_PATH}")


asyncio.run(main())
