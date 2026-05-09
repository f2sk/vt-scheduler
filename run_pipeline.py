# Twitterスクレイピングのみを実行するスクリプト（Pi上でcronから実行）
# YouTube取得・解析・pushはyoutube_analyze_push.pyが別cronで担当
# 実行方法: python3 run_pipeline.py
# 依存: .env（GITHUB_TOKEN, CEREBRAS_API_KEY）

import subprocess
import shutil
import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

REPO_DIR = os.path.expanduser("~/vt-scheduler")
PYTHON = os.path.join(REPO_DIR, ".venv/bin/python")
LOG = os.path.join(REPO_DIR, "cron.log")


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
    print(f"--- {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")
    print("Twitterスクレイピング開始")
    rc = run("scrape_twitter.py")
    if rc != 0:
        print(f"scrape_twitter.py 失敗 (exit {rc})")
        return

    # twitter.json を actions/ にコピー（analyze.py が読む場所）
    src = os.path.join(REPO_DIR, "twitter.json")
    dst = os.path.join(REPO_DIR, "actions", "twitter.json")
    if os.path.exists(src):
        shutil.copy2(src, dst)
    print("Twitter完了")


main()
