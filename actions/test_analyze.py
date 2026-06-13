"""
analyze.py のユニットテスト
実行: python -m pytest test_analyze.py -v
"""

import sys
import os
import re
import pytest

# analyze.py をモジュールとして読み込む（環境変数不要な関数のみテスト）
sys.path.insert(0, os.path.dirname(__file__))

# CEREBRAS_API_KEY が未設定でも import できるようにダミーを設定
os.environ.setdefault("CEREBRAS_API_KEY", "dummy")

import analyze


# ── prep_twitter_for_llm ──────────────────────────────────────────────

class TestPrepTwitterForLlm:

    def test_normal_url(self):
        """通常の1行URLからvideo_idを抽出できる"""
        accounts = {"sn": {"tweets": [{"text": "配信 https://www.youtube.com/watch?v=EgweCO4dIx4 よろしく"}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert result["sn"]["tweets"][0]["video_ids"] == ["EgweCO4dIx4"]

    def test_multiline_url(self):
        """改行で分割されたURLからvideo_idを正しく抽出できる"""
        text = "配信！\nhttps://\nyoutube.com/live/EgweCO4dI\nx4?si=ncxuK6OotzB8JY59"
        accounts = {"sn": {"tweets": [{"text": text}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert result["sn"]["tweets"][0]["video_ids"] == ["EgweCO4dIx4"]

    def test_no_url(self):
        """YouTubeURLがないツイートにはvideo_idsが付与されない"""
        accounts = {"sn": {"tweets": [{"text": "今日もがんばります"}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert "video_ids" not in result["sn"]["tweets"][0]

    def test_partial_id_not_matched(self):
        """11文字未満の文字列はvideo_idとして抽出されない（改行なし版）"""
        accounts = {"sn": {"tweets": [{"text": "https://youtube.com/live/tooshort"}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert "video_ids" not in result["sn"]["tweets"][0]

    def test_dedup(self):
        """同じvideo_idが複数あっても重複しない"""
        url = "https://www.youtube.com/watch?v=EgweCO4dIx4"
        accounts = {"sn": {"tweets": [{"text": f"{url} {url}"}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert result["sn"]["tweets"][0]["video_ids"] == ["EgweCO4dIx4"]

    def test_datetime_converted_to_jst(self):
        """UTC datetimeがJST文字列に変換される"""
        accounts = {"sn": {"tweets": [{"text": "test", "datetime": "2026-06-12T13:53:57.000Z"}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert result["sn"]["tweets"][0]["datetime_jst"] == "2026-06-12 22:53 JST"

    def test_datetime_jst_date_rollover(self):
        """UTC 16:00以降はJST翌日になる"""
        accounts = {"sn": {"tweets": [{"text": "test", "datetime": "2026-06-12T16:00:00.000Z"}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert result["sn"]["tweets"][0]["datetime_jst"] == "2026-06-13 01:00 JST"

    def test_datetime_missing(self):
        """datetimeフィールドがない場合はdatetime_jstも付与されない"""
        accounts = {"sn": {"tweets": [{"text": "test"}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert "datetime_jst" not in result["sn"]["tweets"][0]

    def test_video_id_from_quoted_text(self):
        """quoted_text内の改行分割URLからもvideo_idを抽出できる"""
        quoted = "待機所\nhttps://\nyoutube.com/live/EgweCO4dI\nx4?si=xxx"
        accounts = {"sn": {"tweets": [{"text": "このあとすぐ！", "quoted_text": quoted}]}}
        result = analyze.prep_twitter_for_llm(accounts)
        assert result["sn"]["tweets"][0]["video_ids"] == ["EgweCO4dIx4"]


# ── merge_with_previous ───────────────────────────────────────────────

class TestMergeCarryForward:

    def _make_schedule(self, streams):
        return {"sn": {"streams": streams}}

    def test_twitter_only_null_datetime_not_carried_forward(self):
        """source:twitter + start_datetime:null のエントリはcarry-forwardしない"""
        stale = {
            "start_datetime": None,
            "title": "古いTwitter告知",
            "stream_type": "solo",
            "source": "twitter",
            "stream_url": None,
        }
        # 前回のschedule.jsonにstaleエントリ、今回のLLM結果は空
        import tempfile, os, json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump({"schedule": {"sn": {"streams": [stale]}}}, f)
            tmp = f.name
        orig = analyze.OUTPUT_JSON
        analyze.OUTPUT_JSON = tmp
        try:
            result = analyze.merge_with_previous({"sn": {"streams": []}})
        finally:
            analyze.OUTPUT_JSON = orig
            os.unlink(tmp)
        assert result["sn"]["streams"] == []

    def test_youtube_entry_still_carried_forward(self):
        """有効なstream_urlがあるエントリは通常通りcarry-forwardされる"""
        from datetime import datetime, timezone, timedelta
        future = (datetime.now(timezone(timedelta(hours=9))) + timedelta(hours=2)).strftime("%m/%d %H:%M")
        entry = {
            "start_datetime": future,
            "title": "未来の配信",
            "stream_type": "solo",
            "source": "youtube",
            "stream_url": "https://www.youtube.com/watch?v=EgweCO4dIx4",
        }
        import tempfile, os, json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump({"schedule": {"sn": {"streams": [entry]}}}, f)
            tmp = f.name
        orig = analyze.OUTPUT_JSON
        analyze.OUTPUT_JSON = tmp
        try:
            result = analyze.merge_with_previous({"sn": {"streams": []}})
        finally:
            analyze.OUTPUT_JSON = orig
            os.unlink(tmp)
        assert len(result["sn"]["streams"]) == 1


# ── extract_video_id ──────────────────────────────────────────────────

class TestExtractVideoId:

    def test_watch_url(self):
        assert analyze.extract_video_id("https://www.youtube.com/watch?v=EgweCO4dIx4") == "EgweCO4dIx4"

    def test_live_url(self):
        assert analyze.extract_video_id("https://www.youtube.com/live/EgweCO4dIx4") == "EgweCO4dIx4"

    def test_short_url(self):
        assert analyze.extract_video_id("https://youtu.be/EgweCO4dIx4") == "EgweCO4dIx4"

    def test_none(self):
        assert analyze.extract_video_id(None) is None

    def test_invalid(self):
        assert analyze.extract_video_id("https://example.com") is None
