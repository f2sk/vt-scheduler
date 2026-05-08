# YouTubeの配信情報を取得してdataブランチのyoutube.jsonだけを更新するスクリプト
# 5分おきのcronから実行する（フルパイプラインとは独立）
# 実行方法: python3 fetch_and_push_youtube.py
# 環境変数: GITHUB_TOKEN
# 依存: google-auth google-auth-oauthlib（fetch_youtube.pyと共通）

import os
import json
import base64
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timezone

REPO = "f2sk/vt-scheduler"
BRANCH = "data"
FILE_PATH = "youtube.json"
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

REPO_DIR = os.path.expanduser("~/vt-scheduler")
PYTHON = os.path.join(REPO_DIR, ".venv/bin/python")
YOUTUBE_JSON = os.path.join(REPO_DIR, "actions", FILE_PATH)


def github_request(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())


def get_file_sha() -> str | None:
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}?ref={BRANCH}"
    try:
        data = github_request("GET", url)
        return data["sha"]
    except Exception:
        return None


def push_youtube_json():
    with open(YOUTUBE_JSON, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    sha = get_file_sha()
    body = {
        "message": f"data: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} (youtube)",
        "content": content,
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha

    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    github_request("PUT", url, body)
    print(f"youtube.json を {BRANCH} ブランチに更新しました")


def main():
    # fetch_youtube.py を実行
    result = subprocess.run(
        [PYTHON, os.path.join(REPO_DIR, "actions/fetch_youtube.py")],
        cwd=REPO_DIR,
    )
    if result.returncode != 0:
        print(f"fetch_youtube.py 失敗 (exit {result.returncode})")
        return

    push_youtube_json()


main()
