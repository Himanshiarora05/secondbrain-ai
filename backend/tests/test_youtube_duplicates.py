"""Offline checks that a YouTube video already in the library isn't imported again (mocked DB, no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_youtube_duplicates.py
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["HF_HUB_OFFLINE"] = "1"

from fastapi import HTTPException

from types import SimpleNamespace

# The signed-in user the route functions are called for (routes take it from get_current_user).
TEST_USER = SimpleNamespace(id=1)

from app.api import upload

VIDEO = "jNQXAC9IVRw"


def _saved(doc_id, source_url, filename=None):
    row = MagicMock(id=doc_id, source_url=source_url)
    row.filename = filename or f"YouTube: {VIDEO}"
    return row


def _call(url, saved=(), fetch=None):
    """Run the endpoint with the DB, transcript fetch and storage mocked."""
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = list(saved)
    segments = [{"text": "Alright, so here we are in front of the elephants.", "start": 1.2, "duration": 3.0}]
    fetch = fetch or MagicMock(return_value=(VIDEO, segments))
    with patch.object(upload.YouTubeService, "fetch_transcript", fetch), \
         patch.object(upload, "_store_document_and_chunks", return_value={"status": "stored"}) as store, \
         patch.object(upload, "logger"):
        try:
            result = asyncio.run(upload.upload_youtube(upload.YouTubeUploadRequest(url=url), db=db, user=TEST_USER))
        except HTTPException as e:
            result = e
    return result, fetch, store


def test_same_video_in_any_link_form_is_refused_before_fetching():
    saved = [_saved(21, f"https://www.youtube.com/watch?v={VIDEO}")]
    for url in [
        f"https://www.youtube.com/watch?v={VIDEO}",
        f"https://youtu.be/{VIDEO}?t=5",
        f"https://m.youtube.com/watch?v={VIDEO}&t=90s&list=PL123",
        f"https://www.youtube.com/shorts/{VIDEO}",
        f"https://www.youtube-nocookie.com/embed/{VIDEO}",
        f"  youtube.com/watch?feature=share&v={VIDEO}  ",
    ]:
        result, fetch, store = _call(url, saved=saved)
        assert isinstance(result, HTTPException) and result.status_code == 409, (url, result)
        assert result.detail["document_id"] == 21, url
        assert result.detail["message"].startswith('This video is already in your library as "YouTube: jNQXAC9IVRw"'), result.detail
        fetch.assert_not_called()
        store.assert_not_called()


def test_saved_with_a_different_link_form_still_matches():
    saved = [_saved(22, f"https://youtu.be/{VIDEO}?t=42")]
    result, _, _ = _call(f"https://www.youtube.com/watch?v={VIDEO}", saved=saved)
    assert result.status_code == 409 and result.detail["document_id"] == 22


def test_oldest_copy_is_pointed_to_when_duplicates_already_exist():
    saved = [_saved(5, f"https://youtu.be/{VIDEO}"), _saved(9, f"https://www.youtube.com/watch?v={VIDEO}")]
    result, _, _ = _call(f"https://youtu.be/{VIDEO}", saved=saved)
    assert result.detail["document_id"] == 5


def test_different_video_is_imported():
    saved = [_saved(21, "https://www.youtube.com/watch?v=fNk_zzaMoSs", filename="YouTube: fNk_zzaMoSs")]
    result, fetch, store = _call(f"https://youtu.be/{VIDEO}", saved=saved)
    assert result == {"status": "stored"}, result
    fetch.assert_called_once()
    assert store.call_args.kwargs["source_type"] == "youtube"


def test_link_without_a_video_id_gets_the_normal_error():
    """No ID to compare: the duplicate check is skipped and fetch_transcript reports the bad link."""
    fetch = MagicMock(side_effect=ValueError("Could not extract a valid YouTube video ID from URL: https://example.com"))
    result, _, _ = _call("https://example.com", saved=[_saved(21, f"https://youtu.be/{VIDEO}")], fetch=fetch)
    assert result.status_code == 400 and "video ID" in result.detail


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
