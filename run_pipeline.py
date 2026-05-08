# Pi上でのデータ取得〜push までのパイプラインを実行するスクリプト
# Twitter・YouTube取得を並列実行し、両方完了後に解析・pushを行う
# 実行方法: python3 run_pipeline.py
# 依存: .env（YOUTUBE_API_KEY, CEREBRAS_API_KEY, GITHUB_TOKEN）

import subprocess
import shutil
import os
import sys

REPO_DIR = os.path.expanduser("~/vt-scheduler")
PYTHON = os.path.join(REPO_DIR, ".venv/bin/python")
LOG = os.path.join(REPO_DIR, "cron.log")


def popen(script: str) -> subprocess.Popen:
    with open(LOG, "a") as log:
        return subprocess.Popen(
            [PYTHON, script],
            cwd=REPO_DIR,
            stdout=log,
            stderr=log,
        )


def run(script: str) -> int:
    with open(LOG, "a") as log:
        result = subprocess.run(
            [PYTHON, script],
            cwd=REPO_DIR,
            stdout=log,
            stderr=log,
        )
    return result.returncode


def main():
    # Twitter・YouTubeを並列取得
    print("Twitter・YouTube取得開始（並列）")
    p_twitter = popen("scrape_twitter.py")
    p_youtube = popen("actions/fetch_youtube.py")

    p_twitter.wait()
    p_youtube.wait()

    if p_twitter.returncode != 0:
        print(f"scrape_twitter.py 失敗 (exit {p_twitter.returncode})")
    if p_youtube.returncode != 0:
        print(f"fetch_youtube.py 失敗 (exit {p_youtube.returncode})")

    # twitter.json を actions/ にコピー（analyze.py が読む場所）
    src = os.path.join(REPO_DIR, "twitter.json")
    dst = os.path.join(REPO_DIR, "actions", "twitter.json")
    if os.path.exists(src):
        shutil.copy2(src, dst)

    # 解析（LLM失敗時はYouTubeフォールバックあり）
    print("解析開始")
    rc = run("actions/analyze.py")
    if rc != 0:
        print(f"analyze.py 失敗 (exit {rc})")
        sys.exit(rc)

    # push
    rc = run("push_to_github.py")
    if rc != 0:
        print(f"push_to_github.py 失敗 (exit {rc})")
        sys.exit(rc)

    print("パイプライン完了")


main()
