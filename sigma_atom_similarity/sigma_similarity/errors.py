"""
Custom exceptions for the Sigma semantic similarity engine.

- UnsupportedSigmaFeatureError: count(), near, temporal joins, aggregation,
  multiple logsource blocks, correlation, sequence.
- UnknownTelemetryClassError: rule cannot be mapped to any canonical class
  (caller must re-raise; do not convert to result).
- DeterministicExpansionLimitError: DNF expansion exceeds MAX_DNF_BRANCHES (64);
  engine catches and returns SimilarityResult with reason_flags.
"""


class UnsupportedSigmaFeatureError(Exception):
    """Raised when a Sigma rule uses an unsupported feature.

    Unsupported: count(), near, temporal joins, aggregation operators,
    multiple logsource blocks, correlation rules, sequence operators.
    """


class UnknownTelemetryClassError(Exception):
    """Raised when a rule cannot be mapped to any canonical telemetry class.

    Do NOT return a result for this case — re-raise. Only when both rules
    map to different canonical classes do we return similarity 0 with
    reason_flags (canonical_class_mismatch).
    """


class DeterministicExpansionLimitError(Exception):
    """Raised when DNF expansion would exceed MAX_DNF_BRANCHES (64).

    The similarity_engine catches this and returns SimilarityResult
    with similarity=0 and reason_flags=["dnf_expansion_limit"].
    """
