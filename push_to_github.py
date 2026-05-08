# twitter.json / youtube.json / schedule.json をGitHubのdataブランチにforce pushするスクリプト
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

# actions/ 以下の3ファイルをdataブランチにpush
DATA_FILES = [
    "twitter.json",
    "youtube.json",
    "schedule.json",
]


def run(cmd: list[str], cwd: str = REPO_DIR) -> str:
    result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def ensure_worktree():
    if not os.path.exists(WORKTREE_DIR):
        run(["git", "worktree", "add", "--orphan", "-b", "data", WORKTREE_DIR])


def main():
    actions_dir = os.path.join(REPO_DIR, "actions")

    # 存在確認（schedule.jsonがなければ解析未完了）
    for fname in DATA_FILES:
        src = os.path.join(actions_dir, fname)
        if not os.path.exists(src):
            print(f"{fname} が存在しません。スキップします。")
            return

    ensure_worktree()

    for fname in DATA_FILES:
        shutil.copy2(os.path.join(actions_dir, fname), os.path.join(WORKTREE_DIR, fname))

    msg = f"data: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"

    run(["git", "add"] + DATA_FILES, cwd=WORKTREE_DIR)

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

    run(["git", "update-ref", "refs/heads/data", commit_hash], cwd=WORKTREE_DIR)
    run(["git", "push", "origin", "data", "--force"], cwd=WORKTREE_DIR)

    with open(os.path.join(actions_dir, "schedule.json")) as f:
        analyzed_at = json.load(f).get("analyzed_at", "unknown")
    print(f"push完了 (analyzed_at: {analyzed_at})")


main()
