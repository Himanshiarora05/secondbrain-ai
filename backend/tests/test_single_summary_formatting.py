"""Offline checks that single-document summaries ask for plain formulas, strip inline LaTeX
the model writes anyway, and only flag incomplete explanations as gaps (mocked LLM, no DB).

Run from backend/:  .venv/Scripts/python.exe tests/test_single_summary_formatting.py
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["HF_HUB_OFFLINE"] = "1"

from app.services.ai import merged_service as mg
from app.services.ai import summary_service as ss

FINAL = "You are an expert study assistant creating an exam revision summary"
LATEX = r"- A graph \(G = (V, E)\) has order \( |V| \) and size \(|E|\) [S0]"
PLAIN = "- A graph G = (V, E) has order |V| and size |E|"


def fake_llm(final_reply, finals):
    """Final summary calls get `final_reply` (and their system prompt is recorded); map calls get notes."""
    def create(**kw):
        system = kw["messages"][0]["content"]
        if system.startswith(FINAL):
            finals.append(system)
            text = final_reply
        else:
            text = r"- note \(x_1\) [S0]"
        return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content=text))])

    llm = MagicMock()
    llm.chat.completions.create.side_effect = create
    return llm


def summarize(fn, *args, reply=LATEX):
    finals = []
    with patch.object(ss, "client", fake_llm(reply, finals)):
        return fn(*args), finals


def test_prompt_asks_for_plain_formulas_and_narrow_gaps():
    p = ss.SUMMARY_SYSTEM_PROMPT
    assert "Write formulas in plain text or Unicode" in p and "not LaTeX" in p
    assert "call out any gaps" not in p
    assert "explains it incompletely" in p and "never list topics it doesn't cover" in p


def test_plain_summary_strips_inline_latex_short_and_long():
    out, finals = summarize(ss.generate_summary, "Graphs have vertices and edges.")
    assert out == PLAIN + " [S0]", out  # plain summaries don't use labels, so nothing replaces them
    assert len(finals) == 1 and "not LaTeX" in finals[0] and "never list topics" in finals[0]

    out, finals = summarize(ss.generate_summary, "A plain sentence about graphs. " * 400)  # map-reduce
    assert out == PLAIN + " [S0]", out
    assert len(finals) == 1 and "not LaTeX" in finals[0]


def test_cited_summary_strips_latex_and_keeps_citations():
    out, finals = summarize(ss.generate_cited_summary, ["Graphs are pairs."], [("pp. 1–2", None)])
    assert out == PLAIN + " (pp. 1–2)", out
    assert len(finals) == 1 and "not LaTeX" in finals[0] and "never a range" in finals[0]

    long_chunks = [f"Part {i}. " + "v" * 900 for i in range(10)]  # map-reduce path
    out, finals = summarize(ss.generate_cited_summary, long_chunks, [(f"p. {i + 1}", None) for i in range(10)])
    assert out == PLAIN + " (p. 1)", out
    assert len(finals) == 1


def test_youtube_links_survive():
    url = "https://www.youtube.com/watch?v=abc123"
    out, _ = summarize(ss.generate_youtube_summary, [(125, "Graphs."), (190, "Edges.")], url,
                       reply=r"- Order \(|V|\) [S0][S1]")
    assert out == ("- Order |V| [02:05](https://www.youtube.com/watch?v=abc123&t=125s) "
                   "[03:10](https://www.youtube.com/watch?v=abc123&t=190s)"), out


def test_text_without_latex_is_unchanged():
    for text in ["- Plain (not maths) point.", r"Keep \[S0\] and \begin{x} alone", "- f(x) = (a + b)", ""]:
        assert ss.plain_inline_math(text) == text, text
    out, _ = summarize(ss.generate_summary, "Some text.", reply="# Title\n- Order is |V| (p. 3)")
    assert out == "# Title\n- Order is |V| (p. 3)"


def test_merged_service_uses_the_shared_function():
    assert mg.plain_inline_math is ss.plain_inline_math
    assert mg.plain_inline_math(r"A graph \(G = (V, E)\).") == "A graph G = (V, E)."


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
