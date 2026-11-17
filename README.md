# receipt-ledger

Reads receipts and turns them into bookkeeping records. Built in stages, and every stage is measured.

**Status: Stage 1 of 6 complete — field extraction and evaluation.**

## What Stage 1 does

1. Loads receipts from the SROIE dataset (public scanned receipts with known answers).
2. Sends the text of each receipt to a Gemini model and asks for four fields: company, date, address, total.
3. Checks the model's answer against a schema.
4. Compares each field with the known answer and reports accuracy.

## Results

gemini-3.5-flash-lite · 50 receipts · seed 7 · 0 invalid outputs in any run

| Field | v1 | v2 | v3 |
|---|---|---|---|
| company | 92.0% | 84.0% | 94.0% |
| date | 78.0% | 98.0% | 98.0% |
| address | 92.0% | 92.0% | 92.0% |
| total | 100.0% | 100.0% | 100.0% |
| **All four correct** | **68.0%** | **76.0%** | **88.0%** |

Scores above are normalized: the meaning must match (same calendar date, same amount, same letters
and digits). The strict score, where the text must match the label character for character, is in
the table further down and is discussed below.

Three prompt versions, each written after reading every error from the one before:

- **v1 → v2.** 10 of the 11 date errors were one cause: the model returned the time of day as well
  (`01/APR/2017 01:25:02` where the label is `01/APR/2017`). Telling it to give the date only took
  date from 78% to 98%. The same version also told the model to prefer a company's full legal name.
  That **made company worse**, 92% to 84%.
- **v2 → v3.** Reverted the company wording, kept the date wording. Company returned to 94%, which
  is one receipt different from v1 and therefore the same within noise on a 50-receipt sample.

The regression is the most useful result here. A prompt change that sounded obviously right cost 8
points, and the only reason that was visible is that each field is scored on its own.

### Why company cannot go much higher

The labels follow no single rule. One receipt wants the legal entity over the brand
(`GRAND COMPANIONS SDN BHD`, not `TONY ROMA'S`). Six others want the shop name over the legal
entity (`SANYU STATIONERY SHOP`, not `SANYU SUPPLY SDN BHD`). No instruction can satisfy both, so
v3 keeps the wording that is right more often.

### The remaining 8 errors are mostly the dataset

- Two address labels misspell words the model spelled correctly (`PARINDUSTRIAN`, `PEADANA`).
- One date label says `03 MAR 19` where the receipt plainly reads `03 MAR 18` (checked in the OCR file).
- One address label is truncated; the model's extra `57000 KL` is on the receipt.
- One address label is cleaned up while the OCR text holds the typo, so "copy exactly" cannot win.
- Three are the company convention above.

Further prompt tuning would mean matching the labels' own mistakes, so stage 1 stops here.

### Strict scores, and what the gap means

| Field | v3 strict | v3 normalized |
|---|---|---|
| company | 94.0% | 94.0% |
| date | 98.0% | 98.0% |
| address | 54.0% | 92.0% |
| total | 82.0% | 100.0% |

`python -m receipts.errors <results> --strict` lists the 28 fields where the meaning is right but
the text differs. Every one of them is explained:

- **All 8 total mismatches are the currency symbol, and it is in the label.** The label says
  `RM 5.00` or `$6.60`; the model returns `5.00` and `6.60`, which is what the prompt asks for. Two
  currencies appear in 50 receipts, so the schema needs a separate `currency` field. That is a
  stage 2 change.
- **All 20 address mismatches are whitespace or punctuation**, and several contain real newlines
  because the receipt prints the address over two lines. Harmless for a score, not harmless for a
  database column, so stage 2 collapses whitespace before storing.

Reporting strict only would have said the model is weak at addresses, which is false. Reporting
normalized only would have hidden the currency problem, which matters.

### Cost and speed

Measured on the v3 run, 50 receipts, one model call each:

| | |
|---|---|
| Mean call latency | 4.03 s |
| Input tokens | 26,860 (about 537 per receipt) |
| Output tokens | 4,462 (about 89 per receipt) |
| Wall-clock time | about 4 minutes |

The wall clock is longer than the latency because the client waits 5 seconds between calls to stay
inside the 15-requests-per-minute free-tier limit. Those 15 requests use roughly 9,000 tokens a
minute against a 250,000 limit, so requests per minute is the binding constraint and tokens are
not close. That matters for stage 2, where one receipt will take several model calls.

Token counts are reported rather than a cost in dollars, so the figure can be worked out from
whatever the current rate card says.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

1. Create a free API key in Google AI Studio (aistudio.google.com) and put it in `.env` as `GEMINI_API_KEY`.
2. Run `python -m receipts.check_setup`. It lists the models your key can use.
3. Pick a model from that list and put its name in `.env` as `GEMINI_MODEL`.
4. Run `python -m receipts.check_setup` again. It should say the test call worked.

**On model choice:** this free-tier key allows 20 requests a day on the full Flash models and 500
on the Lite ones. A 50-receipt run does not fit in 20, so the quota chose the model, not a
preference. Comparing Lite against Flash on a 20-receipt subset is the fair way to find out what
that costs in accuracy.

## Data

Download SROIE (Kaggle: `urbikn/sroie-datasetv2`) and unzip it into `data/`. The test split gives
`data/SROIE2019/test/box` (OCR text) and `data/SROIE2019/test/entities` (the known answers).

## Run

```bash
python -m pytest                                      # 11 tests, no API key needed
python -m receipts.evaluate --ocr-dir data/SROIE2019/test/box \
    --answers-dir data/SROIE2019/test/entities --n 50 --out runs/flash-lite-50-v3
python -m receipts.errors runs/flash-lite-50-v3/results.jsonl            # real errors
python -m receipts.errors runs/flash-lite-50-v3/results.jsonl --strict   # formatting differences
```

Answers are cached in `.cache/llm`, keyed by model name and prompt text, so repeating a run makes
no new API calls and changing the prompt never reuses an old answer.

## Privacy note

On the free tier of the Gemini API, Google may use what you send to improve its products. Only send
public data such as SROIE. Do not send your own receipts on the free tier.

## Files

| File | Job |
|---|---|
| `receipts/schema.py` | The four fields we want |
| `receipts/llm.py` | The only file that talks to a model; also the cache |
| `receipts/extract.py` | The prompt, and checking the model's answer |
| `receipts/normalize.py` | Reading dates and amounts from text |
| `receipts/sroie.py` | Loading the dataset |
| `receipts/evaluate.py` | Scoring and the report |
| `receipts/errors.py` | Lists wrong answers, and formatting differences with `--strict` |
| `runs/` | Results of every run, committed as evidence |
| `DECISIONS.md` | Every design choice, the alternative, the reason, and where it breaks |

## Next

Stage 2: a LangGraph workflow that validates the extracted fields, adds the `currency` field,
classifies the expense, turns each receipt into a balanced double-entry journal line, and sends
low-confidence cases for human review.
