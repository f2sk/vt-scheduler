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
  └─ Playwright + cookies         ├─ fetch_youtube.py  (YouTube Data API)
  └─ twitter.json 生成            ├─ analyze.py        (Groq LLM)
push_to_github.py               │    └─ twitter.json + youtube.json → schedule.json
  └─ data ブランチへ force push   └─ generate_html.py  → GitHub Pages
```

Twitterスクレイピングのみラズパイで実行し、YouTube取得・LLM解析・ページ生成はGitHub Actions側で完結する。ラズパイ障害時もYouTubeベースの更新が継続される。

## ファイル構成

| ファイル | 実行場所 | 概要 |
|---|---|---|
| `scrape_twitter.py` | Raspberry Pi | Playwright でツイートを取得し `twitter.json` を生成 |
| `push_to_github.py` | Raspberry Pi | `twitter.json` を `data` ブランチへ履歴なしで force push |
| `actions/fetch_youtube.py` | GitHub Actions | YouTube Data API で live/upcoming 動画を取得 |
| `actions/analyze.py` | GitHub Actions | Groq LLM (llama-3.3-70b) でスケジュールを構造化 |
| `actions/generate_html.py` | GitHub Actions | `schedule.json` + `twitter.json` から index.html を生成 |

## セットアップ

### GitHub Secrets

| シークレット名 | 内容 |
|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API v3 キー |
| `GROQ_API_KEY` | Groq API キー |

### Raspberry Pi

```bash
# 依存インストール
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium

# Twitterのクッキーを cookies.json として保存（Cookie-Editor 等で取得）

# cron 設定（30分ごと）
# */30 * * * * cd ~/vt-scheduler && .venv/bin/python scrape_twitter.py >> cron.log 2>&1 && .venv/bin/python push_to_github.py >> cron.log 2>&1
```

### GitHub Pages

`Settings` → `Pages` → `Source: GitHub Actions`
