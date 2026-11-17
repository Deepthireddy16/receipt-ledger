"""Prints the wrong answers from a run, so you can read the mistakes yourself.

Run:  python -m receipts.errors runs/stage1/results.jsonl
      python -m receipts.errors runs/stage1/results.jsonl --strict

By default it shows real errors: fields where the meaning is wrong.
With --strict it shows the opposite: fields whose meaning is right but whose text
differs from the label. Those are formatting differences, not mistakes, and they are
what makes the strict score lower than the normalized one.
"""

import json
import sys


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    path = args[0] if args else "runs/stage1/results.jsonl"
    strict_only = "--strict" in sys.argv

    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]

    shown = 0
    for row in rows:
        for field, score in row["scores"].items():
            if strict_only:
                # Right meaning, different text.
                show = score["normalized"] and not score["strict"]
            else:
                show = not score["normalized"]
            if show:
                shown += 1
                print(f"{row['receipt_id']}  {field}")
                print(f"    predicted: {row['predicted'][field]!r}")
                print(f"    truth:     {row['truth'][field]!r}")

    label = "formatting differences" if strict_only else "wrong fields"
    print(f"\n{shown} {label} in {len(rows)} receipts.")


if __name__ == "__main__":
    main()
