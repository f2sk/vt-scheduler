# twitter.jsonをGitHubのdataブランチにforce pushするスクリプト
# git worktreeでmainと独立したディレクトリで管理する。
# 履歴を残さないためcommit-treeで単一コミットを作り直してforce pushする。
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


def ensure_worktree():
    if not os.path.exists(WORKTREE_DIR):
        run(["git", "worktree", "add", "--orphan", "-b", "data", WORKTREE_DIR])


def main():
    if not os.path.exists(DATA_SRC):
        print("twitter.json が存在しません")
        return

    with open(DATA_SRC) as f:
        data = json.load(f)
    fetched_at = data.get("fetched_at", "unknown")

    ensure_worktree()

    # twitter.jsonをworktreeにコピー
    shutil.copy2(DATA_SRC, DATA_DST)

    msg = f"data: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"

    # ステージング
    run(["git", "add", "twitter.json"], cwd=WORKTREE_DIR)

    # commit-treeで親なし単一コミットを作成（履歴を積まない）
    tree = run(["git", "write-tree"], cwd=WORKTREE_DIR)
    author_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "rp4",
        "GIT_AUTHOR_EMAIL": "rp4@local",
        "GIT_COMMITTER_NAME": "rp4",
        "GIT_COMMITTER_EMAIL": "rp4@local",
    }
    result = subprocess.run(
        ["git", "commit-tree", tree, "-m", msg],
        cwd=WORKTREE_DIR, check=True, capture_output=True, text=True, env=author_env
    )
    commit_hash = result.stdout.strip()

    # dataブランチをそのコミットに強制移動
    run(["git", "update-ref", "refs/heads/data", commit_hash], cwd=WORKTREE_DIR)
    run(["git", "push", "origin", "data", "--force"], cwd=WORKTREE_DIR)

    print(f"push完了 (fetched_at: {fetched_at})")


main()
