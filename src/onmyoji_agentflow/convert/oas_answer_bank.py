"""Bind the pinned OAS Answer corpus without importing upstream code."""
import csv
import hashlib
import io
from pathlib import Path


ANSWER_BANK = "OAS_ANSWER_BANK"
CORPUS = "tasks/DemonEncounter/data/data.csv"
PINS = {
    "tasks/DemonEncounter/data/answer.py": "0057f6bacb901f427847473483a20d085d178e82d31f39d4def5a4f2bb91af7d",
    CORPUS: "41d87c913e24d2ba15c7e3688d0b84e8aa051c05668cc81253a60c723f60f5ff",
}


def bind_answer_bank(raw, source_root):
    contents = {}
    for name, expected in PINS.items():
        text = (Path(source_root) / name).read_text(encoding="utf-8-sig")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"Answer source fingerprint mismatch: {name}")
        contents[name] = text
    reader = csv.reader(io.StringIO(contents[CORPUS]))
    if next(reader, None) != ["question", "answer"]:
        raise ValueError("Answer question bank has an unexpected header")
    raw.setdefault("inline_resources", {})[ANSWER_BANK] = {"type": "answer_bank", "rows": list(reader)}
