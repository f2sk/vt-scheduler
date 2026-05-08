# Google CalendarにVTuberの配信予定を登録するスクリプト
# GitHub Actionsから実行する
# 実行方法: python3 update_calendar.py
# 環境変数: GOOGLE_CREDENTIALS_JSON (サービスアカウントのJSONキー文字列)
#           GOOGLE_CALENDAR_ID
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

# イベントIDのプレフィックス（カレンダー上の当ツールが作成したイベントを識別するため）
EVENT_ID_PREFIX = "vtsch"


def make_event_id(screen_name: str, start_datetime: str) -> str:
    """スクリーン名＋配信開始日時から決定論的なイベントIDを生成"""
    raw = f"{EVENT_ID_PREFIX}-{screen_name}-{start_datetime}"
    return hashlib.md5(raw.encode()).hexdigest()[:20]


def parse_start_dt(start_datetime_str: str, analyzed_at_iso: str) -> datetime | None:
    """'MM/DD HH:MM' を JST datetime に変換。年は analyzed_at の年を使う"""
    try:
        year = datetime.fromisoformat(analyzed_at_iso).year
        mm = int(start_datetime_str[0:2])
        dd = int(start_datetime_str[3:5])
        hh = int(start_datetime_str[6:8])
        mi = int(start_datetime_str[9:11])
        return datetime(year, mm, dd, hh, mi, tzinfo=JST)
    except Exception:
        return None


def build_event(screen_name: str, stream: dict, start_dt: datetime) -> dict:
    name = DISPLAY_NAMES.get(screen_name, screen_name)
    title = stream.get("title") or "配信"
    stream_url = stream.get("stream_url") or ""
    collab_note = stream.get("collab_note") or ""
    is_collab = stream.get("is_collab", False)

    prefix = "[コラボ]" if is_collab else ""
    summary = f"{prefix}{name} {title}".strip()

    description_parts = []
    if stream_url:
        description_parts.append(stream_url)
    if collab_note:
        description_parts.append(collab_note)
    description = "\n".join(description_parts)

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
    creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"].lstrip("﻿")
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    service = build("calendar", "v3", credentials=creds)

    with open(SCHEDULE_JSON, encoding="utf-8") as f:
        data = json.load(f)

    analyzed_at_iso = data.get("analyzed_at", datetime.now(timezone.utc).isoformat())
    schedule = data.get("schedule", {})

    for screen_name, info in schedule.items():
        streams = info.get("streams", [])
        for stream in streams:
            start_dt_str = stream.get("start_datetime")
            if not start_dt_str:
                print(f"  @{screen_name}: start_datetime不明のためスキップ")
                continue

            start_dt = parse_start_dt(start_dt_str, analyzed_at_iso)
            if not start_dt:
                print(f"  @{screen_name}: 日時パース失敗 ({start_dt_str})")
                continue

            event_id = make_event_id(screen_name, start_dt_str)
            event_body = build_event(screen_name, stream, start_dt)

            try:
                service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=event_id,
                    body={**event_body, "id": event_id},
                ).execute()
                print(f"  @{screen_name}: 更新 {start_dt_str} '{(stream.get('title') or '')[:20]}'")
            except Exception:
                try:
                    service.events().insert(
                        calendarId=CALENDAR_ID,
                        body={**event_body, "id": event_id},
                    ).execute()
                    print(f"  @{screen_name}: 作成 {start_dt_str} '{(stream.get('title') or '')[:20]}'")
                except Exception as e:
                    print(f"  @{screen_name}: エラー {e}")


main()
