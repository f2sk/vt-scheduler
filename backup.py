# cookies.json / youtube_token.json / tweet_store.json を暗号化してリポジトリにバックアップ
# 差分がない場合はコミットしない（タイムスタンプ保持のため）
# 実行方法: python3 backup.py
# 環境変数: BACKUP_PASSPHRASE
# 依存: openssl（システム）

import os
import subprocess
from datetime import datetime, timezone

REPO_DIR = os.path.expanduser("~/vt-scheduler")
BACKUP_DIR = os.path.join(REPO_DIR, "backup")
PASSPHRASE = os.environ["BACKUP_PASSPHRASE"]

BACKUP_FILES = [
    os.path.join(REPO_DIR, "cookies.json"),
    os.path.join(REPO_DIR, "youtube_token.json"),
    os.path.join(REPO_DIR, "tweet_store.json"),
]


def encrypt(src: str, dst: str):
    subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-in", src, "-out", dst, "-pass", f"pass:{PASSPHRASE}"],
        check=True, capture_output=True,
    )


def decrypt_bytes(src: str) -> bytes | None:
    result = subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-d", "-in", src, "-pass", f"pass:{PASSPHRASE}"],
        capture_output=True,
    )
    return result.stdout if result.returncode == 0 else None


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    changed = []

    for src_path in BACKUP_FILES:
        fname = os.path.basename(src_path)
        enc_path = os.path.join(BACKUP_DIR, fname + ".enc")

        if not os.path.exists(src_path):
            print(f"  スキップ（存在しない）: {fname}")
            continue

        with open(src_path, "rb") as f:
            current = f.read()

        # 既存バックアップと平文比較
        if os.path.exists(enc_path):
            existing = decrypt_bytes(enc_path)
            if existing == current:
                print(f"  変更なし: {fname}")
                continue

        encrypt(src_path, enc_path)
        changed.append(fname)
        print(f"  更新: {fname}")

    if not changed:
        return

    enc_paths = [os.path.join("backup", f + ".enc") for f in changed]
    subprocess.run(["git", "add"] + enc_paths, cwd=REPO_DIR, check=True)
    msg = f"backup: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    subprocess.run(["git", "commit", "-m", msg], cwd=REPO_DIR, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=REPO_DIR, check=True, capture_output=True)
    print(f"  コミット＆プッシュ完了: {', '.join(changed)}")


main()
