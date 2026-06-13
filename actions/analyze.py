# Cerebras APIでTwitter・YouTubeのデータを解析して配信情報を構造化するスクリプト
# GitHub Actionsから実行する
# 実行方法: python3 analyze.py
# 環境変数: CEREBRAS_API_KEY
# 入力: twitter.json, youtube.json
# 出力: schedule.json

import os
import re
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

CEREBRAS_API_KEY = os.environ["CEREBRAS_API_KEY"]
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "gpt-oss-120b"

BASE_DIR = os.path.dirname(__file__)
TWITTER_JSON = os.path.join(BASE_DIR, "twitter.json")
YOUTUBE_JSON = os.path.join(BASE_DIR, "youtube.json")
OUTPUT_JSON = os.path.join(BASE_DIR, "schedule.json")

TWITTER_MAX_AGE_HOURS = 2

JST = timezone(timedelta(hours=9))

# channel_id → screen_name マッピング（fetch_youtube.py の TARGETS と対応）
CHANNEL_SCREEN_NAMES = {
    "UCWQtYtq9EOB4-I5P-3fh8lA": "otonosekanade",
    "UCAWSyEs_Io8MtpY3m-zqILA": "momosuzunene",
    "UCt30jJgChL8qeT9VPadidSw": "ui_shig",
}

PROMPT_TEMPLATE = """\
以下はVTuberのツイートと、YouTubeの配信情報です。
これらを分析して、直近・近日中の配信予定を構造化JSONで返してください。

# 現在日時（JST）
{current_datetime}

# 分析対象VTuber（括弧内がYouTubeチャンネルID）
- 音乃瀬奏 (@otonosekanade, channel_id: UCWQtYtq9EOB4-I5P-3fh8lA)
- 桃鈴ねね (@momosuzunene, channel_id: UCAWSyEs_Io8MtpY3m-zqILA)
- しぐれうい (@ui_shig, channel_id: UCt30jJgChL8qeT9VPadidSw)

# Twitterデータ
{twitter_data}

# YouTubeデータ
{youtube_data}

# 出力形式（JSON）
各VTuberについて検出された配信をすべてstreams配列に含めてください。
```json
{{
  "otonosekanade": {{
    "streams": [
      {{
        "start_datetime": "MM/DD HH:MM" または null,
        "title": "YouTubeのtitleフィールドまたはツイート本文から抜いた配信タイトル（要約・翻訳せずそのままコピー）" または null,
        "stream_type": "solo" / "collab" / "guest",
        "collab_note": "コラボ相手・他枠出演の説明" または null,
        "source": "twitter" / "youtube" / "both",
        "video_id": "YouTubeのvideo_id（11文字）" または null
      }}
    ]
  }},
  "momosuzunene": {{ "streams": [ ... ] }},
  "ui_shig": {{ "streams": [ ... ] }}
}}
```

# 判定ルール
- streams: 現在時刻の前後72時間以内に存在する配信をすべて列挙する（過去・未来を問わない、複数あればすべて含める）
- streams配列はstart_datetimeの昇順（早い順）で並べる
- start_datetime: 日本時間（JST）でMM/DD HH:MM形式（例: 05/07 21:00）。日時の解釈はツイートのdatetime_jstを基準にする。「今日」「時刻のみ（例: 21時）」はdatetime_jstの日付を使う。「明日」はその翌日。不明な場合はnull
- stream_type: 以下の3値で判定する
  - "solo"  : 自分の枠で一人で配信
  - "collab": 自分の枠で他者と共同配信
  - "guest" : 他者の枠に出演（RTや引用RTによる他枠告知も含む）
  - 判定補助: YouTubeデータのchannel_idが当該VTuberのchannel_idでない場合は"guest"とする
  - 判定補助: RTおよび引用RTは原則"guest"とする。ただし自分の枠を告知していると明らかな場合を除く
  - 注意: YouTubeデータに含まれる動画は自身のチャンネルとは限らない（メンバー限定プレイリスト経由で他者の枠が含まれる場合がある）。動画タイトルや配信者名から判断すること
- YouTubeのlive/upcomingがあればそれを優先し、Twitterで補完する
- titleはYouTubeデータのtitleフィールドをそのまま使う。YouTubeにない場合はツイート本文から配信タイトル部分を抜き出す
- video_id: 必ずYouTubeデータのvideo_idフィールド、またはツイートのvideo_idsリストに実際に存在するIDのみを使うこと。URLから自分で抽出・推測・生成することは禁止。該当するIDが存在しない場合は必ずnull
- フリーチャット枠（Free chat）は配信予定としてカウントしない
- titleを要約・翻訳・改変しないこと
- 配信が検出されない場合はstreams配列を空にする

JSON以外のテキストは出力しないでください。
"""


