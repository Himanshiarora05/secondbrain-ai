"""Offline checks for merged summaries: numbered citations, the sources list, per-source map
batches, and the save rules (mocked LLM, in-memory SQLite, no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_merged_summary.py
"""
import json
import os
import re
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

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
from app.models import Document, Chunk, Summary, MergedSummary, User
from app.routes import merged_sets as ms
from app.routes.merged_sets import CreateMergedSetRequest
from app.services.ai import merged_service as mg
from app.services.ai import summary_service as ss
from app.services.ai.merged_service import MergedSource

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"
PAGE = "https://example.org/cells"


class FakeLLM:
    """Records prompts. Map calls echo each label they were shown; the final call returns `final`."""

    def __init__(self, final="- A point [S0]", fail=None):
        self.final, self.fail, self.calls = final, fail, []
        self.chat = MagicMock()
        self.chat.completions.create.side_effect = self._create

    def _create(self, **kw):
        system, user = kw["messages"][0]["content"], kw["messages"][1]["content"]
        self.calls.append((system, user, kw.get("max_tokens")))
        if self.fail:
            raise self.fail
        if system.startswith("You are an expert study assistant creating one exam revision summary"):
            text = self.final
        else:
            text = "\n".join(f"- note {label}" for label in re.findall(r"\[S\d+\]", user))
        return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content=text))])

    def map_calls(self):
        return [c for c in self.calls if not c[0].startswith("You are an expert study assistant creating one")]


def mixed_sources():
    return [
        MergedSource(1, "Graph_PPT.pdf", "pdf", None, ["Graphs are pairs.", "Degree counts edges."],
                     [("p. 1", None), ("pp. 2–3", None)], document_id=11),
        MergedSource(2, "quantum.pptx", "pptx", None, ["[Slide 4] Qubits."], [("Slide 4", None)], document_id=12),
        MergedSource(3, "YouTube: abcdefghijk", "youtube", VIDEO, ["Intro to graphs."],
                     [("02:05", f"{VIDEO}&t=125s")], document_id=13),
        MergedSource(4, "Cells [biology]", "website", PAGE, ["Cells have nuclei."], [("Cells [biology]", PAGE)], document_id=14),
        MergedSource(5, "notes.docx", "docx", None, ["Word notes."], [None], document_id=15),
    ]


def test_citation_says_which_source():
    s = mixed_sources()
    assert mg.merged_citation(s[0], ("p. 1", None)) == ("1: p. 1", None)
    assert mg.merged_citation(s[1], ("Slide 4", None)) == ("2: Slide 4", None)
    assert mg.merged_citation(s[2], ("02:05", "u")) == ("3: 02:05", "u")
    assert mg.merged_citation(s[3], ("Cells [biology]", PAGE)) == ("4", PAGE)
    assert mg.merged_citation(s[4], None) == ("5", None)
    assert mg.merged_citation(s[0], None) == ("1", None), "a PDF without pages still names its source"


def test_plain_citations_are_grouped_by_source():
    assert mg.join_by_source(["1: p. 3", "1: pp. 5–6", "2: Slide 4", "3"]) == "1: p. 3, pp. 5–6; 2: Slide 4; 3"
    assert mg.join_by_source(["2: Slide 4", "1: p. 1", "2: Slide 6"]) == "2: Slide 4, Slide 6; 1: p. 1", "first-seen order"
    labels = [("1: p. 1", None), ("1: pp. 2–3", None), ("2: Slide 4", None)]
    assert ss.replace_labels("- Point [S0][S1][S2]", labels, join_plain=mg.join_by_source) == "- Point (1: p. 1, pp. 2–3; 2: Slide 4)"
    assert ss.replace_labels("- Point [S0][S1]", [("p. 1", None), ("p. 2", None)]) == "- Point (p. 1; p. 2)", "per-document output unchanged"


def test_labels_in_the_models_own_parentheses_are_not_doubled():
    pages = [("1: p. 1", None), ("1: pp. 2–3", None), ("3: 02:05", "https://v/t=125")]
    cases = {
        "- A ([S0]).": "- A (1: p. 1).",
        "- B ( [S0][S1] )": "- B (1: p. 1, pp. 2–3)",
        "- C ([S2])": "- C ([3: 02:05](https://v/t=125))",
        "- D ([S2][S0])": "- D [3: 02:05](https://v/t=125) (1: p. 1)",
        "- E ([S9])": "- E",
        "- F (see [S0])": "- F (see (1: p. 1))",
    }
    for text, expected in cases.items():
        got = ss.replace_labels(text, pages, join_plain=mg.join_by_source)
        assert got == expected, (text, got)
    assert ss.replace_labels("- Point ([S0])", [("p. 4", None)]) == "- Point (p. 4)", "per-document too"


