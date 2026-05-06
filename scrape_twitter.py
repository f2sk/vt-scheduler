# Twitterスクレイピングスクリプト
# 監視対象アカウントの最新ツイートを取得してJSONで出力する
# 実行方法: python3 scrape_twitter.py
# 出力: twitter.json（GitHub Actionsが読み込む）
# 依存: playwright, playwright-stealth (pip install playwright playwright-stealth)

import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone, timedelta

from playwright_stealth import Stealth

COOKIES_PATH = os.path.join(os.path.dirname(__file__), "cookies.json")
OUTPUT_PATH  = os.path.join(os.path.dirname(__file__), "twitter.json")
STORE_PATH   = os.path.join(os.path.dirname(__file__), "tweet_store.json")

TARGETS = [
    {"name": "音乃瀬奏",   "screen_name": "otonosekanade"},
    {"name": "桃鈴ねね",   "screen_name": "momosuzunene"},
    {"name": "しぐれうい", "screen_name": "ui_shig"},
]

MAX_NEW_TWEETS  = 50   # 1アカウント1回のスクレイプで取得する新ツイート上限
MAX_SCROLLS     = 15   # スクロール上限
STORE_KEEP_DAYS = 3    # ストアの保持期間（日）
OUTPUT_HOURS    = 24   # twitter.jsonに出力するツイートの時間窓
RANDOM_DELAY_MAX = 180 # 起動時ランダム遅延の上限（秒）


def load_store() -> dict:
    """アカウントごとの蓄積ツイートを読み込む"""
    if not os.path.exists(STORE_PATH):
        return {}
    with open(STORE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_store(store: dict):
    """古いツイートを除去して保存する"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=STORE_KEEP_DAYS)).isoformat()
    pruned = {}
    for sn, tweets in store.items():
        pruned[sn] = [t for t in tweets if (t.get("datetime") or "") >= cutoff]
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)


async def scrape_new_tweets(page, screen_name: str, known_urls: set) -> list[dict]:
    """known_urlsに含まれるURLに到達するまで遡り、新ツイートのみ返す"""
    await page.goto(f"https://x.com/{screen_name}", timeout=30000)
    try:
        await page.wait_for_selector('[data-testid="tweetText"]', timeout=15000)
        await page.wait_for_timeout(random.randint(1500, 3500))
    except Exception:
        return []

    new_tweets = []
    seen_texts = set()

    async def collect_visible() -> bool:
        """現在DOMに表示されているツイートを収集。既知URLに到達したらTrueを返す"""
        els = await page.query_selector_all('[data-testid="tweet"]')
        for el in els:
            text_els = await el.query_selector_all('[data-testid="tweetText"]')
            text = await text_els[0].inner_text() if text_els else None
            if not text or text in seen_texts:
                continue

            time_el = await el.query_selector("time")
            dt = await time_el.get_attribute("datetime") if time_el else None

            url = None
            if time_el:
                href = await time_el.evaluate("el => el.closest('a')?.href")
                if href and "/status/" in href:
                    url = href

            # 既知URLに到達 → これより古いツイートは取得済みなので打ち切り
            if url and url in known_urls:
                return True

            seen_texts.add(text)
            quoted_text = await text_els[1].inner_text() if len(text_els) > 1 else None
            social_el = await el.query_selector('[data-testid="socialContext"]')
            is_retweet = social_el is not None

            new_tweets.append({
                "datetime": dt,
                "text": text,
                "quoted_text": quoted_text,
                "is_retweet": is_retweet,
                "url": url,
            })

        return False

    for _ in range(MAX_SCROLLS + 1):
        hit = await collect_visible()
        if hit or len(new_tweets) >= MAX_NEW_TWEETS:
            break
        # ランダムスクロール量・待機時間・マウス移動で人間らしい操作を模倣
        scroll_amount = random.randint(600, 2400)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await page.mouse.move(random.randint(100, 900), random.randint(100, 600))
        await page.wait_for_timeout(random.randint(1000, 2500))

    return new_tweets


async def main():
    # 起動タイミングをランダムにずらす（cronの固定間隔を隠蔽）
    delay = random.randint(0, RANDOM_DELAY_MAX)
    print(f"起動遅延: {delay}秒")
    await asyncio.sleep(delay)

    with open(COOKIES_PATH) as f:
        cookies = json.load(f)

    store = load_store()

    async with __import__("playwright.async_api", fromlist=["async_playwright"]).async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        # Linux x86_64 Chrome UA（ラズパイのARMと完全一致はしないが最も一般的なLinux UA）
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()
        await Stealth().apply_stealth_async(page)  # navigator.webdriver等のbot検知シグナルを無効化

        for target in TARGETS:
            sn = target["screen_name"]
            print(f"取得中: @{sn}")
            try:
                existing = store.get(sn, [])
                known_urls = {t["url"] for t in existing if t.get("url")}
                new_tweets = await scrape_new_tweets(page, sn, known_urls)
                # 新ツイートをストアの先頭に追加（重複は除外）
                merged = new_tweets + [t for t in existing if t.get("url") not in {nt["url"] for nt in new_tweets}]
                store[sn] = merged
                print(f"  → 新規{len(new_tweets)}件 / 累計{len(merged)}件")
            except Exception as e:
                print(f"  → エラー: {e}")

        await browser.close()

    save_store(store)

    # twitter.json: 直近OUTPUT_HOURS時間分を出力
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=OUTPUT_HOURS)).isoformat()
    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "accounts": {},
    }
    for target in TARGETS:
        sn = target["screen_name"]
        tweets = [t for t in store.get(sn, []) if (t.get("datetime") or "") >= cutoff]
        result["accounts"][sn] = {"name": target["name"], "tweets": tweets}

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"保存完了: {OUTPUT_PATH}")


asyncio.run(main())
