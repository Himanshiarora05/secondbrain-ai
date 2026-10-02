"""Offline checks for flashcard source citations (mocked LLM, no DB, no Chroma data, no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_flashcard_citations.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from types import SimpleNamespace

# The signed-in user the route functions are called for (routes take it from get_current_user).
TEST_USER = SimpleNamespace(id=1)

from app.services.ai import flashcard_service as fs
from app.routes import study
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.flashcard import Flashcard

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"
PAGE = "https://en.wikipedia.org/wiki/Mitochondrial_matrix"


def _fake_llm(reply_for):
    """Mock client whose JSON reply depends on the prompt; records every user prompt."""
    calls = []

    def create(**kwargs):
        user = kwargs["messages"][-1]["content"]
        calls.append({"system": kwargs["messages"][0]["content"], "user": user})
        msg = MagicMock()
        msg.content = reply_for(user)
        resp = MagicMock()
        resp.choices = [MagicMock(message=msg)]
        return resp

    client = MagicMock()
    client.chat.completions.create.side_effect = create
    return client, calls


def _labels_in(prompt):
    return [int(n) for n in re.findall(r"\[S(\d+)\]", prompt)]


def _one_card_per_label(prompt):
    """Reply with one card per label the model was shown, citing that label."""
    return json.dumps([
        {"question": f"What is in section {i}?", "answer": f"Fact {i}.", "source": f"S{i}"}
        for i in _labels_in(prompt)
    ])


# ─── Citations built from stored chunk data ───

def test_youtube_citations_link_to_the_moment():
    cites = fs.build_chunk_citations("youtube", VIDEO, "YouTube: abcdefghijk",
                                     [("Intro.", 0), ("Graphs.", 125), ("No time.", None)])
    assert cites[0] == ("00:00", VIDEO + "&t=0s")
    assert cites[1] == ("02:05", VIDEO + "&t=125s")
    assert cites[2] is None


def test_website_citations_link_to_the_page():
    cites = fs.build_chunk_citations("website", PAGE, "Mitochondrial matrix - Wikipedia", [("a", None), ("b", None)])
    assert cites == [("Mitochondrial matrix - Wikipedia", PAGE)] * 2


def test_pptx_citations_track_slides_across_chunks():
    chunks = [
        ("[Slide 1: Intro]\nWelcome to biology.", None),
        ("more about the intro. [Slide 2: Cells]\nCells are units of life. [Slide 3: DNA]\nDNA stores info.", None),
        ("DNA is a double helix and it continues here.", None),   # starts mid-slide 3
        ("[Slide 4: Proteins]\nProteins fold.", None),           # starts exactly on a marker
        ("[Notes: speaker notes only]", None),                    # no marker, still slide 4
    ]
    cites = fs.build_chunk_citations("pptx", None, "deck.pptx", chunks)
    assert cites == [("Slide 1", None), ("Slides 1–3", None), ("Slide 3", None), ("Slide 4", None), ("Slide 4", None)], cites


def test_pdf_and_docx_get_no_citation():
    for source_type in ("pdf", "docx"):
        assert fs.build_chunk_citations(source_type, None, "notes", [("text", None)] * 3) == [None] * 3


# ─── Generation ───

def test_cards_carry_the_citation_of_their_label():
    chunks = ["Intro to graphs.", "Vertices and edges.", "Adjacency lists."]
    cites = fs.build_chunk_citations("youtube", VIDEO, "t", [(c, s) for c, s in zip(chunks, [0, 46, 89])])
    client, calls = _fake_llm(lambda _: json.dumps([
        {"question": "What is a graph made of?", "answer": "Vertices and edges.", "source": "S1"},
        {"question": "How are graphs stored?", "answer": "Adjacency lists.", "source": "[S2]"},
        {"question": "Invented label?", "answer": "Yes.", "source": "S9"},
        {"question": "No label?", "answer": "None given."},
    ]))
    # One call that sees every chunk, so the fixed reply's labels are all in its batch.
    with patch.object(fs, "client", client), patch.object(fs, "CARDS_PER_CALL", 10):
        cards = fs.generate_cited_flashcards(chunks, cites, count=10)

    assert len(calls) == 1
    assert "[S0] Intro to graphs." in calls[0]["user"] and "'source'" in calls[0]["system"]
    by_q = {c["question"]: c for c in cards}
    assert by_q["What is a graph made of?"]["source_label"] == "00:46"
    assert by_q["What is a graph made of?"]["source_url"] == VIDEO + "&t=46s"
    assert by_q["How are graphs stored?"]["source_label"] == "01:29"
    assert by_q["Invented label?"]["source_label"] is None and by_q["Invented label?"]["source_url"] is None
    assert by_q["No label?"]["source_label"] is None
    for card in cards:
        assert "[S" not in card["question"] + card["answer"]


def test_label_outside_the_batch_is_dropped():
    """The model only saw one batch; a label from another batch must not be trusted."""
    chunks = [f"Topic {i}. " + "x" * 780 for i in range(20)]
    cites = [(f"C{i}", f"https://example.com/{i}") for i in range(20)]
    client, calls = _fake_llm(lambda prompt: json.dumps([
        {"question": f"Q about batch starting S{_labels_in(prompt)[0]}", "answer": "A.", "source": "S19"
         if _labels_in(prompt)[0] == 0 else f"S{_labels_in(prompt)[0]}"},
    ]))
    with patch.object(fs, "client", client):
        cards = fs.generate_cited_flashcards(chunks, cites, count=6)
    first_batch_card = next(c for c in cards if c["question"] == "Q about batch starting S0")
    assert first_batch_card["source_label"] is None, first_batch_card
    others = [c for c in cards if c is not first_batch_card]
    assert others and all(c["source_label"] for c in others), "in-batch labels must still be cited"


def test_long_source_is_covered_start_to_end():
    chunks = [f"Topic {i}. " + "x" * 780 for i in range(40)]  # ~32k chars, many batches
    cites = [(f"{i:02d}:00", f"{VIDEO}&t={i * 60}s") for i in range(40)]
    client, calls = _fake_llm(_one_card_per_label)
    with patch.object(fs, "client", client):
        cards = fs.generate_cited_flashcards(chunks, cites, count=10)

    assert len(cards) == 10
    assert len(calls) == 4, f"expected ceil(10/3)=4 sampled batches, got {len(calls)} calls"
    cited = sorted(int(c["source_label"].split(":")[0]) for c in cards)
    assert cited[0] < 5 and cited[-1] > 34, f"cards should span the whole source, got minutes {cited}"
    first_call, last_call = _labels_in(calls[0]["user"]), _labels_in(calls[-1]["user"])
    assert first_call[0] == 0 and last_call[-1] == 39, "first and last batches must be included"
    assert len({c["question"] for c in cards}) == 10
    minutes = [int(c["source_label"].split(":")[0]) for c in cards]
    assert minutes == sorted(minutes), f"deck should be in source order, got {minutes}"


def test_short_source_is_covered_even_if_the_model_favours_the_start():
    """Like the real 12-slide deck: the model writes every card from the first section it sees."""
    chunks = [f"[Slide {2 * i + 1}: T] Fact {i}. [Slide {2 * i + 2}: U] More." for i in range(5)]
    cites = fs.build_chunk_citations("pptx", None, "deck.pptx", [(c, None) for c in chunks])

    def favour_start(prompt):
        first = _labels_in(prompt)[0]
        return json.dumps([
            {"question": f"Card {n} from S{first}?", "answer": "A.", "source": f"S{first}"} for n in range(4)
        ])

    client, calls = _fake_llm(favour_start)
    with patch.object(fs, "client", client):
        cards = fs.generate_cited_flashcards(chunks, cites, count=8)

    assert len(calls) == 3, len(calls)  # ceil(8/3) groups over 5 chunks
    shown = sorted(i for call in calls for i in _labels_in(call["user"]))
    assert shown == [0, 1, 2, 3, 4], "every chunk must be shown to the model exactly once"
    # Groups are chunks [0, 1], [2], [3, 4]; the model cites the first chunk of each group,
    # so the deck must include cards from the first, middle and last group.
    labels = {c["source_label"] for c in cards}
    assert labels == {"Slides 1–2", "Slides 5–6", "Slides 7–8"}, labels


def test_duplicate_questions_are_removed():
    chunks = ["A.", "B."]
    client, _ = _fake_llm(lambda _: json.dumps([
        {"question": "What is ATP?", "answer": "Energy.", "source": "S0"},
        {"question": "what is atp", "answer": "Energy again.", "source": "S1"},
    ]))
    with patch.object(fs, "client", client):
        cards = fs.generate_cited_flashcards(chunks, [None, None], count=5)
    assert [c["question"] for c in cards] == ["What is ATP?"]


def test_parser_keeps_source_and_accepts_replies_without_it():
    cards = fs._parse_flashcard_json('```json\n[{"question": "Q1", "answer": "A1", "source": "S2"}, {"question": "Q2", "answer": "A2"}]\n```')
    assert cards == [{"question": "Q1", "answer": "A1", "source": "S2"}, {"question": "Q2", "answer": "A2"}]


# ─── Route ───

def _mock_db(doc, chunk_rows, saved):
    """db.query(Model) chains for the flashcards route; `saved` collects added cards."""
    db = MagicMock()

    def query(model):
        q = MagicMock()
        if model is Document:
            q.filter.return_value.first.return_value = doc
        elif model is Chunk:
            q.filter.return_value.order_by.return_value.all.return_value = chunk_rows
        elif model is Flashcard:
            for i, card in enumerate(saved, start=1):
                card.id = i
            q.filter.return_value.order_by.return_value.all.side_effect = lambda: list(saved)
        return q

    db.query.side_effect = query
    db.add_all.side_effect = lambda cards: saved.extend(cards)
    return db


def test_route_saves_and_returns_citations():
    doc = MagicMock(id=5, content="Graphs. Vertices.", source_type="youtube", source_url=VIDEO)
    doc.filename = "YouTube: abcdefghijk"
    chunk_rows = [MagicMock(content="Graphs.", start_seconds=0), MagicMock(content="Vertices.", start_seconds=125)]
    saved = []
    db = _mock_db(doc, chunk_rows, saved)
    client, _ = _fake_llm(_one_card_per_label)
    with patch.object(fs, "client", client):
        result = study.create_flashcards(5, count=5, db=db, user=TEST_USER)

    assert [(c.source_label, c.source_url) for c in saved] == [
        ("00:00", VIDEO + "&t=0s"), ("02:05", VIDEO + "&t=125s"),
    ]
    # Cards also carry their review schedule (tests/test_spaced_repetition.py); only the citation fields matter here.
    fields = ("id", "question", "answer", "source_label", "source_url")
    assert [{k: c[k] for k in fields} for c in result["flashcards"]] == [
        {"id": 1, "question": "What is in section 0?", "answer": "Fact 0.", "source_label": "00:00", "source_url": VIDEO + "&t=0s"},
        {"id": 2, "question": "What is in section 1?", "answer": "Fact 1.", "source_label": "02:05", "source_url": VIDEO + "&t=125s"},
    ]


def test_route_without_chunks_falls_back_to_document_text():
    doc = MagicMock(id=6, content="Some old document text.", source_type="pdf", source_url=None)
    doc.filename = "old.pdf"
    saved = []
    db = _mock_db(doc, [], saved)
    with patch.object(study, "generate_flashcards", return_value=[{"question": "Q?", "answer": "A."}]) as old:
        result = study.create_flashcards(6, count=3, db=db, user=TEST_USER)
    old.assert_called_once_with("Some old document text.", count=3)
    assert result["flashcards"][0]["source_label"] is None and result["flashcards"][0]["source_url"] is None


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
