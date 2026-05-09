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
YOUTUBE_JSON = os.path.join(BASE_DIR, "youtube.json")
OUTPUT_HTML = os.path.join(BASE_DIR, "index.html")

JST = timezone(timedelta(hours=9))
TWEET_MAX_AGE_HOURS = 24


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def format_dt_jst(iso: str) -> str:
    dt = datetime.fromisoformat(iso).astimezone(JST)
    return dt.strftime("%m/%d %H:%M")


def pick_primary_stream(streams: list, now_jst: datetime, year: int) -> dict | None:
    """現在時刻に最も近い未来の配信を返す。なければNone"""
    future = []
    for s in streams:
        dt_str = s.get("start_datetime")
        if not dt_str:
            future.append((None, s))
            continue
        try:
            mm, dd, hh, mi = int(dt_str[0:2]), int(dt_str[3:5]), int(dt_str[6:8]), int(dt_str[9:11])
            dt = datetime(year, mm, dd, hh, mi, tzinfo=JST)
            future.append((dt, s))
        except Exception:
            future.append((None, s))
    # 未来のものを優先、同じなら早い順
    future_only = [(dt, s) for dt, s in future if dt and dt >= now_jst]
    if future_only:
        return min(future_only, key=lambda x: x[0])[1]
    # 未来がなければ最も直近の過去
    past = [(dt, s) for dt, s in future if dt]
    if past:
        return max(past, key=lambda x: x[0])[1]
    return future[0][1] if future else None


def render_stream_cell(s: dict) -> str:
    title = s.get("title") or ""
    stream_url = s.get("stream_url")
    collab_note = s.get("collab_note") or ""
    title_cell = esc(title)
    if stream_url:
        title_cell = f'<a href="{esc(stream_url)}" target="_blank">{esc(title)}</a>'
    collab_cell = f' <span class="collab-note">{esc(collab_note)}</span>' if collab_note else ""
    return f"{title_cell}{collab_cell}"


DISPLAY_ORDER = ["otonosekanade", "momosuzunene", "ui_shig"]


