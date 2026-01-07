import pytest
from types import SimpleNamespace

from src.services import cmdline_caliper


class DummyModel:
    def encode(self, texts, convert_to_tensor=True, normalize_embeddings=True):
        # Return a placeholder list for each input candidate
        return [None for _ in texts]


class DummyScore:
    def __init__(self, value):
        self._value = value

    def numel(self):
        return 1

    def max(self):
        return self

    def item(self):
        return self._value


def make_cos_sim(scores):
    def fake_cos_sim(embeddings, prototypes):
        length = len(embeddings or [])
        if length == 0:
            return []
        return [DummyScore(scores[i % len(scores)]) for i in range(length)]

    return fake_cos_sim


def fake_ensure_model(self):
    self._model = DummyModel()
    self._prototype_embeddings = ["dummy"]


def patch_candidate_lines(monkeypatch):
    sample_lines = [
        {"text": "cmd.exe /c whoami", "start": 0, "end": 20, "context": "ctx 1"},
        {"text": "powershell -NoProfile -Command Get-Service", "start": 20, "end": 60, "context": "ctx 2"},
        {"text": "bash -c ls -la /tmp", "start": 60, "end": 90, "context": "ctx 3"},
    ]

    def fake_extract_candidates(self, content, max_candidates):
        return sample_lines[:max_candidates]

    monkeypatch.setattr(
        cmdline_caliper.CommandLineCaliperExtractor,
        "_extract_candidate_lines",
        fake_extract_candidates,
    )
    return sample_lines


@pytest.fixture(autouse=True)
def patch_model(monkeypatch):
    monkeypatch.setattr(
        cmdline_caliper.CommandLineCaliperExtractor, "_ensure_model", fake_ensure_model
    )
    yield


@pytest.mark.parametrize(
    "scores,threshold,expected_count",
    [
        ([0.95, 0.85, 0.65], 0.7, 2),
        ([0.92, 0.9, 0.88], 0.91, 1),
    ],
)
def test_extract_command_lines_uses_similarity(monkeypatch, scores, threshold, expected_count):
    monkeypatch.setattr(
        cmdline_caliper,
        "util",
        SimpleNamespace(cos_sim=make_cos_sim(scores)),
    )
    patch_candidate_lines(monkeypatch)

    extractor = cmdline_caliper.CommandLineCaliperExtractor()
    content = """
Introduction text that should be ignored.
cmd.exe /c whoami
powershell -NoProfile -Command Get-Service
Some other paragraph talking about the operations.
bash -c ls -la /tmp
"""
    results = extractor.extract(
        content,
        similarity_threshold=threshold,
        max_results=5,
        max_candidates=8,
    )

    assert len(results) == expected_count
    for idx, entry in enumerate(results):
        expected_score = scores[idx]
        assert pytest.approx(expected_score, rel=1e-3) == entry["score"]


def test_extract_command_lines_honors_max_results(monkeypatch):
    monkeypatch.setattr(
        cmdline_caliper,
        "util",
        SimpleNamespace(cos_sim=make_cos_sim([0.95, 0.95, 0.95])),
    )
    patch_candidate_lines(monkeypatch)

    extractor = cmdline_caliper.CommandLineCaliperExtractor()
    content = """
cmd.exe /c whoami
powershell -NoProfile -Command Get-Service
bash -c ls -la /tmp
"""
    results = extractor.extract(
        content,
        similarity_threshold=0.5,
        max_results=2,
        max_candidates=5,
    )

    assert len(results) == 2
    assert all(pytest.approx(0.95, rel=1e-3) == entry["score"] for entry in results)
