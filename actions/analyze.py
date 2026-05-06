# Gemini APIでTwitter・YouTubeのデータを解析して配信情報を構造化するスクリプト
# GitHub Actionsから実行する
# 実行方法: python3 analyze_gemini.py
# 環境変数: GEMINI_API_KEY
# 入力: twitter.json, youtube.json
# 出力: schedule.json

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

BASE_DIR = os.path.dirname(__file__)
TWITTER_JSON = os.path.join(BASE_DIR, "twitter.json")
YOUTUBE_JSON = os.path.join(BASE_DIR, "youtube.json")
OUTPUT_JSON = os.path.join(BASE_DIR, "schedule.json")

TWITTER_MAX_AGE_HOURS = 2

PROMPT_TEMPLATE = """\
以下はVTuberのツイートと、YouTubeの配信情報です。
これらを分析して、今日・近日中の配信予定を構造化JSONで返してください。

# 分析対象VTuber
- 音乃瀬奏 (@otonosekanade)
- 桃鈴ねね (@momosuzunene)
- しぐれうい (@ui_shig)

# Twitterデータ
{twitter_data}

# YouTubeデータ
{youtube_data}

# 出力形式（JSON）
各VTuberについて以下を出力してください。
```json
{{
  "otonosekanade": {{
    "has_stream": true/false,
    "start_time": "HH:MM" または null,
    "title": "YouTubeのtitleフィールドまたはツイート本文から抜いた配信タイトル（要約・翻訳せずそのままコピー）" または null,
    "is_collab": true/false,
    "collab_note": "コラボ相手・他枠出演の説明" または null,
    "source": "twitter" / "youtube" / "both",
    "stream_url": "配信URL（YouTubeのURL優先、なければツイート内のURL）" または null
  }},
  "momosuzunene": {{ ... }},
  "ui_shig": {{ ... }}
}}
```

# 判定ルール
- has_stream: 今日または数時間以内に配信がある場合にtrue
- start_time: 日本時間（JST, UTC+9）でHH:MM形式。不明な場合はnull
- is_collab: 自分の枠ではなく他者の配信に出演する場合もtrue
- YouTubeのlive/upcomingがあればそれを優先し、Twitterで補完する
- titleはYouTubeデータのtitleフィールドをそのまま使う。YouTubeにない場合はツイート本文から配信タイトル部分を抜き出す
- stream_urlはYouTubeのurlフィールドを優先し、なければツイート本文中のURLを使う
- RTは他枠への出演告知として扱う
- フリーチャット枠（Free chat）は配信予定としてカウントしない
- titleを要約・翻訳・改変しないこと

JSON以外のテキストは出力しないでください。
"""


def llm_analyze(prompt: str) -> str:
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "python-requests/2.31.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Groq API error {e.code}: {e.read().decode()}") from e


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


def main():
    twitter = load_twitter()
    with open(YOUTUBE_JSON, encoding="utf-8") as f:
        youtube = json.load(f)

    # プロンプト用にデータを整形
    twitter_text = json.dumps(twitter, ensure_ascii=False, indent=2) if twitter else "（データなし）"
    youtube_text = json.dumps(youtube.get("channels", {}), ensure_ascii=False, indent=2)

    prompt = PROMPT_TEMPLATE.format(
        twitter_data=twitter_text,
        youtube_data=youtube_text,
    )

    print("Gemini解析中...")
    result_text = llm_analyze(prompt)

    try:
        result = json.loads(result_text)
    except json.JSONDecodeError:
        # コードブロックで囲まれている場合は除去
        result_text = result_text.strip().removeprefix("```json").removesuffix("```").strip()
        result = json.loads(result_text)

    output = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "schedule": result,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"保存完了: {OUTPUT_JSON}")

    for sn, info in result.items():
        status = "配信あり" if info.get("has_stream") else "配信なし"
        time_ = info.get("start_time") or "--:--"
        title = (info.get("title") or "")[:30]
        print(f"  @{sn}: {status} {time_} {title}")


main()
