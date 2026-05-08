# バックアップから cookies.json / youtube_token.json / tweet_store.json を復元するスクリプト
# 新しいRaspiへの移行・障害復旧時に使用
# 実行方法: BACKUP_PASSPHRASE=... python3 restore.py
# 前提: git clone済み、opensslインストール済み

import os
import subprocess

REPO_DIR = os.path.dirname(__file__)
BACKUP_DIR = os.path.join(REPO_DIR, "backup")
PASSPHRASE = os.environ["BACKUP_PASSPHRASE"]

RESTORE_FILES = [
    ("cookies.json",        REPO_DIR),
    ("youtube_token.json",  REPO_DIR),
    ("tweet_store.json",    REPO_DIR),
]


def decrypt(src: str, dst: str):
    subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-d", "-in", src, "-out", dst, "-pass", f"pass:{PASSPHRASE}"],
        check=True,
    )


def main():
    for fname, dest_dir in RESTORE_FILES:
        enc_path = os.path.join(BACKUP_DIR, fname + ".enc")
        dst_path = os.path.join(dest_dir, fname)

        if not os.path.exists(enc_path):
            print(f"  スキップ（バックアップなし）: {fname}")
            continue

        decrypt(enc_path, dst_path)
        print(f"  復元完了: {dst_path}")


main()
