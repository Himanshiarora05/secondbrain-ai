"""Offline checks that notes too long for one final call are combined in rounds, keeping their
citation labels (mocked LLM, model limits set by hand; no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_summary_rounds.py
"""
import os
import re
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
from app.services.ai import model_limits as ml
from app.services.ai import summary_service as ss
from app.services.ai.merged_service import MergedSource

FINAL_PROMPTS = ("You are an expert study assistant creating",)


class FakeLLM:
    """Map calls return long notes (so rounds are needed); combining calls return a short note
    carrying every label they were shown; the final call returns every label it was shown."""

    def __init__(self, map_chars=1500, combine_chars=300, shrink=True):
        self.map_chars, self.combine_chars, self.shrink = map_chars, combine_chars, shrink
        self.calls = []
        self.chat = MagicMock()
        self.chat.completions.create.side_effect = self._create

    def kind(self, system):
        if system.startswith("You are a concise academic tutor combining"):
            return "combine"
        if system.startswith(FINAL_PROMPTS):
            return "final"
        return "map"

    def _create(self, **kw):
        system, user = kw["messages"][0]["content"], kw["messages"][1]["content"]
        kind = self.kind(system)
        self.calls.append((kind, len(user), user))
        labels = " ".join(dict.fromkeys(re.findall(r"\[S\d+\]", user)))
        if kind == "final":
            text = f"- Everything {labels}"
        elif kind == "combine":
            size = self.combine_chars if self.shrink else len(user)
            text = f"- combined {labels} " + "c" * max(0, size - len(labels))
        else:
            text = f"- note {labels} " + "n" * self.map_chars
        return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content=text))])

    def of(self, kind):
        return [c for c in self.calls if c[0] == kind]


def set_limits(context, max_output):
    ml._limits.update(model="test/model", context=context, max_output=max_output)


def reset_limits():
    ml._limits.update(model=None, context=None, max_output=None)


def test_budget_follows_the_model():
    reset_limits()
    assert ss.final_input_budget(1500) == ss.FALLBACK_FINAL_INPUT_CHARS == 24_000
    set_limits(16385, 4096)  # gpt-3.5-turbo
    assert ss.final_input_budget(1500) == (16385 - 4096 - 1000) * 3 == 33_867
    set_limits(128000, 16384)  # gpt-4o-mini
    assert ss.final_input_budget(1500) == ss.MAX_FINAL_INPUT_CHARS
    set_limits(5000, 4096)  # tiny context: never below a workable floor
    assert ss.final_input_budget(1500) == 4_000
    reset_limits()


def test_notes_that_fit_are_left_alone():
    llm = FakeLLM()
    with patch.object(ss, "client", llm):
        assert ss.fit_notes(["a [S0]", "b [S1]"], 1000, cite=True) == ["a [S0]", "b [S1]"]
    assert llm.calls == []


def test_long_notes_are_combined_until_they_fit_and_keep_labels():
    parts = [f"### Part {i}\n- point [S{i}] " + "x" * 2000 for i in range(40)]  # ~80,000 chars
    llm = FakeLLM(combine_chars=600)
    with patch.object(ss, "client", llm):
        out = ss.fit_notes(parts, 10_000, cite=True)
    assert ss._joined_len(out) <= 10_000
    combines = llm.of("combine")
    assert combines and all(size <= ss.COMBINE_GROUP_CHARS + 2000 for _, size, _ in combines), "each call gets one group"
    assert set(re.findall(r"\[S\d+\]", "\n".join(out))) == {f"[S{i}]" for i in range(40)}, "no label lost"
    assert "[S0]" in combines[0][2] and "keep the section labels" in combines[0][2].lower()


def test_a_single_huge_note_is_split_first():
    huge = "\n".join(f"- line {i} [S{i}] " + "y" * 200 for i in range(200))  # ~45,000 chars in one part
    llm = FakeLLM()
    with patch.object(ss, "client", llm):
        out = ss.fit_notes([huge], 8_000, cite=True)
    assert ss._joined_len(out) <= 8_000 and len(llm.of("combine")) >= 4


def test_gives_up_with_a_plain_message_if_notes_dont_shrink():
    llm = FakeLLM(shrink=False)
    with patch.object(ss, "client", llm):
        try:
            ss.fit_notes(["z" * 30_000], 5_000, cite=False)
            raise AssertionError("expected AIGenerationError")
        except ss.AIGenerationError as e:
            assert str(e) == ss.TOO_LONG_MESSAGE
    rounds = len(llm.of("combine"))
    assert 0 < rounds, rounds


def test_a_large_merged_set_fits_a_small_context_model():
    set_limits(16385, 4096)  # gpt-3.5-turbo
    try:
        budget = ss.final_input_budget(mg.FINAL_MAX_TOKENS)
        sources = [
            MergedSource(n, f"book{n}.pdf", "pdf", None, [f"Book {n} chunk {i}. " + "t" * 900 for i in range(60)],
                         [(f"p. {i + 1}", None) for i in range(60)], document_id=n)
            for n in (1, 2, 3)
        ]  # ~165,000 characters
        llm = FakeLLM()
        with patch.object(ss, "client", llm):
            out = mg.generate_merged_summary(sources)
        final = llm.of("final")
        assert len(final) == 1 and final[0][1] <= budget + 2_000, (final[0][1], budget)
        assert llm.of("combine"), "rounds were needed"
        # Labels survive into the final citations, for every source.
        body = out.split("\n\n---\n\n")[1]
        assert "(1: p. 1" in body and "2: p. " in body and "3: p. " in body, body[:300]
    finally:
        reset_limits()


def test_a_huge_single_document_fits_too():
    reset_limits()  # unknown context: the 24,000-character fallback budget
    llm = FakeLLM()
    chunks = [f"Chunk {i}. " + "u" * 900 for i in range(360)]  # like a 220,000-character textbook
    with patch.object(ss, "client", llm):
        out = ss.generate_cited_summary(chunks, [(f"p. {i // 2 + 1}", None) for i in range(360)])
    assert llm.of("final")[0][1] <= ss.FALLBACK_FINAL_INPUT_CHARS + 2_000
    assert "(p. 1" in out
    plain = FakeLLM()
    with patch.object(ss, "client", plain):
        ss.generate_summary("Plain sentence about cells. " * 8_000)  # ~220,000 characters, no labels
    assert plain.of("combine") and plain.of("final")[0][1] <= ss.FALLBACK_FINAL_INPUT_CHARS + 2_000


def test_small_material_makes_no_extra_calls():
    llm = FakeLLM()
    with patch.object(ss, "client", llm):
        ss.generate_cited_summary(["Short text."] * 3, [("p. 1", None)] * 3)
    assert [c[0] for c in llm.calls] == ["final"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
