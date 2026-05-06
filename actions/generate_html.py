# schedule.json と twitter.json から GitHub Pages 用 HTML を生成するスクリプト
# GitHub Actionsから実行する
# 実行方法: python3 generate_html.py
# 環境変数: なし
# 入力: schedule.json, twitter.json (任意)
# 出力: index.html

import os
import re
import json
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(__file__)
SCHEDULE_JSON = os.path.join(BASE_DIR, "schedule.json")
TWITTER_JSON = os.path.join(BASE_DIR, "twitter.json")
OUTPUT_HTML = os.path.join(BASE_DIR, "index.html")

JST = timezone(timedelta(hours=9))
TWEET_MAX_AGE_HOURS = 24


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def format_dt_jst(iso: str) -> str:
    dt = datetime.fromisoformat(iso).astimezone(JST)
    return dt.strftime("%m/%d %H:%M")


def render_schedule_rows(schedule: dict) -> str:
    rows = []
    for screen_name, info in schedule.items():
        has_stream = info.get("has_stream", False)
        start_time = info.get("start_time") or "--:--"
        title = info.get("title") or ""
        is_collab = info.get("is_collab", False)
        collab_note = info.get("collab_note") or ""
        source = info.get("source", "none")
        youtube_url = info.get("youtube_url")

        if has_stream:
            status_class = "status-collab" if is_collab else "status-live"
            status_text = "COLLAB" if is_collab else "LIVE"
        else:
            status_class = "status-none"
            status_text = "NO STREAM"

        title_cell = esc(title)
        if youtube_url and has_stream:
            title_cell = f'<a href="{esc(youtube_url)}" target="_blank">{esc(title)}</a>'

        collab_cell = f' <span class="collab-note">{esc(collab_note)}</span>' if collab_note else ""

        rows.append(f"""      <tr>
        <td class="col-handle">@{esc(screen_name)}</td>
        <td class="col-status"><span class="{status_class}">{status_text}</span></td>
        <td class="col-time">{esc(start_time)}</td>
        <td class="col-title">{title_cell}{collab_cell}</td>
        <td class="col-source">{esc(source)}</td>
      </tr>""")
    return "\n".join(rows)


def render_tweets(twitter_data: dict) -> str:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=TWEET_MAX_AGE_HOURS)

    all_tweets = []
    for screen_name, acct in twitter_data.get("accounts", {}).items():
        for tw in acct.get("tweets", []):
            dt_str = tw.get("datetime")
            if not dt_str:
                continue
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt < cutoff:
                continue
            all_tweets.append({
                "screen_name": screen_name,
                "datetime": dt,
                "text": tw.get("text", ""),
                "is_retweet": tw.get("is_retweet", False),
                "url": tw.get("url"),
            })

    if not all_tweets:
        return '<p class="no-tweets">（過去24時間のツイートなし）</p>'

    all_tweets.sort(key=lambda t: t["datetime"], reverse=True)

    items = []
    for tw in all_tweets:
        dt_label = format_dt_jst(tw["datetime"].isoformat())
        rt_mark = '<span class="rt-mark">RT</span> ' if tw["is_retweet"] else ""
        text_escaped = esc(re.sub(r'\n{2,}', '\n', tw["text"].strip()))
        handle = f'@{esc(tw["screen_name"])}'

        if tw["url"]:
            time_part = f'<a href="{esc(tw["url"])}" target="_blank" class="tweet-time">{dt_label}</a>'
        else:
            time_part = f'<span class="tweet-time">{dt_label}</span>'

        items.append(f"""    <div class="tweet-item">
      <div class="tweet-meta">{time_part} <span class="tweet-handle">{handle}</span> {rt_mark}</div>
      <div class="tweet-text">{text_escaped}</div>
    </div>""")

    return "\n".join(items)


