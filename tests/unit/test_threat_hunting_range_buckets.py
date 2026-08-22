"""Partition correctness for the RegexHuntScore filter buckets on /articles.

The dropdown buckets ("0-20", "20-40", "40-60", "60-80", "80-100") must cover
every possible score with no gaps and no overlap -- a fractional score like
19.5 must land in exactly one bucket, never neither ("dead zone") or both.
"""

import pytest

from src.web.routes.pages import parse_threat_hunting_range, score_in_threat_hunting_bucket

pytestmark = pytest.mark.unit

BUCKETS = ["0-20", "20-40", "40-60", "60-80", "80-100"]


def _bucket_hits(score):
    hits = []
    for label in BUCKETS:
        min_score, max_score = parse_threat_hunting_range(label)
        if score_in_threat_hunting_bucket(score, min_score, max_score):
            hits.append(label)
    return hits


@pytest.mark.parametrize(
    "score",
    [0, 19.5, 20, 39.5, 40, 59.5, 60, 79.5, 80, 100, 0.0, 99.999],
)
def test_every_score_lands_in_exactly_one_bucket(score):
    hits = _bucket_hits(score)
    assert len(hits) == 1, f"score {score} matched {hits}, expected exactly 1 bucket"


def test_boundary_scores_land_in_the_higher_bucket():
    # A boundary score belongs to the bucket that starts there, not the one that ends there.
    assert _bucket_hits(20) == ["20-40"]
    assert _bucket_hits(40) == ["40-60"]
    assert _bucket_hits(60) == ["60-80"]
    assert _bucket_hits(80) == ["80-100"]


def test_top_bucket_is_inclusive_of_100():
    assert _bucket_hits(100) == ["80-100"]


def test_missing_score_matches_no_bucket():
    assert _bucket_hits(None) == []


def test_combined_buckets_reconcile_with_their_parts():
    # "High Quality (60+)" (60-100) must equal "Good (60-79)" + "Excellent (80-100)"
    # across the whole score domain, not just at a few sample points.
    high_quality_min, high_quality_max = parse_threat_hunting_range("60-100")
    good_min, good_max = parse_threat_hunting_range("60-80")
    excellent_min, excellent_max = parse_threat_hunting_range("80-100")

    for score in [0, 30, 59.9, 60, 60.1, 79.9, 80, 80.1, 99.9, 100]:
        combined = score_in_threat_hunting_bucket(score, good_min, good_max) or score_in_threat_hunting_bucket(
            score, excellent_min, excellent_max
        )
        high_quality = score_in_threat_hunting_bucket(score, high_quality_min, high_quality_max)
        assert combined == high_quality, f"score {score}: good-or-excellent={combined} high_quality={high_quality}"


def test_malformed_range_parses_to_none():
    assert parse_threat_hunting_range("") is None
    assert parse_threat_hunting_range("not-a-range") is None
    assert parse_threat_hunting_range("garbage") is None
