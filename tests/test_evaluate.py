import json

from pydantic import BaseModel

from receipts.evaluate import normalized_match, run, score_receipt, strict_match
from receipts.llm import CachedClient, LLMResult
from receipts.sroie import load_receipts, sample_receipts


class FakeClient:
    """Stands in for the real model. Returns whatever text we give it."""

    name = "fake"

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def generate_json(self, prompt: str, schema: type[BaseModel]) -> LLMResult:
        self.calls += 1
        return LLMResult(text=self.text, latency_s=0.01, input_tokens=10, output_tokens=5)


def make_dataset(tmp_path, count=3):
    ocr, answers = tmp_path / "box", tmp_path / "entities"
    ocr.mkdir()
    answers.mkdir()
    for i in range(count):
        (ocr / f"r{i}.txt").write_text("1,2,3,4,5,6,7,8,ABC SHOP, KL\n1,2,3,4,5,6,7,8,TOTAL 12.50\n")
        (answers / f"r{i}.txt").write_text(json.dumps(
            {"company": "ABC SHOP", "date": "25/12/2018", "address": "1, JALAN A", "total": "12.50"}))
    return ocr, answers


def test_strict_and_normalized_differ():
    assert not strict_match("25-12-2018", "25/12/2018")
    assert normalized_match("date", "25-12-2018", "25/12/2018")
    assert normalized_match("total", "RM12.5", "12.50")
    assert not normalized_match("total", "12.60", "12.50")
    assert not normalized_match("company", None, "ABC")


def test_fields_without_an_answer_are_skipped():
    truth = {"company": "ABC", "date": None, "address": None, "total": "1.00"}
    predicted = {"company": "ABC", "date": "x", "address": None, "total": "2.00"}
    scores = score_receipt(predicted, truth)
    assert set(scores) == {"company", "total"}
    assert scores["company"]["strict"] and not scores["total"]["normalized"]


def test_loader_keeps_commas_inside_text(tmp_path):
    ocr, answers = make_dataset(tmp_path)
    receipts = load_receipts(ocr, answers)
    assert len(receipts) == 3
    assert receipts[0].text.splitlines()[0] == "ABC SHOP, KL"


def test_sampling_is_repeatable(tmp_path):
    ocr, answers = make_dataset(tmp_path, count=10)
    receipts = load_receipts(ocr, answers)
    first = [r.receipt_id for r in sample_receipts(receipts, 4, seed=7)]
    second = [r.receipt_id for r in sample_receipts(receipts, 4, seed=7)]
    assert first == second


def test_full_run_with_fake_model(tmp_path):
    ocr, answers = make_dataset(tmp_path)
    reply = json.dumps({"company": "ABC SHOP", "date": "25-12-2018", "address": None, "total": "12.5"})
    rows, summary = run(load_receipts(ocr, answers), FakeClient(reply))
    assert summary["fields"]["company"]["strict"] == 1.0
    assert summary["fields"]["date"]["strict"] == 0.0
    assert summary["fields"]["date"]["normalized"] == 1.0
    assert summary["fields"]["address"]["normalized"] == 0.0
    assert summary["all_fields_correct_normalized"] == 0.0


def test_invalid_model_output_is_counted_not_crashed(tmp_path):
    ocr, answers = make_dataset(tmp_path)
    rows, summary = run(load_receipts(ocr, answers), FakeClient("this is not json"))
    assert summary["invalid_outputs"] == 3
    assert summary["fields"]["total"]["normalized"] == 0.0


def test_cache_avoids_second_call(tmp_path):
    fake = FakeClient("{}")
    client = CachedClient(fake, tmp_path / "cache")
    first = client.generate_json("same prompt", BaseModel)
    second = client.generate_json("same prompt", BaseModel)
    assert fake.calls == 1
    assert not first.cached and second.cached
