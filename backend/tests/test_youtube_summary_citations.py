"""Offline checks for YouTube summary timestamp citations (no LLM, no DB).

Run from backend/:  .venv/Scripts/python.exe tests/test_youtube_summary_citations.py
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.services.ai import summary_service as ss
from app.services.youtube.youtube_service import YouTubeService

URL = "https://www.youtube.com/watch?v=abcdefghijk"


def test_format_timestamp():
    assert ss.format_timestamp(0) == "00:00"
    assert ss.format_timestamp(89) == "01:29"
    assert ss.format_timestamp(578) == "09:38"
    assert ss.format_timestamp(3725) == "1:02:05"


def test_timestamp_url_replaces_existing_t():
    assert YouTubeService.generate_timestamp_url(URL, 89) == URL + "&t=89s"
    assert YouTubeService.generate_timestamp_url(URL + "&t=30s", 89) == URL + "&t=89s"
    assert YouTubeService.generate_timestamp_url("https://youtu.be/abcdefghijk?t=5", 89) == "https://youtu.be/abcdefghijk?t=89"
    assert YouTubeService.generate_timestamp_url(URL, None) == URL


def test_link_citations():
    starts = [0, 46, 89]
    out = ss.link_citations("- A [S1]\n- B [S0][S2]\n- C [S1, S2, S1]\n- D [S9]\n- E", starts, URL)
    lines = out.splitlines()
    assert lines[0] == f"- A [00:46]({URL}&t=46s)"
    assert lines[1] == f"- B [00:00]({URL}&t=0s) [01:29]({URL}&t=89s)"
    assert lines[2] == f"- C [00:46]({URL}&t=46s) [01:29]({URL}&t=89s)"  # duplicate dropped
    assert lines[3] == "- D"  # invented label removed, no trailing space
    assert lines[4] == "- E"


def _fake_llm(reply_for):
    """Mock client whose reply depends on the prompt; records every prompt."""
    calls = []

    def create(**kwargs):
        user = kwargs["messages"][-1]["content"]
        calls.append(user)
        msg = MagicMock()
        msg.content = reply_for(user)
        resp = MagicMock()
        resp.choices = [MagicMock(message=msg)]
        return resp

    client = MagicMock()
    client.chat.completions.create.side_effect = create
    return client, calls


def test_short_video_single_call():
    chunks = [(0, "Intro to graphs."), (46, "Vertices and edges."), (89, "Adjacency lists.")]
    client, calls = _fake_llm(lambda _: "## Graphs\n- Graph = (V, E) [S1]\n- Stored as lists [S2]")
    with patch.object(ss, "client", client):
        out = ss.generate_youtube_summary(chunks, URL)
    assert len(calls) == 1
    assert "[S0] Intro to graphs." in calls[0] and "[S2] Adjacency lists." in calls[0]
    assert f"[00:46]({URL}&t=46s)" in out and f"[01:29]({URL}&t=89s)" in out
    assert "[S" not in out


def test_long_video_map_reduce_keeps_global_labels():
    chunks = [(i * 60, f"Topic {i}. " + "x" * 780) for i in range(14)]

    def reply(prompt):
        if prompt.startswith("Extract key concepts"):  # map step: cite the batch's first label
            first = prompt.split("[S", 1)[1].split("]", 1)[0]
            return f"- point from batch [S{first}]"
        return "## Summary\n- early point [S0]\n- late point [S13]"

    client, calls = _fake_llm(reply)
    with patch.object(ss, "client", client):
        out = ss.generate_youtube_summary(chunks, URL)
    assert len(calls) > 2, "expected map calls plus one final call"
    assert "[S13]" in calls[-1] or "[S12]" in calls[-1], "final call should see labels from late batches"
    assert f"[13:00]({URL}&t=780s)" in out
    assert "[S" not in out


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