def test_inline_latex_delimiters_are_removed():
    assert mg.plain_inline_math(r"A graph \(G = (V, E)\) has order \(|V|\).") == "A graph G = (V, E) has order |V|."
    assert mg.plain_inline_math(r"Keep \[S0\] and \begin{x} alone") == r"Keep \[S0\] and \begin{x} alone"


def test_sources_list_is_built_by_code():
    text = mg.sources_list(mixed_sources())
    assert text.splitlines() == [
        "**Sources**",
        "",
        "1. Graph\\_PPT.pdf — PDF",
        "2. quantum.pptx — PowerPoint",
        f"3. [YouTube: abcdefghijk]({VIDEO}) — YouTube video",
        f"4. [Cells \\[biology\\]]({PAGE}) — Web page",
        "5. notes.docx — Word document",
    ], text


def test_small_set_is_one_call_with_numbered_citations():
    llm = FakeLLM(final=(
        "# Revision\n"
        "- Graphs are pairs, also shown in the video [S0][S3]\n"
        "- Degree and qubits [S1, S2]\n"
        "- Cells have nuclei [S4]\n"
        "- From the Word notes \\[S5\\]\n"
        "- Made-up [S99]"
    ))
    with patch.object(ss, "client", llm):
        out = mg.generate_merged_summary(mixed_sources())
    assert len(llm.calls) == 1, len(llm.calls)
    system, user, max_tokens = llm.calls[0]
    assert "organised by topic" in system and "[S3]" in system, "merged prompt with the citation rule"
    assert "'Source 1'" in system and "never write the [S0]" in system, "sources are named by number, not label"
    assert "not LaTeX" in system
    assert max_tokens == mg.FINAL_MAX_TOKENS + ss.REASONING_ALLOWANCE
    for heading in ("## Source 1: Graph_PPT.pdf (PDF)", "## Source 3: YouTube: abcdefghijk (YouTube video)",
                    "## Source 5: notes.docx (Word document)"):
        assert heading in user, heading
    assert "[S0] Graphs are pairs." in user and "[S5] Word notes." in user, "labels run across all sources"

    sources, body = out.split("\n\n---\n\n")
    assert sources.startswith("**Sources**\n\n1. Graph\\_PPT.pdf — PDF")
    assert body.splitlines() == [
        "# Revision",
        f"- Graphs are pairs, also shown in the video [3: 02:05]({VIDEO}&t=125s) (1: p. 1)",
        "- Degree and qubits (1: pp. 2–3; 2: Slide 4)",
        f"- Cells have nuclei [4]({PAGE})",
        "- From the Word notes (5)",
        "- Made-up",
    ], body


def test_long_sources_are_mapped_one_source_at_a_time():
    big = MergedSource(1, "big.pdf", "pdf", None, [f"Big chunk {i}. " + "x" * 900 for i in range(12)],
                       [(f"p. {i + 1}", None) for i in range(12)], document_id=1)
    other = MergedSource(2, "other.pdf", "pdf", None, [f"Other chunk {i}. " + "y" * 900 for i in range(5)],
                         [(f"p. {i + 1}", None) for i in range(5)], document_id=2)
    small = MergedSource(3, "small.pptx", "pptx", None, ["[Slide 1] Short."], [("Slide 1", None)], document_id=3)
    llm = FakeLLM(final="- Point [S0][S12][S17]")
    with patch.object(ss, "client", llm):
        out = mg.generate_merged_summary([big, other, small])
    maps = llm.map_calls()
    assert len(maps) >= 5 and len(llm.calls) == len(maps) + 1, len(maps)
    for _, user, _ in maps:
        labels = {int(n) for n in re.findall(r"\[S(\d+)\]", user)}
        assert labels <= set(range(12)) or labels <= set(range(12, 17)), f"a map batch mixed sources: {sorted(labels)}"
    final_user = llm.calls[-1][1]
    assert "## Source 3: small.pptx (PowerPoint)\n[S17] [Slide 1] Short." in final_user, "a short source goes in as is"
    assert "x" * 900 not in final_user, "long sources reach the final step only as notes"
    assert out.endswith("- Point (1: p. 1; 2: p. 1; 3: Slide 1)"), out


# ─── Route (in-memory SQLite) ───

def fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    # The signed-in user the routes are called for; add_doc gives it every document.
    owner = User(email="owner@example.com", password_hash="not-used")
    db.add(owner)
    db.commit()
    db.info["user"] = owner
    return db


def add_doc(db, name, source_type, chunks, pages=None, starts=None, url=None):
    doc = Document(user_id=db.info["user"].id, file_id=f"f-{name}", filename=name, content=" ".join(chunks), source_type=source_type, source_url=url)
    db.add(doc)
    db.flush()
    for i, text in enumerate(chunks):
        p = pages[i] if pages else (None, None)
        db.add(Chunk(document_id=doc.id, content=text, chroma_id=f"{doc.id}-{i}", page_start=p[0], page_end=p[1],
                     start_seconds=starts[i] if starts else None))
    db.commit()
    return doc.id


