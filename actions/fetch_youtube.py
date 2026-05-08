# YouTubeの配信待機所・ライブ配信を取得するスクリプト
# Pi上でcronから実行する
# 実行方法: python3 fetch_youtube.py
# 認証: ~/vt-scheduler/youtube_token.json（OAuth2、メン限アクセスに必要）
# 出力: youtube.json
# 方式: playlistItems.list ベース（search.listより大幅にクォータ削減）
#   search.list: 100ユニット/call → 600ユニット/run
#   本方式: channels.list(1) + playlistItems.list(1) + videos.list(1) = 3ユニット/channel → 9ユニット/run

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
# fetch_youtube.py は actions/ にあるため、トークンは一つ上の階層
TOKEN_PATH = os.path.join(os.path.dirname(__file__), "..", "youtube_token.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "youtube.json")

TARGETS = [
    {"name": "音乃瀬奏",   "channel_id": "UCZlDXzGoo7d44bwdNObFacg"},
    {"name": "桃鈴ねね",   "channel_id": "UCAWSyEs_Io8MtpY3m-zqILA"},
    {"name": "しぐれうい", "channel_id": "UCt30jJgChL8qeT9VPadidSw"},
]

PLAYLIST_ITEMS_MAX = 20  # アップロード一覧から取得する件数

FREE_CHAT_KEYWORDS = ("free chat", "フリーチャット", "free-chat", "待機所")


def get_access_token() -> str:
    """OAuthトークンを読み込み、期限切れなら自動更新して返す"""
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds.token


def api_get(endpoint: str, params: dict) -> dict:
    token = get_access_token()
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def get_uploads_playlist_id(channel_id: str) -> str:
    """チャンネルのアップロードプレイリストIDを取得（1ユニット）"""
    data = api_get("channels", {
        "part": "contentDetails",
        "id": channel_id,
        "fields": "items/contentDetails/relatedPlaylists/uploads",
    })
    return data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_live_and_upcoming(channel_id: str) -> list[dict]:
    """直近アップロードからライブ・待機中の動画を取得（3ユニット）"""
    # アップロードプレイリストから直近N件のvideo_idを取得（1ユニット）
    playlist_id = get_uploads_playlist_id(channel_id)
    pl_data = api_get("playlistItems", {
        "part": "contentDetails",
        "playlistId": playlist_id,
        "maxResults": PLAYLIST_ITEMS_MAX,
        "fields": "items/contentDetails/videoId",
    })
    video_ids = [item["contentDetails"]["videoId"] for item in pl_data.get("items", [])]
    if not video_ids:
        return []

    # 動画詳細（ライブ状態・開始時刻）を一括取得（1ユニット）
    detail = api_get("videos", {
        "part": "snippet,liveStreamingDetails",
        "id": ",".join(video_ids),
        "fields": "items(id,snippet(title,liveBroadcastContent),liveStreamingDetails)",
    })

    results = []
    for item in detail.get("items", []):
        broadcast_content = item["snippet"].get("liveBroadcastContent", "none")
        if broadcast_content not in ("live", "upcoming"):
            continue
        title = item["snippet"]["title"]
        if any(kw.lower() in title.lower() for kw in FREE_CHAT_KEYWORDS):
            continue
        live = item.get("liveStreamingDetails", {})
        results.append({
            "video_id": item["id"],
            "title": title,
            "status": broadcast_content,
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
