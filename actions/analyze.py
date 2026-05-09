# Cerebras APIでTwitter・YouTubeのデータを解析して配信情報を構造化するスクリプト
# GitHub Actionsから実行する
# 実行方法: python3 analyze.py
# 環境変数: CEREBRAS_API_KEY
# 入力: twitter.json, youtube.json
# 出力: schedule.json

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

CEREBRAS_API_KEY = os.environ["CEREBRAS_API_KEY"]
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "qwen-3-235b-a22b-instruct-2507"

BASE_DIR = os.path.dirname(__file__)
TWITTER_JSON = os.path.join(BASE_DIR, "twitter.json")
YOUTUBE_JSON = os.path.join(BASE_DIR, "youtube.json")
OUTPUT_JSON = os.path.join(BASE_DIR, "schedule.json")

TWITTER_MAX_AGE_HOURS = 2

JST = timezone(timedelta(hours=9))

# channel_id → screen_name マッピング（fetch_youtube.py の TARGETS と対応）
CHANNEL_SCREEN_NAMES = {
    "UCZlDXzGoo7d44bwdNObFacg": "otonosekanade",
    "UCAWSyEs_Io8MtpY3m-zqILA": "momosuzunene",
    "UCt30jJgChL8qeT9VPadidSw": "ui_shig",
}

PROMPT_TEMPLATE = """\
以下はVTuberのツイートと、YouTubeの配信情報です。
これらを分析して、直近・近日中の配信予定を構造化JSONで返してください。

# 現在日時（JST）
{current_datetime}

# 分析対象VTuber
- 音乃瀬奏 (@otonosekanade)
- 桃鈴ねね (@momosuzunene)
- しぐれうい (@ui_shig)

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
        "stream_url": "配信URL（YouTubeのURL優先、なければツイート内のURL）" または null
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
- start_datetime: 日本時間（JST）でMM/DD HH:MM形式（例: 05/07 21:00）。不明な場合はnull
- stream_type: 以下の3値で判定する
  - "solo"  : 自分の枠で一人で配信
  - "collab": 自分の枠で他者と共同配信
  - "guest" : 他者の枠に出演（RTや引用RTによる他枠告知も含む）
- YouTubeのlive/upcomingがあればそれを優先し、Twitterで補完する
- titleはYouTubeデータのtitleフィールドをそのまま使う。YouTubeにない場合はツイート本文から配信タイトル部分を抜き出す
- stream_urlはYouTubeのurlフィールドを優先し、なければツイート本文中のURLを使う
- RTおよび引用RTは他枠への出演告知として扱う（stream_type="guest"）
- フリーチャット枠（Free chat）は配信予定としてカウントしない
- titleを要約・翻訳・改変しないこと
- 配信が検出されない場合はstreams配列を空にする

JSON以外のテキストは出力しないでください。
"""


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
                "stream_url": v.get("url"),
            })
        result[screen_name]["streams"] = streams
    return result


def load_twitter() -> dict:
    if not os.path.exists(TWITTER_JSON):
        return {}
    with open(TWITTER_JSON, encoding="utf-8") as f:
        data = json.load(f)

    # 古いデータはスキップ
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


def _build_yt_url_sets(youtube_data: dict | None) -> tuple[set[str], set[str]]:
    """YouTube データから live/upcoming の URL セットを返す"""
    live_urls: set[str] = set()
    upcoming_urls: set[str] = set()
    if not youtube_data:
        return live_urls, upcoming_urls
    for ch in youtube_data.get("channels", {}).values():
        for v in ch.get("videos", []):
            url = v.get("url")
            if not url:
                continue
            if v.get("status") == "live":
                live_urls.add(url)
            elif v.get("status") == "upcoming":
                upcoming_urls.add(url)
    return live_urls, upcoming_urls


def _should_show(stream: dict, live_urls: set, upcoming_urls: set, now: datetime) -> bool:
    """フローチャートに基づき表示すべきかを返す"""
    url = stream.get("stream_url")
    if url and url in live_urls:
        return True
    if url and url in upcoming_urls:
        return True
    # YouTube = none → start_dt で判断
    dt = parse_stream_dt(stream.get("start_datetime"))
    if dt and dt < now:
        return False
    if dt and dt >= now:
        return True
    # start_dt = null → Twitter あり（source に twitter を含む）なら表示
    return stream.get("source") in ("twitter", "both")


def _normalize_source(stream: dict, live_urls: set, upcoming_urls: set) -> dict:
    """YouTube status と既存 source を元に source フィールドを正規化する"""
    url = stream.get("stream_url")
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
    if new_source == stream.get("source"):
        return stream
    return {**stream, "source": new_source}


def merge_with_previous(new_schedule: dict, youtube_data: dict = None) -> dict:
    """前回のschedule.jsonから配信を引き継ぎ、新規結果とマージする"""
    prev: dict = {}
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, encoding="utf-8") as f:
                prev = json.load(f).get("schedule", {})
        except Exception:
            pass

    live_urls, upcoming_urls = _build_yt_url_sets(youtube_data)
    now = datetime.now(JST)
    _far_future = datetime(9999, 12, 31, 23, 59, tzinfo=JST)

    merged = {}
    for sn in set(list(new_schedule.keys()) + list(prev.keys())):
        new_streams = new_schedule.get(sn, {}).get("streams", [])
        prev_streams = prev.get(sn, {}).get("streams", [])

        new_urls = {s["stream_url"] for s in new_streams if s.get("stream_url")}
        new_dts  = {s["start_datetime"] for s in new_streams if s.get("start_datetime")}

        # 前回エントリのうち新規結果にないものを carry-forward
        extra = []
        for s in prev_streams:
            url    = s.get("stream_url")
            dt_str = s.get("start_datetime")
            if url and url in new_urls:
                continue
            if not url and dt_str and dt_str in new_dts:
                continue
            if _should_show(s, live_urls, upcoming_urls, now):
                extra.append(_normalize_source(s, live_urls, upcoming_urls))

        # 新規エントリも source 正規化
        normalized_new = [_normalize_source(s, live_urls, upcoming_urls) for s in new_streams]

        all_streams = normalized_new + extra
        all_streams.sort(key=lambda s: parse_stream_dt(s.get("start_datetime")) or _far_future)
        merged[sn] = {"streams": all_streams}

    return merged


def main():
    twitter = load_twitter()
    with open(YOUTUBE_JSON, encoding="utf-8") as f:
        youtube = json.load(f)

    # プロンプト用にデータを整形（重複行を圧縮）
    twitter_normalized = normalize_twitter(twitter) if twitter else {}
    twitter_text = json.dumps(twitter_normalized, ensure_ascii=False, indent=2) if twitter_normalized else "（データなし）"
    youtube_text = json.dumps(youtube.get("channels", {}), ensure_ascii=False, indent=2)

    jst = timezone(timedelta(hours=9))
    current_datetime = datetime.now(jst).strftime("%Y/%m/%d %H:%M JST")

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
    except Exception as e:
        msg = str(e)
        # "Cerebras API error 429: ..." → "fallback:429"
        import re as _re
        m = _re.search(r"error (\d+)", msg)
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
