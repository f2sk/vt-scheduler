# vt-scheduler

VTuberの配信予定を自動収集してダッシュボードに表示するシステム。

https://f2sk.github.io/vt-scheduler/

## 監視対象

- 音乃瀬奏 (@otonosekanade)
- 桃鈴ねね (@momosuzunene)
- しぐれうい (@ui_shig)

## アーキテクチャ

```
Raspberry Pi (ローカル)          GitHub
──────────────────────          ──────────────────────────────────────
scrape_twitter.py               Actions: update.yml (30分ごと)
  └─ Playwright + cookies         ├─ fetch_youtube.py   (YouTube Data API)
  └─ tweet_store.json に蓄積      ├─ analyze.py         (Groq LLM)
  └─ twitter.json 生成            │    └─ twitter.json + youtube.json
push_to_github.py               │         → schedule.json (streams配列)
  └─ data ブランチへ force push   ├─ generate_html.py   → GitHub Pages
                                  └─ update_calendar.py → Google Calendar
```

Twitterスクレイピングのみラズパイで実行し、YouTube取得・LLM解析・ページ生成・カレンダー登録はGitHub Actions側で完結する。ラズパイ障害時もYouTubeベースの更新が継続される。

## ファイル構成

| ファイル | 実行場所 | 概要 |
|---|---|---|
| `scrape_twitter.py` | Raspberry Pi | Playwright でツイートを取得し `tweet_store.json` に蓄積、`twitter.json` を生成 |
| `push_to_github.py` | Raspberry Pi | `twitter.json` を `data` ブランチへ履歴なしで force push |
| `actions/fetch_youtube.py` | GitHub Actions | YouTube Data API で live/upcoming 動画を取得し `youtube.json` を生成 |
| `actions/analyze.py` | GitHub Actions | Groq LLM (llama-3.3-70b) で全配信を `streams` 配列として構造化 |
| `actions/generate_html.py` | GitHub Actions | `schedule.json` + `twitter.json` から `index.html` を生成 |
| `actions/update_calendar.py` | GitHub Actions | `schedule.json` の全配信を Google Calendar に登録・更新・削除 |

## データフロー

1. ラズパイが30分ごと（毎時25・55分）にTwitterをスクレイピング → `twitter.json` を data ブランチへ push
2. cron-job.org が毎時00・30分に Actions をトリガー
3. Actions が YouTube API + Groq LLM で解析 → `schedule.json`（VTuberごとの `streams` 配列）を生成
4. `index.html` を生成して GitHub Pages へデプロイ
5. Google Calendar に配信予定を登録（同一配信は `screen_name + start_datetime` から生成したIDで冪等管理）

## schedule.json スキーマ

```json
{
  "analyzed_at": "2026-05-06T14:00:00+00:00",
  "schedule": {
    "otonosekanade": {
      "streams": [
        {
          "start_datetime": "05/06 21:00",
          "title": "配信タイトル",
          "is_collab": false,
          "collab_note": null,
          "source": "youtube",
          "stream_url": "https://www.youtube.com/watch?v=..."
        }
      ]
    }
  }
}
```

## セットアップ

### GitHub Secrets

| シークレット名 | 内容 |
|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API v3 キー |
| `GROQ_API_KEY` | Groq API キー |
| `GOOGLE_CREDENTIALS_JSON` | Google サービスアカウントの JSON キー（文字列） |
| `GOOGLE_CALENDAR_ID` | 登録先 Google Calendar の ID |

### Raspberry Pi

```bash
# 依存インストール
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium

# Twitterのクッキーを cookies.json として保存（Cookie-Editor 等で取得）

# cron 設定（毎時25・55分）
# 25,55 * * * * cd ~/vt-scheduler && .venv/bin/python scrape_twitter.py >> cron.log 2>&1 && .venv/bin/python push_to_github.py >> cron.log 2>&1
```

### GitHub Pages

`Settings` → `Pages` → `Source: GitHub Actions`

### Google Calendar

1. Google Cloud Console でサービスアカウントを作成し、JSON キーを発行
2. カレンダーの共有設定でサービスアカウントに「予定の変更」権限を付与
3. カレンダー ID と JSON キーを GitHub Secrets に登録

## 手動テスト手順

```bash
# ① Twitterデータ取得
ssh <pi> 'cd ~/vt-scheduler && .venv/bin/python scrape_twitter.py'

# ② data ブランチへ push
ssh <pi> 'cd ~/vt-scheduler && .venv/bin/python push_to_github.py'

# ③ Actions 手動トリガー
gh workflow run update.yml --repo f2sk/vt-scheduler

# 実行監視
gh run list --repo f2sk/vt-scheduler --limit 1
gh run watch <run_id> --repo f2sk/vt-scheduler
```