def library(db):
    pdf = add_doc(db, "Graph_PPT.pdf", "pdf", ["Graphs are pairs.", "Degree counts edges."], pages=[(1, 1), (2, 3)])
    ppt = add_doc(db, "quantum.pptx", "pptx", ["[Slide 1] Qubits.", "[Slide 2] Gates."])
    vid = add_doc(db, "YouTube: abcdefghijk", "youtube", ["Intro.", "Later."], starts=[5, 125], url=VIDEO)
    db.add(Summary(document_id=pdf, content="the PDF's own summary"))
    db.commit()
    return pdf, ppt, vid


def post(db, set_id, regenerate=False):
    try:
        return ms.create_merged_summary(set_id, regenerate=regenerate, db=db, user=db.info["user"])
    except HTTPException as e:
        return e


def test_route_generates_saves_and_reuses():
    db = fresh_db()
    pdf, ppt, vid = library(db)
    set_id = ms.create_merged_set(CreateMergedSetRequest(document_ids=[pdf, ppt, vid]), db=db, user=db.info["user"])["merged_set"]["id"]
    try:
        ms.get_merged_summary(set_id, db=db, user=db.info["user"])
        raise AssertionError("expected 404 before generating")
    except HTTPException as e:
        assert e.status_code == 404

    llm = FakeLLM(final="- Graphs [S0]\n- Gates [S3]\n- Later in the video [S5]")
    with patch.object(ss, "client", llm):
        res = post(db, set_id)
    assert len(llm.calls) == 1
    assert "(1: p. 1)" in res["summary"] and "(2: Slide 2)" in res["summary"]
    assert f"[3: 02:05]({VIDEO}&t=125s)" in res["summary"], res["summary"]
    assert res["stale"] is False
    saved = db.query(MergedSummary).one()
    assert json.loads(saved.document_ids) == [pdf, ppt, vid] and saved.content == res["summary"]

    with patch.object(ss, "client", FakeLLM(final="- Should not be used [S0]")) as again:
        assert post(db, set_id)["summary"] == res["summary"]
    assert again.calls == [], "an existing summary is returned without calling the AI"

    with patch.object(ss, "client", FakeLLM(final="- New version [S1]")):
        regenerated = post(db, set_id, regenerate=True)["summary"]
    assert regenerated.endswith("- New version (1: pp. 2–3)"), regenerated
    assert db.query(MergedSummary).count() == 1 and db.query(MergedSummary).one().content == regenerated
    assert db.query(Summary).one().content == "the PDF's own summary", "the document's own summary is untouched"
    assert ms.get_merged_set(set_id, db=db, user=db.info["user"])["has_summary"] is True


def test_failure_keeps_the_existing_summary():
    db = fresh_db()
    pdf, ppt, _ = library(db)
    set_id = ms.create_merged_set(CreateMergedSetRequest(document_ids=[pdf, ppt]), db=db, user=db.info["user"])["merged_set"]["id"]
    with patch.object(ss, "client", FakeLLM(final="- First [S0]")):
        first = post(db, set_id)["summary"]
    with patch.object(ss, "client", FakeLLM(fail=RuntimeError("boom"))), patch.object(ss, "logger"):
        res = post(db, set_id, regenerate=True)
    assert isinstance(res, HTTPException) and res.status_code == 502, res
    assert res.detail.endswith("The existing merged summary was not changed."), res.detail
    assert db.query(MergedSummary).one().content == first


def test_deleted_member_makes_it_stale_until_regenerated():
    db = fresh_db()
    pdf, ppt, vid = library(db)
    set_id = ms.create_merged_set(CreateMergedSetRequest(document_ids=[pdf, ppt, vid]), db=db, user=db.info["user"])["merged_set"]["id"]
    with patch.object(ss, "client", FakeLLM(final="- Gates [S3]")):
        post(db, set_id)
    db.delete(db.get(Document, pdf))
    db.commit()
    db.expire_all()
    assert ms.get_merged_summary(set_id, db=db, user=db.info["user"])["stale"] is True
    assert ms.get_merged_set(set_id, db=db, user=db.info["user"])["summary_stale"] is True
    with patch.object(ss, "client", FakeLLM(final="- Gates [S1]")):
        res = post(db, set_id, regenerate=True)
    assert res["stale"] is False
    assert "(1: Slide 2)" in res["summary"], "the remaining sources are renumbered from 1"
    assert res["summary"].startswith("**Sources**\n\n1. quantum.pptx — PowerPoint\n2. [YouTube")

    db.delete(db.get(Document, vid))
    db.commit()
    res = post(db, set_id, regenerate=True)
    assert isinstance(res, HTTPException) and res.status_code == 400 and "fewer than 2" in res.detail


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