def generate(schedule_data: dict, twitter_data: dict) -> str:
    analyzed_at_iso = schedule_data.get("analyzed_at", datetime.now(timezone.utc).isoformat())
    analyzed_at = datetime.fromisoformat(analyzed_at_iso).astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
    schedule = schedule_data.get("schedule", {})

    rows = render_schedule_rows(schedule)
    tweets_html = render_tweets(twitter_data)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="1800">
  <title>Stream Monitor</title>
  <style>
    :root {{
      --bg: #0d1117;
      --bg2: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --muted: #8b949e;
      --green: #3fb950;
      --blue: #58a6ff;
      --purple: #bc8cff;
      --font: 'Courier New', 'Consolas', monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      font-size: 13px;
      min-height: 100vh;
      padding: 16px;
    }}
    .header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 10px;
      margin-bottom: 16px;
    }}
    .title {{ font-size: 14px; font-weight: bold; color: var(--blue); }}
    .meta {{ margin-top: 4px; color: var(--muted); font-size: 11px; }}
    .meta span {{ color: var(--text); }}

    /* スケジュールテーブル */
    .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 480px;
    }}
    thead tr {{ border-bottom: 1px solid var(--border); }}
    th {{
      text-align: left;
      padding: 5px 10px;
      color: var(--muted);
      font-size: 10px;
      font-weight: normal;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      white-space: nowrap;
    }}
    td {{
      padding: 7px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .col-handle {{ color: var(--blue); white-space: nowrap; }}
    .col-status {{ white-space: nowrap; }}
    .col-time {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
    .col-source {{ color: var(--muted); font-size: 11px; white-space: nowrap; }}
    .col-title a {{ color: var(--text); text-decoration: none; }}
    .col-title a:hover {{ color: var(--blue); text-decoration: underline; }}
    .status-live   {{ color: var(--green);  }}
    .status-collab {{ color: var(--purple); }}
    .status-none   {{ color: var(--muted);  }}
    .collab-note {{ color: var(--muted); font-size: 11px; }}

    /* ツイートセクション */
    .section-title {{
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin: 24px 0 10px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border);
    }}
    .tweet-item {{
      padding: 8px 0;
      border-bottom: 1px solid var(--border);
    }}
    .tweet-item:last-child {{ border-bottom: none; }}
    .tweet-meta {{
      font-size: 11px;
      color: var(--muted);
      margin-bottom: 3px;
    }}
    .tweet-time {{ color: var(--muted); text-decoration: none; }}
    .tweet-time:hover {{ color: var(--blue); }}
    .tweet-handle {{ color: var(--blue); }}
    .rt-mark {{
      background: #21262d;
      color: var(--muted);
      font-size: 10px;
      padding: 1px 4px;
      border-radius: 3px;
    }}
    .tweet-text {{
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.5;
    }}
    .no-tweets {{ color: var(--muted); font-size: 12px; padding: 8px 0; }}

    .footer {{
      margin-top: 20px;
      color: var(--muted);
      font-size: 11px;
      border-top: 1px solid var(--border);
      padding-top: 10px;
    }}
    .dot {{
      display: inline-block;
      width: 6px; height: 6px;
      border-radius: 50%;
      background: var(--green);
      margin-right: 6px;
      vertical-align: middle;
    }}
  </style>
</head>
<body>
  <div class="header">
    <div class="title">&#x25a0; stream-monitor</div>
    <div class="meta">last updated: <span>{analyzed_at}</span></div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>handle</th>
          <th>status</th>
          <th>time (jst)</th>
          <th>title / note</th>
          <th>src</th>
        </tr>
      </thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </div>

  <div class="section-title">recent tweets (24h)</div>
  <div class="tweets">
{tweets_html}
  </div>

  <div class="footer">
    <span class="dot"></span>auto-refresh every 30 min
  </div>
</body>
</html>"""


def main():
    with open(SCHEDULE_JSON, encoding="utf-8") as f:
        schedule_data = json.load(f)

    twitter_data = {}
    if os.path.exists(TWITTER_JSON):
        with open(TWITTER_JSON, encoding="utf-8") as f:
            twitter_data = json.load(f)

    html = generate(schedule_data, twitter_data)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"生成完了: {OUTPUT_HTML}")


main()
