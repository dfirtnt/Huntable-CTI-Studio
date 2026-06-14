"""
Detection-atom + logsource scorer for end-to-end Sigma rule evaluation.

Compares the Sigma rules an article *should* produce (ground truth) against the
rules the pipeline actually generated, and reports precision/recall at two
granularities:

- logsource level: the set of canonical telemetry classes (e.g.
  ``windows.process_creation``) the rules target -- did we produce rules about
  the right behaviors at all?
- detection-atom level: the set of normalized ``field|modifier|value`` atoms
  (e.g. ``process.image|endswith|/rundll32.exe``) -- did the detections contain
  the right fields and values?

Both the expected and actual rules are decomposed through the SAME extractor
(``src.services.sigma_atom_precompute.extract_atom_fields``, which wraps the
``sigma_similarity`` package).  Running both sides through identical
normalization is what makes the comparison robust to cosmetic YAML differences
(casing, wildcard spelling, backslash direction, taxonomy field aliases) and to
prompt drift -- only a genuine difference in detection logic moves the score.

This module is deterministic and has no database or network dependencies, so it
can be exercised against historical executions or run inline in the workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.services.sigma_atom_precompute import extract_atom_fields, is_sigma_similarity_available


@dataclass
class SetScore:
    """Precision/recall result for one set comparison (logsource or atoms)."""

    precision: float  # TP / (TP + FP)
    recall: float  # TP / (TP + FN)
    matched: list[str]  # in both expected and actual
    missed: list[str]  # in expected but not actual (false negatives)
    extra: list[str]  # in actual but not expected (false positives)
    matched_count: int
    missed_count: int
    extra_count: int


@dataclass
class SigmaEvalResult:
    """Full result of scoring one article's generated Sigma rules vs ground truth."""

    # Count layer (Eval1 analog)
    expected_rule_count: int
    actual_rule_count: int

    # Logsource layer: canonical telemetry classes
    logsource: SetScore

    # Detection-atom layer: positive atoms (the primary quality signal)
    atoms: SetScore

    # Decomposition health -- surfaces rules we could not break down.
    # An undecomposable EXPECTED rule is a ground-truth authoring bug; an
    # undecomposable ACTUAL rule is a generation/validity problem.
    expected_undecomposable: int = 0
    actual_undecomposable: int = 0

    # Rules whose logsource did not resolve to a known canonical class.
    actual_logsource_unresolved: int = 0

    # Negative (filter) atoms, reported for visibility but not part of the
    # primary precision/recall headline in Phase 1.
    negative_atoms: SetScore | None = None

    warnings: list[str] = field(default_factory=list)


def _score_string_sets(expected: set[str], actual: set[str]) -> SetScore:
    """Set-based precision/recall over already-normalized identity strings.

    The inputs are atom/canonical-class identity strings produced by
    ``extract_atom_fields``, which has already normalized them, so no further
    normalization happens here (unlike ``eval_item_scorer.score_items``, which
    normalizes free-text command lines).
    """
    matched_keys = expected & actual
    missed_keys = expected - actual
    extra_keys = actual - expected

    tp = len(matched_keys)
    fn = len(missed_keys)
    fp = len(extra_keys)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    return SetScore(
        precision=round(precision, 4),
        recall=round(recall, 4),
        matched=sorted(matched_keys),
        missed=sorted(missed_keys),
        extra=sorted(extra_keys),
        matched_count=tp,
        missed_count=fn,
        extra_count=fp,
    )


@dataclass
class _Decomposition:
    canonical_classes: set[str]
    positive_atoms: set[str]
    negative_atoms: set[str]
    undecomposable: int
    logsource_unresolved: int


def _decompose_rules(rules: list[dict[str, Any]]) -> _Decomposition:
    """Flatten a list of Sigma rule dicts into aggregate atom/logsource sets.

    Each rule must be a dict with at least ``logsource`` and ``detection`` keys
    (the same shape emitted by ``SigmaGenerationService`` and persisted in
    ``SigmaRuleQueueTable.rule_metadata``).  ``require_canonical_class=False`` so
    that rules whose logsource does not resolve still contribute their atoms --
    we count the unresolved logsource separately rather than dropping the rule.
    """
    canonical_classes: set[str] = set()
    positive_atoms: set[str] = set()
    negative_atoms: set[str] = set()
    undecomposable = 0
    logsource_unresolved = 0

    for rule in rules:
        if not isinstance(rule, dict):
            undecomposable += 1
            continue
        fields = extract_atom_fields(rule, require_canonical_class=False)
        if fields is None:
            undecomposable += 1
            continue
        cclass = fields.get("canonical_class")
        if cclass:
            canonical_classes.add(cclass)
        else:
            logsource_unresolved += 1
        positive_atoms.update(fields.get("positive_atoms") or [])
        negative_atoms.update(fields.get("negative_atoms") or [])

    return _Decomposition(
        canonical_classes=canonical_classes,
        positive_atoms=positive_atoms,
        negative_atoms=negative_atoms,
        undecomposable=undecomposable,
        logsource_unresolved=logsource_unresolved,
    )


def score_sigma(
    expected_rules: list[dict[str, Any]],
    actual_rules: list[dict[str, Any]],
    expected_rule_count: int | None = None,
) -> SigmaEvalResult:
    """Score generated Sigma rules against ground-truth expected rules.

    Args:
        expected_rules: Ground-truth rule dicts (``logsource`` + ``detection``).
            These are hand-authored or bootstrapped from a vetted run.
        actual_rules: Rule dicts the pipeline generated for the article (the
            ``rules`` list from ``SigmaGenerationService.generate_sigma_rules``
            or ``rule_metadata`` rows).
        expected_rule_count: Optional override for the expected count headline.
            Defaults to ``len(expected_rules)``.  Useful when the ground-truth
            count is tracked separately in ``config/eval_articles.yaml``.

    Returns:
        A ``SigmaEvalResult``.  Aggregation is set-based across all of an
        article's rules (the union of canonical classes and the union of atoms),
        which sidesteps the rule-to-rule alignment problem; rule-aligned scoring
        can be layered on later if the flat-set signal proves too coarse.
    """
    warnings: list[str] = []
    if not is_sigma_similarity_available():
        warnings.append(
            "sigma_similarity is not installed; atom/logsource decomposition is unavailable. "
            "Scores will report zero atoms on both sides."
        )

    exp = _decompose_rules(expected_rules or [])
    act = _decompose_rules(actual_rules or [])

    if exp.undecomposable:
        warnings.append(
            f"{exp.undecomposable} expected (ground-truth) rule(s) could not be decomposed -- "
            "check the ground_truth.json detection blocks."
        )

    return SigmaEvalResult(
        expected_rule_count=expected_rule_count if expected_rule_count is not None else len(expected_rules or []),
        actual_rule_count=len(actual_rules or []),
        logsource=_score_string_sets(exp.canonical_classes, act.canonical_classes),
        atoms=_score_string_sets(exp.positive_atoms, act.positive_atoms),
        negative_atoms=_score_string_sets(exp.negative_atoms, act.negative_atoms),
        expected_undecomposable=exp.undecomposable,
        actual_undecomposable=act.undecomposable,
        actual_logsource_unresolved=act.logsource_unresolved,
        warnings=warnings,
    )
