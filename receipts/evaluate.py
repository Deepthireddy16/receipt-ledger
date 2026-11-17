"""Measures how often the extraction is right.

Run:  python -m receipts.evaluate --ocr-dir <folder> --answers-dir <folder>

Two scores are reported for every field:
  strict     - the text must be exactly the same as the answer (after trimming spaces)
  normalized - the meaning must be the same (same date, same amount, same letters and digits)
"""

import argparse
import json
from pathlib import Path

from receipts.extract import PROMPT_VERSION, extract
from receipts.llm import CachedClient, LLMClient, gemini_from_env
from receipts.normalize import clean_text, parse_amount, parse_date
from receipts.schema import FIELD_NAMES
from receipts.sroie import Receipt, load_receipts, sample_receipts


def strict_match(predicted: str | None, truth: str) -> bool:
    return predicted is not None and predicted.strip() == truth.strip()


def normalized_match(field: str, predicted: str | None, truth: str) -> bool:
    if predicted is None:
        return False
    if field == "date":
        a, b = parse_date(predicted), parse_date(truth)
        if a and b:
            return a == b
    if field == "total":
        a, b = parse_amount(predicted), parse_amount(truth)
        if a is not None and b is not None:
            return a == b
    # Text fields, and dates or totals we could not parse, are compared as cleaned text.
    return clean_text(predicted) == clean_text(truth)


def score_receipt(predicted: dict[str, str | None], truth: dict[str, str | None]) -> dict[str, dict[str, bool]]:
    """Scores one receipt. Fields with no answer in the dataset are skipped."""
    scores = {}
    for field in FIELD_NAMES:
        if truth[field] is None:
            continue
        scores[field] = {
            "strict": strict_match(predicted[field], truth[field]),
            "normalized": normalized_match(field, predicted[field], truth[field]),
        }
    return scores


def run(receipts: list[Receipt], client: LLMClient) -> tuple[list[dict], dict]:
    rows = []
    for number, receipt in enumerate(receipts, start=1):
        extraction = extract(receipt.text, client)
        empty = dict.fromkeys(FIELD_NAMES)
        predicted = extraction.fields.model_dump() if extraction.fields else empty
        rows.append({
            "receipt_id": receipt.receipt_id,
            "predicted": predicted,
            "truth": receipt.truth,
            "scores": score_receipt(predicted, receipt.truth),
            "invalid_output": extraction.error,
            "latency_s": round(extraction.llm.latency_s, 3),
            "input_tokens": extraction.llm.input_tokens,
            "output_tokens": extraction.llm.output_tokens,
            "cached": extraction.llm.cached,
        })
        print(f"[{number}/{len(receipts)}] {receipt.receipt_id}")
    return rows, summarize(rows, client.name)


def summarize(rows: list[dict], model: str) -> dict:
    fields = {}
    for field in FIELD_NAMES:
        scored = [row["scores"][field] for row in rows if field in row["scores"]]
        fields[field] = {
            "count": len(scored),
            "strict": sum(s["strict"] for s in scored) / len(scored) if scored else None,
            "normalized": sum(s["normalized"] for s in scored) / len(scored) if scored else None,
        }
    all_correct = [all(s["normalized"] for s in row["scores"].values()) for row in rows if row["scores"]]
    latencies = [row["latency_s"] for row in rows if not row["cached"]]
    return {
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "receipts": len(rows),
        "invalid_outputs": sum(1 for row in rows if row["invalid_output"]),
        "fields": fields,
        "all_fields_correct_normalized": sum(all_correct) / len(all_correct) if all_correct else None,
        "mean_latency_s": sum(latencies) / len(latencies) if latencies else None,
        "input_tokens": sum(row["input_tokens"] or 0 for row in rows),
        "output_tokens": sum(row["output_tokens"] or 0 for row in rows),
    }


def print_summary(summary: dict) -> None:
    def pct(value):
        return "  n/a" if value is None else f"{value:6.1%}"

    print(f"\nModel: {summary['model']}   Prompt: {summary['prompt_version']}   Receipts: {summary['receipts']}")
    print(f"Invalid outputs: {summary['invalid_outputs']}")
    print(f"{'field':<10}{'count':>6}{'strict':>10}{'normalized':>12}")
    for field, s in summary["fields"].items():
        print(f"{field:<10}{s['count']:>6}{pct(s['strict']):>10}{pct(s['normalized']):>12}")
    print(f"All fields correct (normalized): {pct(summary['all_fields_correct_normalized'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate receipt extraction on SROIE.")
    parser.add_argument("--ocr-dir", required=True, help="folder with the OCR .txt files")
    parser.add_argument("--answers-dir", required=True, help="folder with the answer files")
    parser.add_argument("--n", type=int, default=50, help="how many receipts to test")
    parser.add_argument("--seed", type=int, default=7, help="controls which receipts are picked")
    parser.add_argument("--out", default="runs/stage1", help="where to save results")
    args = parser.parse_args()

    receipts = load_receipts(args.ocr_dir, args.answers_dir)
    if not receipts:
        raise SystemExit("No receipts found. Check the two folder paths.")
    sample = sample_receipts(receipts, args.n, args.seed)
    print(f"Found {len(receipts)} receipts, testing {len(sample)} (seed {args.seed}).")

    client = CachedClient(gemini_from_env(), cache_dir=".cache/llm")
    rows, summary = run(sample, client)
    summary["seed"] = args.seed

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "results.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print_summary(summary)
    print(f"\nSaved to {out}/results.jsonl and {out}/summary.json")


if __name__ == "__main__":
    main()
