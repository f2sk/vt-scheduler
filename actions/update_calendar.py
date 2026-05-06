# Google CalendarにVTuberの配信予定を登録するスクリプト
# GitHub Actionsから実行する
# 実行方法: python3 update_calendar.py
# 環境変数: GOOGLE_CREDENTIALS_JSON (サービスアカウントのJSONキー文字列)
# 入力: schedule.json
# 依存: google-api-python-client google-auth

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

CALENDAR_ID = os.environ["GOOGLE_CALENDAR_ID"]
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
JST = timezone(timedelta(hours=9))
DEFAULT_DURATION_HOURS = 2

BASE_DIR = os.path.dirname(__file__)
SCHEDULE_JSON = os.path.join(BASE_DIR, "schedule.json")

DISPLAY_NAMES = {
    "otonosekanade": "音乃瀬奏",
    "momosuzunene":  "桃鈴ねね",
    "ui_shig":       "しぐれうい",
}


def make_event_id(screen_name: str, date_str: str) -> str:
    """日付＋アカウント名から決定論的なイベントIDを生成（重複防止）"""
    raw = f"vt-{screen_name}-{date_str}"
    return hashlib.md5(raw.encode()).hexdigest()[:20]


def build_event(screen_name: str, info: dict, today: datetime) -> dict:
    name = DISPLAY_NAMES.get(screen_name, screen_name)
    title = info.get("title") or "配信"
    stream_url = info.get("stream_url") or ""
    collab_note = info.get("collab_note") or ""
    is_collab = info.get("is_collab", False)
    start_time_str = info.get("start_time")

    prefix = "[コラボ]" if is_collab else ""
    summary = f"{prefix}@{screen_name} {title}".strip()

    description_parts = []
    if stream_url:
        description_parts.append(stream_url)
    if collab_note:
        description_parts.append(collab_note)
    description = "\n".join(description_parts)

    if start_time_str:
        h, m = map(int, start_time_str.split(":"))
        start_dt = today.replace(hour=h, minute=m, second=0, microsecond=0)
    else:
        start_dt = today.replace(hour=21, minute=0, second=0, microsecond=0)

    end_dt = start_dt + timedelta(hours=DEFAULT_DURATION_HOURS)

    event = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Tokyo",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Tokyo",
        },
    }
    if stream_url:
        event["location"] = stream_url

    return event


def main():
    creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"]
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    service = build("calendar", "v3", credentials=creds)

    with open(SCHEDULE_JSON, encoding="utf-8") as f:
        data = json.load(f)

    today_jst = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    date_str = today_jst.strftime("%Y%m%d")

    schedule = data.get("schedule", {})

    for screen_name, info in schedule.items():
        event_id = make_event_id(screen_name, date_str)

        if not info.get("has_stream"):
            # 配信なしなら既存イベントを削除
            try:
                service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
                print(f"  @{screen_name}: イベント削除")
            except Exception:
                pass
            continue

        event_body = build_event(screen_name, info, today_jst)

        try:
            service.events().update(
                calendarId=CALENDAR_ID,
                eventId=event_id,
                body={**event_body, "id": event_id},
            ).execute()
            print(f"  @{screen_name}: イベント更新")
        except Exception:
            service.events().insert(
                calendarId=CALENDAR_ID,
                body={**event_body, "id": event_id},
            ).execute()
            print(f"  @{screen_name}: イベント作成")


main()
