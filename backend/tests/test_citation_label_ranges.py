"""Offline checks that label ranges like "[S0-S3]" become real citations and that the prompt
forbids ranges and labels written as words (no LLM, no DB).

Run from backend/:  .venv/Scripts/python.exe tests/test_citation_label_ranges.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from app.services.ai import summary_service as ss
from app.services.ai.merged_service import join_by_source

PAGES = [("pp. 1–2", None), ("pp. 3–4", None), ("pp. 5–6", None), ("pp. 6–8", None)]
ALL_PAGES = "(pp. 1–2; pp. 3–4; pp. 5–6; pp. 6–8)"


def test_ranges_with_any_dash_expand():
    # "-", non-breaking hyphen (what Nemotron wrote), en dash, em dash, minus sign.
    for dash in ("-", "‑", "–", "—", "−"):
        text = f"- No traversal algorithms. [S0{dash}S3]"
        assert ss.replace_labels(text, PAGES) == f"- No traversal algorithms. {ALL_PAGES}", dash


def test_range_variants():
    assert ss.replace_labels("- a [S1-S3]", PAGES) == "- a (pp. 3–4; pp. 5–6; pp. 6–8)"
    assert ss.replace_labels("- a [S1 - S2]", PAGES) == "- a (pp. 3–4; pp. 5–6)"
    assert ss.replace_labels("- a [S0-3]", PAGES) == f"- a {ALL_PAGES}", "S optional after the dash"
    assert ss.replace_labels("- a [S3-S1]", PAGES) == "- a (pp. 3–4; pp. 5–6; pp. 6–8)", "reversed"
    assert ss.replace_labels("- a [S2-S2]", PAGES) == "- a (pp. 5–6)"
    assert ss.replace_labels("- a [S0-S1, S3]", PAGES) == "- a (pp. 1–2; pp. 3–4; pp. 6–8)"
    assert ss.replace_labels("- a [S0-S1][S3]", PAGES) == "- a (pp. 1–2; pp. 3–4; pp. 6–8)"
    assert ss.replace_labels("- a ([S0-S1])", PAGES) == "- a (pp. 1–2; pp. 3–4)", "own parentheses"
    assert ss.replace_labels(r"- a \[S0-S1\]", PAGES) == "- a (pp. 1–2; pp. 3–4)", "escaped"


def test_ranges_past_the_end_are_clipped_or_dropped():
    assert ss.replace_labels("- a [S2-S999]", PAGES) == "- a (pp. 5–6; pp. 6–8)"
    assert ss.replace_labels("- a [S7-S9]", PAGES) == "- a"
    assert ss.replace_labels("- a [S0-S99999999]", PAGES) == f"- a {ALL_PAGES}"


def test_ranges_as_links_and_merged():
    links = [(f"0{i}:00", f"https://youtu.be/x?t={i * 60}") for i in range(4)]
    assert ss.replace_labels("- a [S1-S2]", links) == (
        "- a [01:00](https://youtu.be/x?t=60) [02:00](https://youtu.be/x?t=120)")
    merged = [("1: p. 1", None), ("1: p. 2", None), ("2: Slide 4", None)]
    assert ss.replace_labels("- a [S0-S2]", merged, join_plain=join_by_source) == "- a (1: p. 1, p. 2; 2: Slide 4)"


def test_single_labels_unchanged():
    assert ss.replace_labels("- a [S1]\n- b [S0][S2]\n- c [S1, S3]", PAGES) == (
        "- a (pp. 3–4)\n- b (pp. 1–2; pp. 5–6)\n- c (pp. 3–4; pp. 6–8)")
    assert ss.replace_labels("Section S2 and 3-4 [not a label]", PAGES) == "Section S2 and 3-4 [not a label]"


def test_prompt_forbids_ranges_and_labels_as_words():
    rule = ss.CITATION_RULE
    assert "never a range" in rule and "never mention them" in rule
    seen = []

    def create(**kw):
        seen.append(kw["messages"][0]["content"])
        return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content="- Graphs [S0-S1]"))])

    llm = MagicMock()
    llm.chat.completions.create.side_effect = create
    with patch.object(ss, "client", llm):
        out = ss.generate_cited_summary(["Graphs are pairs.", "Vertices and edges."], PAGES[:2])
    assert out == "- Graphs (pp. 1–2; pp. 3–4)", out
    assert "never a range" in seen[0] and "never mention them" in seen[0]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
