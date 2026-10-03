"""Offline checks that single-document summaries ask for plain formulas, strip inline LaTeX
the model writes anyway, stick to the material (no gaps, nothing from general knowledge),
cite on each point rather than in a list at the end, and start with a '## ' heading
(mocked LLM, no DB).

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


HEADED = "## Summary\n\n" + PLAIN


def test_prompt_asks_for_plain_formulas_and_no_gaps():
    p = ss.SUMMARY_SYSTEM_PROMPT
    assert "Write formulas in plain text or Unicode" in p and "not LaTeX" in p
    assert "call out any gaps" not in p and "explains it incompletely" not in p and "Note:" not in p
    assert ss.SOURCE_ONLY_RULE in p and "general knowledge" in p and "doesn't explain, define or cover" in p
    assert "Start with a '## ' heading" in p


def test_citation_rule_wants_a_label_on_every_bullet_not_a_list():
    assert "end of the bullet it supports" in ss.CITATION_RULE and "never collect labels" in ss.CITATION_RULE


def test_map_and_condense_calls_also_stick_to_the_material():
    systems = []

    def create(**kw):
        systems.append(kw["messages"][0]["content"])
        return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content="- note [S0]"))])

    llm = MagicMock()
    llm.chat.completions.create.side_effect = create
    with patch.object(ss, "client", llm):
        ss.generate_summary("A plain sentence about graphs. " * 400)
        ss.generate_cited_summary([f"Part {i}. " + "v" * 900 for i in range(10)], [("p. 1", None)] * 10)
        ss._condense("- note [S0]", cite=True)
    assert len(systems) > 4 and all(ss.SOURCE_ONLY_RULE in s for s in systems), systems


def test_plain_summary_strips_inline_latex_short_and_long():
    out, finals = summarize(ss.generate_summary, "Graphs have vertices and edges.")
    assert out == HEADED + " [S0]", out  # plain summaries don't use labels, so nothing replaces them
    assert len(finals) == 1 and "not LaTeX" in finals[0] and "general knowledge" in finals[0]

    out, finals = summarize(ss.generate_summary, "A plain sentence about graphs. " * 400)  # map-reduce
    assert out == HEADED + " [S0]", out
    assert len(finals) == 1 and "not LaTeX" in finals[0]


def test_cited_summary_strips_latex_and_keeps_citations():
    out, finals = summarize(ss.generate_cited_summary, ["Graphs are pairs."], [("pp. 1–2", None)])
    assert out == HEADED + " (pp. 1–2)", out
    assert len(finals) == 1 and "not LaTeX" in finals[0] and "never a range" in finals[0]

    long_chunks = [f"Part {i}. " + "v" * 900 for i in range(10)]  # map-reduce path
    out, finals = summarize(ss.generate_cited_summary, long_chunks, [(f"p. {i + 1}", None) for i in range(10)])
    assert out == HEADED + " (p. 1)", out
    assert len(finals) == 1


def test_youtube_links_survive():
    url = "https://www.youtube.com/watch?v=abc123"
    out, _ = summarize(ss.generate_youtube_summary, [(125, "Graphs."), (190, "Edges.")], url,
                       reply="## Graphs\n" + r"- Order \(|V|\) [S0][S1]")
    assert out == ("## Graphs\n- Order |V| [02:05](https://www.youtube.com/watch?v=abc123&t=125s) "
                   "[03:10](https://www.youtube.com/watch?v=abc123&t=190s)"), out


def test_text_without_latex_is_unchanged():
    for text in ["- Plain (not maths) point.", r"Keep \[S0\] and \begin{x} alone", "- f(x) = (a + b)", ""]:
        assert ss.plain_inline_math(text) == text, text
    out, _ = summarize(ss.generate_summary, "Some text.", reply="## Title\n- Order is |V| (p. 3)")
    assert out == "## Title\n- Order is |V| (p. 3)"


def test_summary_always_starts_with_a_level_two_heading():
    assert ss.ensure_heading("## Trees\n- a") == "## Trees\n- a"
    assert ss.ensure_heading("# Red-Black Trees\n\n- a") == "## Red-Black Trees\n\n- a"
    assert ss.ensure_heading("### Trees") == "## Trees"
    assert ss.ensure_heading("\n\n- a\n- b") == "## Summary\n\n- a\n- b"
    assert ss.ensure_heading("Red-black trees are balanced.") == "## Summary\n\nRed-black trees are balanced."
    assert ss.ensure_heading("#hashtag text") == "## Summary\n\n#hashtag text"  # not a heading
    out, _ = summarize(ss.generate_cited_summary, ["Trees."], [("p. 1", None)], reply="# Trees\n- Balanced [S0]")
    assert out == "## Trees\n- Balanced (p. 1)", out


SCANNED_REPLY = """## Red-Black Trees
- Every node is red or black [S0]
- The root is black

Sources: [S0][S1][S2]"""


def test_a_citation_list_at_the_end_is_dropped():
    out, _ = summarize(ss.generate_cited_summary, ["a", "b", "c"], [("p. 1", None), ("p. 2", None), ("p. 3", None)],
                       reply=SCANNED_REPLY)
    assert out == "## Red-Black Trees\n- Every node is red or black (p. 1)\n- The root is black", out

    for tail in ["### Sources\n- [S0]\n- [S1]", "**References:**\n[S0], [S1]", "[S0][S1][S2]", "- [S0, S1]",
                 "## Citations\n\n1. [S0]\n2. [S2]"]:
        text = "## T\n- Point [S0]\n\n" + tail
        assert ss.drop_citation_lists(text) == "## T\n- Point [S0]", (tail, ss.drop_citation_lists(text))


def test_points_and_headings_with_content_are_kept():
    text = ("## Sources of error\n- Rounding [S0]\n\n### References\n- Cormen, chapter 13 [S1]\n"
            "- [S2] starts with a label\n- Points 3 and 4 [S3]")
    assert ss.drop_citation_lists(text) == text


def test_merged_service_uses_the_shared_function():
    assert mg.plain_inline_math is ss.plain_inline_math
    assert mg.plain_inline_math(r"A graph \(G = (V, E)\).") == "A graph G = (V, E)."


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
