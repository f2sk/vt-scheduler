# twitter.jsonをGitHubにforce pushするスクリプト
# cronから呼び出す。履歴を残さないためforce pushを使用。
# 実行方法: python3 push_to_github.py
# 依存: git（システム）

import subprocess
import os
import json
from datetime import datetime, timezone

REPO_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(REPO_DIR, "twitter.json")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO_DIR, check=True, capture_output=True, text=True, **kwargs)


def main():
    if not os.path.exists(DATA_FILE):
        print("twitter.json が存在しません")
        return

    with open(DATA_FILE) as f:
        data = json.load(f)
    fetched_at = data.get("fetched_at", "unknown")
    print(f"push対象: twitter.json (fetched_at: {fetched_at})")

    # 孤立コミットで履歴を残さない
    run(["git", "checkout", "--orphan", "tmp-data"])
    run(["git", "reset"])
    run(["git", "add", "twitter.json"])
    run(["git", "commit", "-m", f"data: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"])
    run(["git", "branch", "-M", "tmp-data", "data"])
    run(["git", "push", "origin", "data", "--force"])

    # ローカルブランチをmainに戻す
    run(["git", "checkout", "main", "--"])

    print("push完了")


main()
