# twitter.jsonをGitHubのdataブランチにforce pushするスクリプト
# git worktreeでmainと独立したディレクトリで管理する。
# 初回実行時にworktreeを自動セットアップする。
# 実行方法: python3 push_to_github.py
# 依存: git（システム）

import subprocess
import os
import json
import shutil
from datetime import datetime, timezone

REPO_DIR = os.path.expanduser("~/vt-scheduler")
WORKTREE_DIR = os.path.expanduser("~/vt-scheduler-data")
DATA_SRC = os.path.join(REPO_DIR, "twitter.json")
DATA_DST = os.path.join(WORKTREE_DIR, "twitter.json")


def run(cmd: list[str], cwd: str = REPO_DIR) -> str:
    result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def setup_worktree():
    """dataブランチ用のworktreeを初回セットアップする"""
    # orphanブランチをworktreeとして作成
    run(["git", "worktree", "add", "--orphan", "-b", "data", WORKTREE_DIR])
    # 空コミットで初期化
    open(os.path.join(WORKTREE_DIR, ".gitkeep"), "w").close()
    run(["git", "add", ".gitkeep"], cwd=WORKTREE_DIR)
    run(["git", "commit", "-m", "init data branch"], cwd=WORKTREE_DIR)
    run(["git", "push", "origin", "data"], cwd=WORKTREE_DIR)
    print("dataブランチ worktreeセットアップ完了")


def main():
    if not os.path.exists(DATA_SRC):
        print("twitter.json が存在しません")
        return

    # worktreeが存在しない場合はセットアップ
    if not os.path.exists(WORKTREE_DIR):
        setup_worktree()

    with open(DATA_SRC) as f:
        data = json.load(f)
    fetched_at = data.get("fetched_at", "unknown")

    # twitter.jsonをworktreeにコピー
    shutil.copy2(DATA_SRC, DATA_DST)

    # コミット＆force push
    run(["git", "add", "twitter.json"], cwd=WORKTREE_DIR)
    run(["git", "commit", "--amend", "--no-edit", "-m",
         f"data: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"],
        cwd=WORKTREE_DIR)
    run(["git", "push", "origin", "data", "--force"], cwd=WORKTREE_DIR)

    print(f"push完了 (fetched_at: {fetched_at})")


main()
