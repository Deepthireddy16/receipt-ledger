# Decision log

Each entry: what was chosen, what the other option was, why, and where it breaks.
Read these before you run the code. Change any you disagree with, and write down why.

## Stage 1 — extraction and evaluation

### 1. Build the evaluation before the agent
- **Chose:** measure plain extraction first, with no agent, database, or API.
- **Other option:** build the full workflow first and test at the end.
- **Why:** every later stage claims to improve something. Without a starting number there is nothing to compare with.
- **Where it breaks:** this score covers extraction only. It says nothing about the full workflow yet.

### 2. Send OCR text, not the receipt image
- **Chose:** use the OCR text that comes with SROIE.
- **Other option:** send the image and let the model read it.
- **Why:** it tests one thing at a time. If the answer is wrong, the cause is extraction, not reading the image. Text also uses fewer tokens.
- **Where it breaks:** the dataset's OCR text is clean. A real photo needs OCR or image input first, and that adds errors this score does not show. Comparing text input with image input is a good later experiment.

### 3. All fields are optional strings
- **Chose:** the model returns text or null. Our own code turns text into dates and amounts.
- **Other option:** ask the model for a real date and a number.
- **Why:** null is safer than a guess, because a missing value can be sent to a person. Parsing in code is the same every time and can be unit tested. A model asked to reformat a date might change it.
- **Where it breaks:** `parse_date` only knows the formats in its list, and `parse_amount` reads "1.234,56" wrongly.

### 4. Ask for JSON in a schema, and still validate it
- **Chose:** Gemini's structured output with the Pydantic schema, then `model_validate_json` in our code.
- **Other option:** trust the API, or parse free text with regex.
- **Why:** the API setting makes bad JSON rare. Our own check means a bad answer is counted as `invalid_output` and the run continues.
- **Where it breaks:** valid JSON can still hold wrong values. The schema checks shape, not truth.

### 5. Two scores: strict and normalized
- **Chose:** report both for every field.
- **Other option:** exact match only, which is how the SROIE challenge scores.
- **Why:** strict match marks "25-12-2018" wrong when the answer is "25/12/2018". That is a format difference, not a wrong date. Normalized match compares meaning. Showing both is more honest than picking the higher one.
- **Where it breaks:** normalized match ignores punctuation and spacing, so it could accept two different addresses that only differ in punctuation. Dates are read day-first, which is an assumption about this dataset.

### 6. Temperature 0
- **Chose:** temperature 0.
- **Why:** the same receipt should give the same answer, so two runs can be compared.
- **Where it breaks:** it reduces randomness but the API does not promise identical output every time.

### 7. Cache every model answer on disk
- **Chose:** save each answer under a hash of model name + prompt.
- **Other option:** call the API every time.
- **Why:** the free tier has a daily limit. With a cache, changing the scoring code and re-running costs no calls. The hash includes the prompt, so a changed prompt never reuses an old answer.
- **Where it breaks:** latency for cached rows is the old saved value, so mean latency only counts fresh calls. If the provider updates a model without changing its name, the cache keeps the old answers.

### 8. Test a fixed random sample, not the whole test set
- **Chose:** 50 receipts picked with seed 7.
- **Other option:** all test receipts.
- **Why:** it fits in the free daily limit, and the seed means every run uses the same 50.
- **Where it breaks:** 50 is small. One receipt is 2 percentage points, so small differences between runs mean nothing. Always report the count next to the score.

### 9. One small interface for the model (`LLMClient`)
- **Chose:** the rest of the code calls `generate_json(prompt, schema)` and nothing else.
- **Other option:** call the Gemini SDK directly where needed.
- **Why:** tests run with a fake client and no API key. Changing provider later means editing one file.
- **Where it breaks:** the interface is text-only. Image input will need it to change.

### 10. Model name comes from `.env`
- **Chose:** no model name in the code.
- **Why:** free-tier model names and limits change. The model used is written into `summary.json` with every run.

### 11. Receipt text is wrapped in tags and marked as data
- **Chose:** the prompt puts the receipt inside `<receipt>` tags and says to ignore instructions inside it.
- **Why:** receipt text comes from outside and could contain instructions.
- **Where it breaks:** this is a first step, not a defence. It is not tested yet. Stage 6 tests it with receipts that contain hidden instructions.

## Not decided yet
- Expense categories (SROIE has none, so we will need to label a small set by hand).
- Which agent steps exist and when a person must review.
- Database tables.

## Stage 1 results and the v2 prompt

### 12. Prompt v2 came from reading every error, not from guessing
- **Chose:** run v1, print all 19 wrong fields, group them by cause, then change the prompt once.
- **Other option:** rewrite the prompt by intuition after seeing the scores.
- **Why:** the scores say a field is weak; only the errors say why. 10 of the 11 date errors were
  one cause (the model appended the time of day), which no score could have told us.
- **Where it breaks:** the v2 prompt is tuned on these 50 receipts. A different sample could show
  different causes, so the fix should be rechecked on fresh receipts before trusting it.

### 13. Three instructions changed at once, and that is still measurable
- **Chose:** change the date, company, and total instructions in the same version.
- **Why:** each field is scored separately, so a change to the date wording can only move the date
  score. The changes do not mix.
- **Where it breaks:** this holds because the fields are independent here. Changing a general rule,
  such as "do not fix spelling", would affect every field and would need its own run.

