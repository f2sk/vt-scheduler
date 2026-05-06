# schedule.jsonからGitHub Pages用HTMLを生成するスクリプト
# GitHub Actionsから実行する
# 実行方法: python3 generate_html.py
# 環境変数: なし
# 入力: schedule.json
# 出力: index.html

import os
import json
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(__file__)
SCHEDULE_JSON = os.path.join(BASE_DIR, "schedule.json")
OUTPUT_HTML = os.path.join(BASE_DIR, "index.html")

JST = timezone(timedelta(hours=9))

DISPLAY_NAMES = {
    "otonosekanade": "otonosekanade",
    "momosuzunene":  "momosuzunene",
    "ui_shig":       "ui_shig",
}


def format_analyzed_at(iso: str) -> str:
    dt = datetime.fromisoformat(iso).astimezone(JST)
    return dt.strftime("%Y-%m-%d %H:%M JST")


def render_row(screen_name: str, info: dict) -> str:
    handle = DISPLAY_NAMES.get(screen_name, screen_name)
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

    title_escaped = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    collab_escaped = collab_note.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    title_cell = title_escaped
    if youtube_url and has_stream:
        url_escaped = youtube_url.replace("&", "&amp;")
        title_cell = f'<a href="{url_escaped}" target="_blank">{title_escaped}</a>'

    collab_cell = f'<span class="collab-note">{collab_escaped}</span>' if collab_note else ""

    return f"""      <tr>
        <td class="col-handle">@{handle}</td>
        <td class="col-status"><span class="{status_class}">{status_text}</span></td>
        <td class="col-time">{start_time}</td>
        <td class="col-title">{title_cell} {collab_cell}</td>
        <td class="col-source">{source}</td>
      </tr>"""


def generate(schedule_data: dict) -> str:
    analyzed_at = format_analyzed_at(schedule_data.get("analyzed_at", datetime.now(timezone.utc).isoformat()))
    schedule = schedule_data.get("schedule", {})

    rows = "\n".join(render_row(sn, info) for sn, info in schedule.items())

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
      --yellow: #d29922;
      --blue: #58a6ff;
      --red: #f85149;
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
      padding: 24px;
    }}
    .header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
      margin-bottom: 20px;
    }}
    .header-top {{
      display: flex;
      align-items: baseline;
      gap: 16px;
    }}
    .title {{
      font-size: 15px;
      font-weight: bold;
      color: var(--blue);
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 12px;
    }}
    .meta {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 11px;
    }}
    .meta span {{ color: var(--text); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      max-width: 900px;
    }}
    thead tr {{
      border-bottom: 1px solid var(--border);
    }}
    th {{
      text-align: left;
      padding: 6px 12px;
      color: var(--muted);
      font-size: 11px;
      font-weight: normal;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    td {{
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: var(--bg2); }}
    .col-handle {{ color: var(--blue); width: 180px; }}
    .col-status {{ width: 110px; }}
    .col-time {{ width: 70px; font-variant-numeric: tabular-nums; }}
    .col-source {{ color: var(--muted); width: 80px; font-size: 11px; }}
    .col-title a {{ color: var(--text); text-decoration: none; }}
    .col-title a:hover {{ color: var(--blue); text-decoration: underline; }}
    .status-live   {{ color: var(--green);  }}
    .status-collab {{ color: var(--purple); }}
    .status-none   {{ color: var(--muted);  }}
    .collab-note {{
      color: var(--muted);
      font-size: 11px;
      margin-left: 8px;
    }}
    .footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 11px;
      border-top: 1px solid var(--border);
      padding-top: 12px;
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
    <div class="header-top">
      <span class="title">&#x25a0; stream-monitor</span>
      <span class="subtitle">// vtuber schedule dashboard</span>
    </div>
    <div class="meta">last updated: <span>{analyzed_at}</span></div>
  </div>

  <table>
    <thead>
      <tr>
        <th>handle</th>
        <th>status</th>
        <th>time (jst)</th>
        <th>title / note</th>
        <th>source</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>

  <div class="footer">
    <span class="dot"></span>auto-refresh every 30 min &nbsp;|&nbsp; data: youtube api + twitter scrape + llm analysis
  </div>
</body>
</html>"""


def main():
    with open(SCHEDULE_JSON, encoding="utf-8") as f:
        data = json.load(f)

    html = generate(data)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"生成完了: {OUTPUT_HTML}")


main()
