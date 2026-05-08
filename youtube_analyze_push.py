# YouTube取得→LLM解析→GitHubプッシュを行うスクリプト（Pi上でcronから実行）
# Twitterスクレイピングとは独立して10分おきに実行する
# 実行方法: python3 youtube_analyze_push.py
# 依存: .env（GITHUB_TOKEN, CEREBRAS_API_KEY, BACKUP_PASSPHRASE）

import subprocess
import os
import sys

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
    rc = run("actions/fetch_youtube.py")
    if rc != 0:
        print(f"fetch_youtube.py 失敗 (exit {rc})")
        sys.exit(rc)

    rc = run("actions/analyze.py")
    if rc != 0:
        print(f"analyze.py 失敗 (exit {rc})")
        sys.exit(rc)

    rc = run("push_to_github.py")
    if rc != 0:
        print(f"push_to_github.py 失敗 (exit {rc})")
        sys.exit(rc)

    print("YouTube+解析+push完了")

    rc = run("backup.py")
    if rc != 0:
        print(f"backup.py 失敗 (exit {rc})")


main()