### 14. Some errors are wrong labels, and we count them anyway
- **Found:** 4 of 19 errors are dataset problems, not model problems. Three addresses differ only
  because the label has an OCR typo (`PARINDUSTRIAN`, `PEADANA`), and one receipt plainly reads
  `03 MAR 18` while the label says `03 MAR 19` (checked by reading the OCR file).
- **Chose:** leave them in the score and describe them in the README.
- **Other option:** drop them, or hand-correct the labels.
- **Why:** correcting labels because the model disagreed is how a benchmark gets quietly tuned to
  flatter the system. Reporting the real number with the reason is more useful than a higher one.
- **Where it breaks:** it means the reported accuracy understates the model slightly. The practical
  ceiling on this sample is about 92%, not 100%, and that should be said whenever the number is quoted.

### 15. Why gemini-3.5-flash-lite and not a full Flash model
- **Chose:** Flash Lite for the main run.
- **Why:** on this free-tier key the full Flash models allow 20 requests a day, which cannot cover a
  50-receipt run. The Lite models allow 500. The quota picked the model, not a preference.
- **Where it breaks:** a Lite model is weaker. The 20-request daily quota is exactly enough for a
  20-receipt comparison, so a like-for-like Lite against Flash run on the same 20 receipts is the
  fair way to find out what the quota costs in accuracy.

### 16. The company instruction in v2 made things worse, and we reverted it
- **Measured:** v1 company 92% -> v2 84%. The instruction to prefer the full legal name fixed 3
  receipts and broke 7. Six of the new errors were the same shop: the model answered
  `SANYU SUPPLY SDN BHD` where the label says `SANYU STATIONERY SHOP`. A seventh added a
  registration number: `CONTENTO (JM0761170-K)` for the label `CONTENTO`.
- **What it revealed:** the labels have no single rule for "company". One receipt wants the legal
  entity over the brand (`GRAND COMPANIONS SDN BHD`, not `TONY ROMA'S`); six want the shop name
  over the legal entity. No instruction can be right on both.
- **Chose:** revert company to the v1 wording in v3, keep the v2 date wording.
- **Other option:** keep tuning the company instruction until it beats 92%.
- **Why:** when the labels disagree with each other, more tuning is fitting to noise, not
  improving extraction. We take the wording that is right more often and write down why.
- **Where it breaks:** 92% is the ceiling this label convention allows, not the model's limit. A
  different dataset, or a real client with a stated rule for which name to use, would need
  measuring again from scratch.

### 17. One change per field, so a result can be attributed
- **Chose:** v3 changes the company wording only; the date and total wording carry over unchanged.
- **Why:** v2 changed three fields at once. That was safe because fields are scored separately,
  but it is only safe while changes stay inside one field. Reverting one field at a time keeps
  every number explainable.

### 18. `--strict` added to errors.py
- **Chose:** a second view that lists fields whose meaning is right but whose text differs.
- **Why:** total has been 100% normalized and 82% strict in every run, and the default error view
  could not show those 9 cases because they are not errors. Without seeing them we were guessing
  about the cause.

### 19. The currency belongs in its own field (found in the strict view)
- **Found:** all 8 of the total strict mismatches are the currency symbol, and it is in the label,
  not the model's answer: the label says `RM 5.00` or `$6.60` where the model returns `5.00` and
  `6.60`, which is what our prompt asked for. Two different currencies appear in 50 receipts.
- **Chose:** keep the prompt as it is, and add a `currency` field to the schema in stage 2.
- **Other option:** ask the model to include the symbol so the strict score rises.
- **Why:** an amount and its currency are two facts. A ledger has to do arithmetic on the amount,
  which means it must be a number, and it has to know the currency to keep the books straight.
  Joining them to score better on this benchmark would make the data worse for its real job.
- **Where it breaks:** total's strict score stays near 82% and will look like a weakness to anyone
  reading the table without this note. The note has to travel with the number.

### 20. Addresses need their whitespace collapsed before storage
- **Found:** all 20 address strict mismatches are spacing or punctuation. Several answers contain
  real newlines, because the receipt prints the address over two lines and we told the model to
  copy what it sees.
- **Chose:** leave extraction alone; collapse runs of whitespace when writing to the database in
  stage 2.
- **Why:** the newline is faithful to the receipt, so it is not an extraction error. It is a
  storage problem, and it belongs where storage is decided.
- **Where it breaks:** collapsing whitespace is lossy. If a later feature needs the original line
  breaks, the raw answer has to be kept alongside the cleaned one.

### 21. Stage 1 stops here, because the remaining errors are label problems
- **Measured:** v3 reaches 88% of receipts with all four fields correct (v1 was 68%).
- **Found:** of the 8 remaining field errors, 5 are dataset problems (two labels misspell words the
  model spelled correctly, one date label contradicts the receipt, one address label is truncated,
  one label is cleaned while the OCR text has the typo). The other 3 are the inconsistent company
  convention described in entry 16.
- **Chose:** stop tuning the prompt and move to stage 2.
- **Why:** further gains on this sample would come from matching the labels' own mistakes. That
  improves the score and nothing else.
- **Where it breaks:** 88% is specific to these 50 receipts, this model, and this prompt. It is a
  starting point for stage 2, not a claim about receipts in general.
