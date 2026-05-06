# YouTubeの配信待機所・ライブ配信を取得するスクリプト
# GitHub Actionsから実行する
# 実行方法: python3 fetch_youtube.py
# 環境変数: YOUTUBE_API_KEY
# 出力: youtube.json

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

API_KEY = os.environ["YOUTUBE_API_KEY"]
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "youtube.json")

TARGETS = [
    {"name": "音乃瀬奏",   "channel_id": "UCZlDXzGoo7d44bwdNObFacg"},
    {"name": "桃鈴ねね",   "channel_id": "UCAWSyEs_Io8MtpY3m-zqILA"},
    {"name": "しぐれうい", "channel_id": "UCt30jJgChL8qeT9VPadidSw"},
]


def api_get(endpoint: str, params: dict) -> dict:
    params["key"] = API_KEY
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def get_uploads_playlist_id(channel_id: str) -> str:
    data = api_get("channels", {
        "part": "contentDetails",
        "id": channel_id,
        "fields": "items/contentDetails/relatedPlaylists/uploads",
    })
    return data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


FREE_CHAT_KEYWORDS = ("free chat", "フリーチャット", "free-chat", "待機所")


def get_live_and_upcoming(channel_id: str) -> list[dict]:
    """ライブ配信中・待機所の動画を取得する（search.list 100units + videos.list 1unit）"""
    seen_ids = set()
    video_ids = []

    for event_type in ("live", "upcoming"):
        data = api_get("search", {
            "part": "id",
            "channelId": channel_id,
            "eventType": event_type,
            "type": "video",
            "maxResults": 5,
        })
        for item in data.get("items", []):
            vid = item["id"]["videoId"]
            if vid not in seen_ids:
                seen_ids.add(vid)
                video_ids.append(vid)

    if not video_ids:
        return []

    # 詳細情報（タイトル・正確な開始時刻・配信状態）を取得
    detail = api_get("videos", {
        "part": "snippet,liveStreamingDetails",
        "id": ",".join(video_ids),
    })

    results = []
    for item in detail.get("items", []):
        title = item["snippet"]["title"]
        # フリーチャット枠を除外
        if any(kw.lower() in title.lower() for kw in FREE_CHAT_KEYWORDS):
            continue
        live = item.get("liveStreamingDetails", {})
        results.append({
            "video_id": item["id"],
            "title": title,
            "status": item["snippet"].get("liveBroadcastContent", "none"),
            "scheduled_start": live.get("scheduledStartTime") or live.get("actualStartTime"),
            "url": f"https://www.youtube.com/watch?v={item['id']}",
        })
    return results


def main():
    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "channels": {},
    }

    for target in TARGETS:
        cid = target["channel_id"]
        name = target["name"]
        print(f"取得中: {name}")
        try:
            videos = get_live_and_upcoming(cid)
            result["channels"][cid] = {
                "name": name,
                "videos": videos,
            }
            print(f"  → {len(videos)}件 (live/upcoming)")
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  → エラー: {e}")
            result["channels"][cid] = {
                "name": name,
                "videos": [],
                "error": str(e),
            }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n保存完了: {OUTPUT_PATH}")


main()
