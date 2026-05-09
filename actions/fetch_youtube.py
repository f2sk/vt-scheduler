# YouTubeの配信待機所・ライブ配信を取得するスクリプト
# Pi上でcronから実行する
# 実行方法: python3 fetch_youtube.py
# 認証: ~/vt-scheduler/youtube_token.json（OAuth2、メン限アクセスに必要）
# 出力: youtube.json, tracked_videos.json
# 方式: playlistItems.list ベース（search.listより大幅にクォータ削減）
#   search.list: 100ユニット/call → 600ユニット/run
#   本方式: channels.list(1) + playlistItems.list(1) + videos.list(1) = 3ユニット/channel → 9ユニット/run
#   + tracked_videos補完: videos.list(1)/run（upcoming捕捉済みIDのlive追跡 + guest配信終了検知）

import os
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
# fetch_youtube.py は actions/ にあるため、トークンは一つ上の階層
TOKEN_PATH    = os.path.join(os.path.dirname(__file__), "..", "youtube_token.json")
OUTPUT_PATH   = os.path.join(os.path.dirname(__file__), "youtube.json")
TRACKED_PATH  = os.path.join(os.path.dirname(__file__), "tracked_videos.json")
SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), "schedule.json")

TARGETS = [
    {"name": "音乃瀬奏",   "channel_id": "UCZlDXzGoo7d44bwdNObFacg", "screen_name": "otonosekanade"},
    {"name": "桃鈴ねね",   "channel_id": "UCAWSyEs_Io8MtpY3m-zqILA", "screen_name": "momosuzunene"},
    {"name": "しぐれうい", "channel_id": "UCt30jJgChL8qeT9VPadidSw", "screen_name": "ui_shig"},
]

CID_BY_SCREEN_NAME = {t["screen_name"]: t["channel_id"] for t in TARGETS}

PLAYLIST_ITEMS_MAX = 20  # アップロード一覧から取得する件数
MEMBERS_ITEMS_MAX = 10  # メンバー限定一覧から取得する件数

FREE_CHAT_KEYWORDS = ("free chat", "フリーチャット", "free-chat", "待機所")


def load_tracked() -> dict:
    """追跡中の video_id → {channel_id or screen_name, added_at} を返す"""
    if not os.path.exists(TRACKED_PATH):
        return {}
    try:
        return json.load(open(TRACKED_PATH, encoding="utf-8")).get("videos", {})
    except Exception:
        return {}


def save_tracked(videos: dict) -> None:
    with open(TRACKED_PATH, "w", encoding="utf-8") as f:
        json.dump({"videos": videos}, f, ensure_ascii=False, indent=2)


