"""Loads the SROIE receipt dataset from disk.

Each receipt has two files with the same name:
  - an OCR file: one line per piece of text, "x1,y1,x2,y2,x3,y3,x4,y4,TEXT"
  - an answer file: JSON with company, date, address, total
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

from receipts.schema import FIELD_NAMES


@dataclass
class Receipt:
    receipt_id: str
    text: str
    truth: dict[str, str | None]


def read_ocr_text(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(",", 8)  # the text itself may contain commas, so split only 8 times
        if len(parts) == 9 and parts[8].strip():
            lines.append(parts[8].strip())
    return "\n".join(lines)


def load_receipts(ocr_dir: str | Path, answers_dir: str | Path) -> list[Receipt]:
    ocr_dir, answers_dir = Path(ocr_dir), Path(answers_dir)
    receipts = []
    for answer_path in sorted(answers_dir.iterdir()):
        if answer_path.suffix not in {".txt", ".json"}:
            continue
        ocr_path = ocr_dir / f"{answer_path.stem}.txt"
        if not ocr_path.exists():
            continue
        answers = json.loads(answer_path.read_text(encoding="utf-8", errors="replace"))
        truth = {name: (answers.get(name) or None) for name in FIELD_NAMES}
        receipts.append(Receipt(answer_path.stem, read_ocr_text(ocr_path), truth))
    return receipts


def sample_receipts(receipts: list[Receipt], n: int, seed: int) -> list[Receipt]:
    """Picks n receipts at random. The same seed always picks the same receipts."""
    if n >= len(receipts):
        return receipts
    return random.Random(seed).sample(receipts, n)
