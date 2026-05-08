# vt-scheduler

VTuberの配信予定を自動収集してダッシュボードに表示するシステム。

https://f2sk.github.io/vt-scheduler/

## 監視対象

- 音乃瀬奏 (@otonosekanade)
- 桃鈴ねね (@momosuzunene)
- しぐれうい (@ui_shig)

## アーキテクチャ

```
Raspberry Pi (ローカル)               GitHub
────────────────────────────────────  ──────────────────────────────────────
scrape_twitter.py                     Actions: update.yml (30分ごと)
  └─ Playwright + cookies               ├─ generate_html.py → GitHub Pages
  └─ tweet_store.json に蓄積            └─ update_calendar.py → Google Calendar
  └─ twitter.json 生成
fetch_youtube.py
  └─ YouTube Data API (OAuth2)
  └─ メン限を含む live/upcoming を取得
  └─ youtube.json 生成
analyze.py
  └─ Cerebras API (qwen-3-235b)
  └─ twitter.json + youtube.json
       → schedule.json (streams配列)
       ※ LLM失敗時は youtube のみでフォールバック
push_to_github.py
  └─ twitter.json / youtube.json /
     schedule.json を data ブランチへ
     force push
```

Twitter・YouTube取得・LLM解析までラズパイで実行し、ページ生成・カレンダー登録・デプロイのみGitHub Actionsで完結する。

## ファイル構成

| ファイル | 実行場所 | 概要 |
|---|---|---|
| `run_pipeline.py` | Raspberry Pi | Twitter・YouTube取得を並列実行し、解析・pushまでを統括するエントリポイント |
| `scrape_twitter.py` | Raspberry Pi | Playwright でツイートを取得し `tweet_store.json` に蓄積、`twitter.json` を生成 |
| `actions/fetch_youtube.py` | Raspberry Pi | YouTube Data API (OAuth2) で live/upcoming 動画を取得し `youtube.json` を生成 |
| `actions/analyze.py` | Raspberry Pi | Cerebras API (Qwen3-235B) で全配信を `streams` 配列として構造化。LLM失敗時はYouTubeのみでフォールバック |
| `push_to_github.py` | Raspberry Pi | `twitter.json` / `youtube.json` / `schedule.json` を `data` ブランチへ履歴なしで force push |
| `actions/generate_html.py` | GitHub Actions | `schedule.json` + `twitter.json` + `youtube.json` から `index.html` を生成 |
| `actions/update_calendar.py` | GitHub Actions | `schedule.json` の全配信を Google Calendar に登録・更新・削除 |

## データフロー

1. ラズパイが30分ごと（毎時25・55分）に `run_pipeline.py` を起動
   - scrape_twitter.py と fetch_youtube.py を**並列実行**
   - 両方完了後に analyze.py（Cerebras）→ push_to_github.py
2. GitHub Actions が30分ごとに data ブランチから3ファイルを取得
3. `index.html` を生成して GitHub Pages へデプロイ
4. Google Calendar に配信予定を登録（同一配信は `screen_name + start_datetime` から生成したIDで冪等管理）

## schedule.json スキーマ

```json
{
  "analyzed_at": "2026-05-08T16:35:00+00:00",
  "schedule": {
    "otonosekanade": {
      "streams": [
        {
          "start_datetime": "05/08 21:00",
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
| `GOOGLE_CREDENTIALS_JSON` | Google サービスアカウントの JSON キー（文字列） |
| `GOOGLE_CALENDAR_ID` | 登録先 Google Calendar の ID |

### Raspberry Pi

```bash
# 依存インストール
python3 -m venv .venv
source .venv/bin/activate
pip install playwright playwright-stealth google-auth google-auth-oauthlib requests
playwright install chromium

# Twitterのクッキーを cookies.json として保存（Cookie-Editor 等で取得）

# .env に以下を設定
# GITHUB_TOKEN=...
# CEREBRAS_API_KEY=...

# cron 設定（毎時25・55分）
# 25,55 * * * * echo "--- $(date)" >> ~/vt-scheduler/cron.log 2>&1 && \
#   cd ~/vt-scheduler && set -a && . .env && set +a && \
#   .venv/bin/python run_pipeline.py >> cron.log 2>&1
```

### YouTube OAuth 初回セットアップ

YouTube のメンバー限定配信を取得するために、ユーザーアカウントの OAuth 認証が必要。

1. Google Cloud Console で OAuth 2.0 クライアント ID を作成（デスクトップアプリ）
2. OAuth 同意画面でテストユーザーに自分のアカウントを追加
3. `client_secret.json` を `C:\tmp\` に配置して以下を実行：
   ```powershell
   pip install google-auth-oauthlib
   python C:\tmp\auth_youtube.py
   ```
4. 生成された `youtube_token.json` を Pi に転送：
   ```powershell
   scp C:\tmp\youtube_token.json <pi>:~/vt-scheduler/youtube_token.json
   ```

### GitHub Pages

`Settings` → `Pages` → `Source: GitHub Actions`

### Google Calendar

1. Google Cloud Console でサービスアカウントを作成し、JSON キーを発行
2. カレンダーの共有設定でサービスアカウントに「予定の変更」権限を付与
3. カレンダー ID と JSON キーを GitHub Secrets に登録

## 手動テスト手順

```bash
# ① Pi側でフルパイプライン実行
ssh <pi> 'cd ~/vt-scheduler && set -a && . .env && set +a && .venv/bin/python run_pipeline.py'

# ② Actions 手動トリガー
gh workflow run update.yml --repo f2sk/vt-scheduler

# 実行監視
gh run list --repo f2sk/vt-scheduler --limit 1
gh run watch <run_id> --repo f2sk/vt-scheduler
```