def extract_video_id(url: str) -> str | None:
    """YouTube URL から video_id（11文字）を抽出する"""
    m = re.search(r'(?:v=|live/|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else None


def load_guest_stream_ids() -> dict:
    """schedule.json の guest エントリの stream_url から video_id を収集する"""
    if not os.path.exists(SCHEDULE_PATH):
        return {}
    try:
        data = json.load(open(SCHEDULE_PATH, encoding="utf-8"))
    except Exception:
        return {}
    result = {}
    now = datetime.now(timezone.utc).isoformat()
    for sn, info in data.get("schedule", {}).items():
        for s in info.get("streams", []):
            if s.get("stream_type") != "guest":
                continue
            url = (s.get("stream_url") or "").strip()
            vid = extract_video_id(url)
            if vid:
                result[vid] = {"screen_name": sn, "added_at": now}
    return result


def check_tracked(tracked: dict) -> tuple[list[dict], set[str], set[str]]:
    """tracked IDs を videos.list で一括確認（1ユニット）。
    Returns: (live/upcoming エントリ一覧, 削除すべき ID セット, 確認済み終了 URL セット)"""
    if not tracked:
        return [], set(), set()
    video_ids = list(tracked.keys())
    detail = api_get("videos", {
        "part": "snippet,liveStreamingDetails",
        "id": ",".join(video_ids),
        "fields": "items(id,snippet(title,liveBroadcastContent),liveStreamingDetails)",
    })
    active: list[dict] = []
    to_remove: set[str] = set(video_ids)
    ended_urls: set[str] = set()
    for item in detail.get("items", []):
        vid = item["id"]
        broadcast_content = item["snippet"].get("liveBroadcastContent", "none")
        url = f"https://www.youtube.com/watch?v={vid}"
        if broadcast_content not in ("live", "upcoming"):
            ended_urls.add(url)  # none で返ってきた = 確認済み終了
            continue
        title = item["snippet"]["title"]
        if any(kw.lower() in title.lower() for kw in FREE_CHAT_KEYWORDS):
            continue
        live = item.get("liveStreamingDetails", {})
        entry = {
            "video_id": vid,
            "title": title,
            "status": broadcast_content,
            "scheduled_start": live.get("scheduledStartTime") or live.get("actualStartTime"),
            "url": url,
        }
        # channel_id か screen_name でルーティング情報を付与
        meta = tracked[vid]
        if "channel_id" in meta:
            entry["channel_id"] = meta["channel_id"]
        elif "screen_name" in meta:
            entry["screen_name"] = meta["screen_name"]
        active.append(entry)
        to_remove.discard(vid)
    return active, to_remove, ended_urls


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


def get_members_playlist_id(channel_id: str) -> str:
    """チャンネルIDからメンバー限定プレイリストIDを導出（API不要）"""
    return "UUMO" + channel_id[2:]


def get_live_and_upcoming(channel_id: str) -> list[dict]:
    """直近アップロード＋メン限プレイリストからライブ・待機中の動画を取得（4ユニット）"""
    # uploadsプレイリストから直近N件のvideo_idを取得（1ユニット）
    playlist_id = get_uploads_playlist_id(channel_id)
    pl_data = api_get("playlistItems", {
        "part": "contentDetails",
        "playlistId": playlist_id,
        "maxResults": PLAYLIST_ITEMS_MAX,
        "fields": "items/contentDetails/videoId",
    })
    video_ids = [item["contentDetails"]["videoId"] for item in pl_data.get("items", [])]

    # メン限プレイリストから直近N件を追加取得（1ユニット）
    members_pl_id = get_members_playlist_id(channel_id)
    try:
        mem_data = api_get("playlistItems", {
            "part": "contentDetails",
            "playlistId": members_pl_id,
            "maxResults": MEMBERS_ITEMS_MAX,
            "fields": "items/contentDetails/videoId",
        })
        for item in mem_data.get("items", []):
            vid = item["contentDetails"]["videoId"]
            if vid not in video_ids:
                video_ids.append(vid)
    except Exception:
        pass  # メンバーでない・プレイリスト非公開の場合はスキップ

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
    # guest stream_url を schedule.json から取得して tracked に追加
    tracked = load_tracked()
    for vid, meta in load_guest_stream_ids().items():
        if vid not in tracked:
            tracked[vid] = meta

    tracked_active, tracked_remove, ended_urls = check_tracked(tracked)
    if tracked_active:
        print(f"tracked補完: {len(tracked_active)}件")
    if ended_urls:
        print(f"confirmed ended: {len(ended_urls)}件")

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "channels": {},
        "ended_urls": sorted(ended_urls),
    }

    updated_tracked = {vid: data for vid, data in tracked.items() if vid not in tracked_remove}

    for target in TARGETS:
        cid = target["channel_id"]
        sn  = target["screen_name"]
        name = target["name"]
        print(f"取得中: {name}")
        try:
            videos = get_live_and_upcoming(cid)

            # tracked補完: playlist に出ていないが live/upcoming なものを追加
            playlist_ids = {v["video_id"] for v in videos}
            for tv in tracked_active:
                vid_id = tv["video_id"]
                if vid_id in playlist_ids:
                    continue
                # channel_id か screen_name でルーティング
                if tv.get("channel_id") == cid or tv.get("screen_name") == sn:
                    videos.append({k: v for k, v in tv.items() if k not in ("channel_id", "screen_name")})

            # upcoming を tracking に追加（自分のチャンネルのもの）
            for v in videos:
                if v["status"] == "upcoming" and v["video_id"] not in updated_tracked:
                    updated_tracked[v["video_id"]] = {
                        "channel_id": cid,
                        "added_at": datetime.now(timezone.utc).isoformat(),
                    }

            result["channels"][cid] = {"name": name, "videos": videos}
            print(f"  → {len(videos)}件 (live/upcoming)")
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  → エラー: {e}")
            result["channels"][cid] = {"name": name, "videos": [], "error": str(e)}

    save_tracked(updated_tracked)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n保存完了: {OUTPUT_PATH}")


main()