def render_schedule_rows(schedule: dict, analyzed_at_iso: str) -> str:
    now_jst = datetime.fromisoformat(analyzed_at_iso).astimezone(JST)
    year = now_jst.year
    rows = []
    for screen_name in DISPLAY_ORDER:
        info = schedule.get(screen_name, {})
        streams = info.get("streams", [])
        primary = pick_primary_stream(streams, now_jst, year) if streams else None

        if primary:
            stream_type = primary.get("stream_type", "solo")
            status_class = {"solo": "status-live", "collab": "status-collab", "guest": "status-guest"}.get(stream_type, "status-live")
            status_text  = {"solo": "SOLO",        "collab": "COLLAB",        "guest": "GUEST"}.get(stream_type, "SOLO")
            start_time = primary.get("start_datetime") or "--"
            source = primary.get("source") or "none"
            title_html = render_stream_cell(primary)
            # 複数配信がある場合は件数バッジを付ける
            extra = f' <span class="extra-streams">+{len(streams)-1}</span>' if len(streams) > 1 else ""
        else:
            status_class = "status-none"
            status_text = "NO STREAM"
            start_time = "--"
            source = "none"
            title_html = ""
            extra = ""

        rows.append(f"""      <tr>
        <td class="col-handle">@{esc(screen_name)}</td>
        <td class="col-status"><span class="{status_class}">{status_text}</span></td>
        <td class="col-time" style="white-space:nowrap">{esc(start_time)}</td>
        <td class="col-title">{title_html}{extra}</td>
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
                "quoted_text": tw.get("quoted_text"),
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

        quoted = tw.get("quoted_text")
        quoted_html = f'\n      <div class="tweet-quoted">{esc(re.sub(r"\n{{2,}}", "\n", quoted.strip()))}</div>' if quoted else ""

        items.append(f"""    <div class="tweet-item" data-account="{esc(tw['screen_name'])}">
      <div class="tweet-meta">{time_part} <span class="tweet-handle">{handle}</span> {rt_mark}</div>
      <div class="tweet-text">{text_escaped}</div>{quoted_html}
    </div>""")

    return "\n".join(items)


def compute_fetch_status(twitter_data: dict, youtube_data: dict, schedule_data: dict | None = None) -> dict:
    """Twitter/YouTubeの取得状態を返す"""
    # Twitter: fetched_atが存在し2時間以内ならOK
    tw_ok = False
    tw_label = "no data"
    if twitter_data:
        fetched_at_str = twitter_data.get("fetched_at")
        if fetched_at_str:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            age_h = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
            tw_ok = age_h <= 2
            tw_label = format_dt_jst(fetched_at_str) if tw_ok else f"stale ({age_h:.0f}h)"

    # YouTube: fetched_atが存在し2時間以内かつerrorなしならOK
    yt_ok = False
    yt_label = "no data"
    if youtube_data:
        fetched_at_str = youtube_data.get("fetched_at")
        if fetched_at_str:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            age_h = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
            channels = youtube_data.get("channels", {})
            errors = [cid for cid, ch in channels.items() if "error" in ch] if channels else []
            yt_ok = age_h <= 2 and len(errors) == 0
            if yt_ok:
                yt_label = format_dt_jst(fetched_at_str)
            elif age_h > 2:
                yt_label = f"stale ({age_h:.0f}h)"
            else:
                yt_label = f"err({len(errors)}/{len(channels)})"

    # LLM: schedule.jsonのllm_statusフィールドから取得
    llm_ok = False
    llm_label = "no data"
    if schedule_data:
        status = schedule_data.get("llm_status", "")
        if status == "ok":
            llm_ok = True
            llm_label = "ok"
        elif status.startswith("fallback"):
            code = status.split(":", 1)[1] if ":" in status else ""
            llm_label = f"fallback({code})" if code else "fallback"
        elif status:
            llm_label = status

    return {"tw_ok": tw_ok, "tw_label": tw_label, "yt_ok": yt_ok, "yt_label": yt_label,
            "llm_ok": llm_ok, "llm_label": llm_label}


def generate(schedule_data: dict, twitter_data: dict, fetch_status: dict | None = None) -> str:
    analyzed_at_iso = schedule_data.get("analyzed_at", datetime.now(timezone.utc).isoformat())
    analyzed_at = datetime.fromisoformat(analyzed_at_iso).astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
    schedule = schedule_data.get("schedule", {})

    rows = render_schedule_rows(schedule, analyzed_at_iso)
    tweets_html = render_tweets(twitter_data)

    # フェッチステータス HTML
    if fetch_status:
        tw_cls  = "fetch-ok" if fetch_status["tw_ok"]  else "fetch-ng"
        yt_cls  = "fetch-ok" if fetch_status["yt_ok"]  else "fetch-ng"
        llm_cls = "fetch-ok" if fetch_status["llm_ok"] else "fetch-ng"
        status_html = (
            f'  <div class="meta">data: '
            f'<span class="fetch-label {tw_cls}">tw {esc(fetch_status["tw_label"])}</span>'
            f' / '
            f'<span class="fetch-label {yt_cls}">yt {esc(fetch_status["yt_label"])}</span>'
            f' / '
            f'<span class="fetch-label {llm_cls}">llm {esc(fetch_status["llm_label"])}</span>'
            f'</div>'
        )
    else:
        status_html = ""

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
      --yellow: #e3b341;
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
    .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; width: 100%; }}
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
    .status-guest  {{ color: var(--yellow); }}
    .status-none   {{ color: var(--muted);  }}
    .collab-note {{ color: var(--muted); font-size: 11px; }}
    .extra-streams {{
      background: #21262d;
      color: var(--muted);
      font-size: 10px;
      padding: 1px 5px;
      border-radius: 3px;
      margin-left: 6px;
    }}

    /* ツイートセクション */
    .section-title {{
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin: 24px 0 0;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border);
    }}
    .tweet-tabs {{
      display: flex;
      gap: 4px;
      margin: 8px 0 10px;
    }}
    .tweet-tab {{
      background: none;
      border: 1px solid var(--border);
      color: var(--muted);
      font-family: var(--font);
      font-size: 11px;
      padding: 3px 10px;
      border-radius: 3px;
      cursor: pointer;
    }}
    .tweet-tab.active {{
      border-color: var(--blue);
      color: var(--blue);
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
    .tweet-quoted {{
      margin-top: 6px;
      padding: 6px 8px;
      border-left: 2px solid var(--border);
      color: var(--muted);
      font-size: 12px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .no-tweets {{ color: var(--muted); font-size: 12px; padding: 8px 0; }}

    .footer {{
      margin-top: 20px;
      color: var(--muted);
      font-size: 11px;
      border-top: 1px solid var(--border);
      padding-top: 10px;
    }}
    .fetch-label {{ font-size: 11px; }}
    .fetch-ok {{ color: var(--green); }}
    .fetch-ng {{ color: #f85149; }}

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
{status_html}
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>handle</th>
          <th>status</th>
          <th>date / time (jst)</th>
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
  <div class="tweet-tabs">
    <button class="tweet-tab active" data-filter="all">all</button>
    <button class="tweet-tab" data-filter="otonosekanade">奏</button>
    <button class="tweet-tab" data-filter="momosuzunene">ねね</button>
    <button class="tweet-tab" data-filter="ui_shig">うい</button>
  </div>
  <div class="tweets">
{tweets_html}
  </div>

  <div class="footer">
    <span class="dot"></span>auto-refresh every 30 min
  </div>
  <script>
    document.querySelectorAll('.tweet-tab').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tweet-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const filter = btn.dataset.filter;
        document.querySelectorAll('.tweet-item').forEach(item => {{
          item.style.display = (filter === 'all' || item.dataset.account === filter) ? '' : 'none';
        }});
      }});
    }});
  </script>
</body>
</html>"""


def main():
    with open(SCHEDULE_JSON, encoding="utf-8") as f:
        schedule_data = json.load(f)

    twitter_data = {}
    if os.path.exists(TWITTER_JSON):
        with open(TWITTER_JSON, encoding="utf-8") as f:
            twitter_data = json.load(f)

    youtube_data = {}
    if os.path.exists(YOUTUBE_JSON):
        with open(YOUTUBE_JSON, encoding="utf-8") as f:
            youtube_data = json.load(f)

    fetch_status = compute_fetch_status(twitter_data, youtube_data, schedule_data)
    html = generate(schedule_data, twitter_data, fetch_status)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"生成完了: {OUTPUT_HTML}")


main()