def extract_video_id(url: str | None) -> str | None:
    """YouTube URL から video_id（11文字）を抽出する"""
    if not url:
        return None
    m = re.search(r'(?:v=|live/|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else None


def video_id_to_url(vid: str | None) -> str | None:
    if not vid:
        return None
    return f"https://www.youtube.com/watch?v={vid}"


def prep_youtube_for_llm(youtube: dict) -> dict:
    """youtube.jsonからURLを除去してvideo_idのみ残す"""
    channels = {}
    for channel_id, ch in youtube.get("channels", {}).items():
        videos = []
        for v in ch.get("videos", []):
            videos.append({k: val for k, val in v.items() if k != "url"})
        channels[channel_id] = {**ch, "videos": videos}
    return channels


def prep_twitter_for_llm(accounts: dict) -> dict:
    """ツイートテキスト内のYouTube URLをvideo_idsリストとして付与し、datetimeをJSTに変換する"""
    result = {}
    for sn, acct in accounts.items():
        tweets = []
        for t in acct.get("tweets", []):
            text = t.get("text") or ""
            quoted = t.get("quoted_text") or ""
            # text と quoted_text を結合し、改行分割URLに対応するため空白を除去してから抽出
            text_collapsed = re.sub(r'\s+', '', text + " " + quoted)
            vids = list(dict.fromkeys(
                m for m in re.findall(r'(?:v=|live/|youtu\.be/)([A-Za-z0-9_-]{11})', text_collapsed)
            ))
            entry = dict(t)
            if vids:
                entry["video_ids"] = vids
            # UTC datetimeをJSTに変換（「今日」等の相対日付解釈に使用）
            raw_dt = t.get("datetime")
            if raw_dt:
                try:
                    dt_utc = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                    dt_jst = dt_utc.astimezone(JST)
                    entry["datetime_jst"] = dt_jst.strftime("%Y-%m-%d %H:%M JST")
                except Exception:
                    pass
            tweets.append(entry)
        result[sn] = {**acct, "tweets": tweets}
    return result


def apply_video_ids(result: dict) -> dict:
    """LLM出力のvideo_id → stream_url に変換する"""
    converted = {}
    for sn, info in result.items():
        streams = []
        for s in info.get("streams", []):
            vid = s.get("video_id")
            stream = {k: v for k, v in s.items() if k != "video_id"}
            stream["stream_url"] = video_id_to_url(vid)
            streams.append(stream)
        converted[sn] = {"streams": streams}
    return converted


def llm_analyze(prompt: str) -> str:
    payload = json.dumps({
        "model": CEREBRAS_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        CEREBRAS_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CEREBRAS_API_KEY}",
            "User-Agent": "curl/7.68.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Cerebras API error {e.code}: {e.read().decode()}") from e


def youtube_to_streams(youtube: dict) -> dict:
    """youtube.jsonをschedule形式に変換（LLM失敗時のフォールバック）"""
    result = {sn: {"streams": []} for sn in CHANNEL_SCREEN_NAMES.values()}
    for channel_id, ch in youtube.get("channels", {}).items():
        screen_name = CHANNEL_SCREEN_NAMES.get(channel_id)
        if not screen_name:
            continue
        streams = []
        for v in ch.get("videos", []):
            dt_str = v.get("scheduled_start")
            start_datetime = None
            if dt_str:
                try:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(JST)
                    start_datetime = dt.strftime("%m/%d %H:%M")
                except Exception:
                    pass
            streams.append({
                "start_datetime": start_datetime,
                "title": v.get("title"),
                "stream_type": "solo",
                "collab_note": None,
                "source": "youtube",
                "stream_url": video_id_to_url(v.get("video_id")),
            })
        result[screen_name]["streams"] = streams
    return result


def load_twitter() -> dict:
    if not os.path.exists(TWITTER_JSON):
        return {}
    with open(TWITTER_JSON, encoding="utf-8") as f:
        data = json.load(f)

    fetched_at = datetime.fromisoformat(data.get("fetched_at", "2000-01-01T00:00:00+00:00"))
    age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
    if age_hours > TWITTER_MAX_AGE_HOURS:
        print(f"Twitterデータが古いためスキップ ({age_hours:.1f}時間前)")
        return {}

    return data.get("accounts", {})


def dedup_lines(text: str) -> str:
    """連続する重複行を1行に圧縮する（ねねちスタイル対策）"""
    lines = text.splitlines()
    result = []
    for line in lines:
        if not result or line != result[-1]:
            result.append(line)
    return "\n".join(result)


def normalize_twitter(accounts: dict) -> dict:
    """ツイート本文の重複行を圧縮して返す"""
    normalized = {}
    for sn, acct in accounts.items():
        tweets = []
        for t in acct.get("tweets", []):
            tweets.append({**t, "text": dedup_lines(t.get("text", ""))})
        normalized[sn] = {**acct, "tweets": tweets}
    return normalized


def parse_stream_dt(dt_str: str | None) -> datetime | None:
    """MM/DD HH:MM → JST datetime。年またぎを考慮"""
    if not dt_str:
        return None
    now = datetime.now(JST)
    try:
        dt = datetime.strptime(f"{now.year}/{dt_str}", "%Y/%m/%d %H:%M").replace(tzinfo=JST)
        if dt < now - timedelta(days=180):
            dt = dt.replace(year=now.year + 1)
        return dt
    except ValueError:
        return None


def _build_yt_url_sets(youtube_data: dict | None) -> tuple[set[str], set[str], set[str]]:
    """YouTube データから live/upcoming/ended の URL セットを返す"""
    live_urls: set[str] = set()
    upcoming_urls: set[str] = set()
    ended_urls: set[str] = set(youtube_data.get("ended_urls", []) if youtube_data else [])
    if not youtube_data:
        return live_urls, upcoming_urls, ended_urls
    for ch in youtube_data.get("channels", {}).values():
        for v in ch.get("videos", []):
            url = video_id_to_url(v.get("video_id"))
            if not url:
                continue
            if v.get("status") == "live":
                live_urls.add(url)
            elif v.get("status") == "upcoming":
                upcoming_urls.add(url)
    return live_urls, upcoming_urls, ended_urls


def _should_show(stream: dict, live_urls: set, upcoming_urls: set, ended_urls: set, now: datetime) -> bool:
    """フローチャートに基づき表示すべきかを返す"""
    url = stream.get("stream_url")
    if url and url in ended_urls:
        return False
    if url and url in live_urls:
        return True
    if url and url in upcoming_urls:
        return True
    dt = parse_stream_dt(stream.get("start_datetime"))
    if dt and dt >= now:
        return True
    if dt and dt < now:
        return now - dt <= timedelta(hours=5)
    return stream.get("source") in ("twitter", "both")


def _normalize_source(stream: dict, live_urls: set, upcoming_urls: set) -> dict:
    """YouTube status と既存 source を元に source / is_live フィールドを正規化する"""
    url = stream.get("stream_url")
    is_live = bool(url and url in live_urls)
    yt_active = bool(url and (url in live_urls or url in upcoming_urls))
    tw_active = stream.get("source") in ("twitter", "both")
    if yt_active and tw_active:
        new_source = "both"
    elif yt_active:
        new_source = "youtube"
    elif tw_active:
        new_source = "twitter"
    else:
        new_source = stream.get("source")
    updated = dict(stream)
    if new_source != stream.get("source"):
        updated["source"] = new_source
    if is_live:
        updated["is_live"] = True
    elif "is_live" in updated:
        del updated["is_live"]
    return updated if updated != stream else stream


def merge_with_previous(new_schedule: dict, youtube_data: dict = None) -> dict:
    """前回のschedule.jsonから配信を引き継ぎ、新規結果とマージする"""
    prev: dict = {}
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, encoding="utf-8") as f:
                prev = json.load(f).get("schedule", {})
        except Exception:
            pass

    live_urls, upcoming_urls, ended_urls = _build_yt_url_sets(youtube_data)
    now = datetime.now(JST)
    _far_future = datetime(9999, 12, 31, 23, 59, tzinfo=JST)

    merged = {}
    for sn in set(list(new_schedule.keys()) + list(prev.keys())):
        new_streams = new_schedule.get(sn, {}).get("streams", [])
        prev_streams = prev.get(sn, {}).get("streams", [])

        # 新規エントリのvideo_id・日時セット（重複判定用）
        new_vids = {extract_video_id(s.get("stream_url")) for s in new_streams} - {None}
        new_dts  = {s["start_datetime"] for s in new_streams if s.get("start_datetime")}

        # 前回エントリのうち新規結果と重複しないものを carry-forward
        # ただし source:twitter + start_datetime:null のエントリは引き継がない
        # （現在のツイートから再生成されるべき情報であり、引き継ぐと無限蓄積になる）
        extra = []
        for s in prev_streams:
            if s.get("source") == "twitter" and not s.get("start_datetime"):
                continue
            url = s.get("stream_url")
            vid = extract_video_id(url)
            if vid and vid in new_vids:
                continue
            if not vid and s.get("start_datetime") in new_dts:
                continue
            if _should_show(s, live_urls, upcoming_urls, ended_urls, now):
                extra.append(_normalize_source(s, live_urls, upcoming_urls))

        # 新規エントリのsource正規化・video_id重複除去
        seen_vids: set[str] = set()
        normalized_new = []
        for s in new_streams:
            vid = extract_video_id(s.get("stream_url"))
            if vid and vid in seen_vids:
                continue
            if vid:
                seen_vids.add(vid)
            normalized_new.append(_normalize_source(s, live_urls, upcoming_urls))

        all_streams = normalized_new + extra
        all_streams.sort(key=lambda s: parse_stream_dt(s.get("start_datetime")) or _far_future)
        merged[sn] = {"streams": all_streams}

    return merged


def main():
    twitter = load_twitter()
    with open(YOUTUBE_JSON, encoding="utf-8") as f:
        youtube = json.load(f)

    # LLMに渡すデータを前処理
    twitter_normalized = normalize_twitter(twitter) if twitter else {}
    twitter_prepped = prep_twitter_for_llm(twitter_normalized) if twitter_normalized else {}
    youtube_prepped = prep_youtube_for_llm(youtube)

    twitter_text = json.dumps(twitter_prepped, ensure_ascii=False, indent=2) if twitter_prepped else "（データなし）"
    youtube_text = json.dumps(youtube_prepped, ensure_ascii=False, indent=2)

    current_datetime = datetime.now(JST).strftime("%Y/%m/%d %H:%M JST")

    prompt = PROMPT_TEMPLATE.format(
        current_datetime=current_datetime,
        twitter_data=twitter_text,
        youtube_data=youtube_text,
    )

    print("Cerebras解析中...")
    llm_status = "ok"
    try:
        result_text = llm_analyze(prompt)
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            result_text = result_text.strip().removeprefix("```json").removesuffix("```").strip()
            result = json.loads(result_text)
        # video_id → stream_url に変換
        result = apply_video_ids(result)
    except Exception as e:
        msg = str(e)
        m = re.search(r"error (\d+)", msg)
        llm_status = f"fallback:{m.group(1)}" if m else "fallback"
        print(f"LLM失敗、YouTubeのみでフォールバック: {e}")
        result = youtube_to_streams(youtube)

    result = merge_with_previous(result, youtube)

    output = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "llm_status": llm_status,
        "schedule": result,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"保存完了: {OUTPUT_JSON}")

    for sn, info in result.items():
        streams = info.get("streams", [])
        if streams:
            for s in streams:
                t = (s.get("start_datetime") or "--")
                title = (s.get("title") or "")[:30]
                collab = f" [{s.get('stream_type', 'solo')}]" if s.get("stream_type", "solo") != "solo" else ""
                print(f"  @{sn}: {t} {title}{collab}")
        else:
            print(f"  @{sn}: 配信なし")


main()
