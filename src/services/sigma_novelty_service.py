"""
SIGMA Rule Behavioral Novelty Assessment Service

Determines whether a newly submitted SIGMA rule is BEHAVIORALLY NOVEL
relative to an existing SIGMA rule repository.

Behavioral novelty answers: "Does this rule detect meaningfully new telemetry behavior?"

When the standalone sigma_semantic_similarity package is installed, pairwise
rule comparison uses its deterministic engine (canonical class, DNF, Jaccard,
containment, filter penalty). Candidates missing stored atoms are extracted
live with the same package path.
"""

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

# Optional: deterministic sigma similarity engine (install sigma_semantic_similarity)
try:
    from sigma_similarity.containment_estimator import compute_containment
    from sigma_similarity.filter_analyzer import filter_penalty as _sigma_filter_penalty

    _sigma_compare_rules_available = True
except ImportError:
    compute_containment = None
    _sigma_filter_penalty = None
    _sigma_compare_rules_available = False


# ── Atom identity normalization (runtime safety net) ──────────────────────────
# Normalizes precomputed atom identity strings so that field name variants
# (PascalCase vs snake_case vs lowercase) and value casing all resolve to the
# same canonical form.  This lets the precomputed-atom fast path produce correct
# Jaccard scores even when the proposed rule was atomized by a different version
# of the extractor than the stored SigmaHQ atoms.
_ATOM_FIELD_ALIAS: dict[str, str] = {
    # Process execution — map to process.* namespace
    "commandline": "process.command_line",
    "command_line": "process.command_line",
    "processcommandline": "process.command_line",
    "process_command_line": "process.command_line",
    "image": "process.image",
    "processpath": "process.image",
    "process_path": "process.image",
    "parentimage": "process.parent_image",
    "parent_image": "process.parent_image",
    "parentcommandline": "process.parent_command_line",
    "parent_command_line": "process.parent_command_line",
    # Service creation — collapse multi-to-one aliases so stored atoms using
    # either alias resolve to the same form as proposed atoms via FIELD_ALIAS_MAP.
    "servicefilename": "serviceimagepath",
    "servicefile_name": "serviceimagepath",
    "imagepath": "serviceimagepath",
    "image_path": "serviceimagepath",
    "starttype": "servicestarttype",
    "start_type": "servicestarttype",
}


_PROCESS_EXE_CANONICAL_FIELDS: set[str] = {
    "process.image",
    "process.parent_image",
    "process.command_line",
    "process.parent_command_line",
    "process.original_file_name",
    # Legacy / un-aliased forms that may appear
    "image",
    "parentimage",
    "commandline",
    "parentcommandline",
    "originalfilename",
    "command_line",
    "parent_image",
}


def _extract_exe_value(atom_str: str) -> str | None:
    """Extract the value portion from an atom string if its field is process-exe related.

    Field matching is case-insensitive so callers that forget to run the
    atom through ``_normalize_atom_identity`` first (e.g. "Image|endswith|...")
    still resolve correctly. Mirrors the case-insensitive lookup used by the
    class-method fallback in ``SigmaNoveltyService.compute_atom_jaccard``.
    """
    parts = atom_str.split("|", 1)
    if len(parts) < 2:
        return None
    field = parts[0].lower()
    if field not in _PROCESS_EXE_CANONICAL_FIELDS:
        return None
    # Value is the last pipe-separated segment
    segments = atom_str.split("|")
    return segments[-1] if len(segments) >= 3 else None


def _soft_exe_jaccard_from_atom_strings(A1: set[str], A2: set[str], union: set[str]) -> float:
    """Compute soft jaccard from precomputed atom strings using value-based cross-field matching."""
    if not union:
        return 0.0
    vals1 = {v for a in A1 if (v := _extract_exe_value(a)) is not None}
    vals2 = {v for a in A2 if (v := _extract_exe_value(a)) is not None}
    shared = vals1 & vals2
    if not shared:
        return 0.0
    # Dampen by 0.5 since cross-field match is weaker than exact atom match
    return min((len(shared) / len(union)) * 0.5, 1.0)


def _normalize_atom_identity(atom_id: str) -> str:
    """Normalize a precomputed atom identity string: resolve field aliases + lowercase."""
    lowered = atom_id.lower()
    # Atom format: field|modifier_chain|value (operator = modifier_chain.split("|")[0]).
    # We only need the leading field segment here, so split count is irrelevant.
    parts = lowered.split("|", 1)
    if len(parts) < 2:
        return lowered
    field, rest = parts
    resolved = _ATOM_FIELD_ALIAS.get(field, field)
    return f"{resolved}|{rest}"


def _atom_identity_to_display(atom_id: str) -> str:
    """Render a 3-slot atom identity (``field|modifier_chain|value``) the same way
    the full-parse path's ``_atom_to_string`` renders parsed atoms: ``field|op:value``
    (or ``field:value`` when the modifier chain is empty, i.e. a default ``eq``).

    The precomputed path stores raw identity strings; without this the UI rendered
    them verbatim — diverging from the full-parse explainability surface. ``op`` is
    the first modifier token (``modifier_chain.split("|")[0]``). ``value`` is always
    the final ``|`` segment, mirroring ``_extract_exe_value``.
    """
    segments = atom_id.split("|")
    if len(segments) < 2:
        return atom_id
    field = segments[0]
    value = segments[-1]
    mod_tokens = segments[1:-1]
    op = mod_tokens[0] if mod_tokens and mod_tokens[0] else ""
    return f"{field}|{op}:{value}" if op else f"{field}:{value}"


class NoveltyLabel(StrEnum):
    """Novelty classification labels."""

    DUPLICATE = "DUPLICATE"
    SIMILAR = "SIMILAR"
    NOVEL = "NOVEL"


def classify_match_novelty(match: dict[str, Any]) -> NoveltyLabel:
    """Classify a single candidate match's novelty relative to the proposed rule.

    Single source of truth for the legacy atom/logic-shape thresholds and the
    exact-hash override (Phase 2 of the sigma-similarity unification). Operates on
    ONE candidate match — callers that classify many candidates (e.g. the article
    coverage view) get a per-match verdict, not a single broadcast label.

    Thresholds (per spec):
    - exact_hash_match            -> DUPLICATE
    - atom_jaccard > 0.95 AND logic_shape > 0.95 -> DUPLICATE
    - atom_jaccard > 0.80         -> SIMILAR
    - otherwise                   -> NOVEL

    logic_shape_similarity of None is the early-exit perfect-match signal and is
    treated as 1.0.
    """
    if match.get("exact_hash_match"):
        return NoveltyLabel.DUPLICATE

    atom_jaccard = match.get("atom_jaccard", 0.0) or 0.0
    logic_shape = match.get("logic_shape_similarity")
    logic_shape = 1.0 if logic_shape is None else logic_shape

    if atom_jaccard > 0.95 and logic_shape > 0.95:
        return NoveltyLabel.DUPLICATE
    if atom_jaccard > 0.80:
        return NoveltyLabel.SIMILAR
    return NoveltyLabel.NOVEL


@dataclass
class Atom:
    """Atomic predicate representing one irreducible behavioral constraint."""

    field: str
    op: str  # Primary operator (e.g., "contains", "endswith", "re")
    op_type: str  # "literal" or "regex" (determined by operator)
    value: str
    value_type: str  # "string", "int", "float", "bool"
    polarity: str  # "positive" or "negative" (NOT logic)


@dataclass
class CanonicalRule:
    """Canonical representation of a SIGMA rule."""

    version: str = "1.0"
    logsource: dict[str, str] = None  # {"product": "...", "category": "..."}
    detection: dict[str, Any] = None  # {"atoms": [...], "logic": {...}}

    def __post_init__(self):
        if self.logsource is None:
            self.logsource = {}
        if self.detection is None:
            self.detection = {"atoms": [], "logic": {}}


class SigmaNoveltyService:
    """Service for assessing behavioral novelty of SIGMA rules (v1.2)."""

    # Canonical version
    CANONICAL_VERSION = "1.2"

    # Fields that require aggressive normalization
    AGGRESSIVE_NORMALIZATION_FIELDS = {"CommandLine", "ProcessCommandLine", "ParentCommandLine"}

    # Field alias map (v1.2) - maps equivalent field names to canonical form
    FIELD_ALIAS_MAP = {
        # Process execution
        "CommandLine": "CommandLine",
        "ProcessCommandLine": "CommandLine",
        "Image": "Image",
        "ProcessPath": "Image",
        "NewProcessName": "Image",
        "ExecutablePath": "Image",
        "ParentImage": "ParentImage",
        "ParentProcessPath": "ParentImage",
        "ParentProcessName": "ParentImage",
        # Network
        "DestinationIp": "DestinationIp",
        "DestinationIpAddress": "DestinationIp",
        "DestIp": "DestinationIp",
        "SourceIp": "SourceIp",
        "SourceIpAddress": "SourceIp",
        "SrcIp": "SourceIp",
        "DestinationPort": "DestinationPort",
        "DestPort": "DestinationPort",
        "SourcePort": "SourcePort",
        "SrcPort": "SourcePort",
        # DNS
        "QueryName": "DnsQuery",
        "DnsQuery": "DnsQuery",
        "Query": "DnsQuery",
        # File system
        "TargetFilename": "FilePath",
        "TargetFileName": "FilePath",
        "FileName": "FilePath",
        "FilePath": "FilePath",
        # Registry
        "TargetObject": "RegistryPath",
        "RegistryKey": "RegistryPath",
        "RegistryPath": "RegistryPath",
        "RegistryValue": "RegistryValue",
        # Service creation
        "ServiceName": "ServiceName",
        "ServiceFileName": "ServiceImagePath",
        "ImagePath": "ServiceImagePath",
        "StartType": "ServiceStartType",
        "ServiceType": "ServiceType",
        "ServiceStartType": "ServiceStartType",
        # Scheduled tasks
        "TaskName": "TaskName",
        "TaskContent": "TaskContent",
    }

    # Service penalty configuration (v1.2)
    SERVICE_PENALTY = 0.05

    def __init__(self, db_session=None):
        """
        Initialize the novelty service.

        Args:
            db_session: Optional SQLAlchemy session for database queries
        """
        self.db_session = db_session

    def assess_novelty(self, proposed_rule: dict[str, Any], threshold: float = 0.0, top_k: int = 20) -> dict[str, Any]:
        """
        Assess behavioral novelty of a proposed SIGMA rule.

        Args:
            proposed_rule: SIGMA rule dictionary (from YAML parse)
            threshold: Minimum similarity threshold (0-1)
            top_k: Maximum number of candidates to retrieve

        Returns:
            Dictionary with novelty classification and explainability
        """
        try:
            _warnings: list[str] = []
            semantic_extraction_failed = False

            # Step 1: Build canonical rule
            canonical_rule = self.build_canonical_rule(proposed_rule)

            # Step 2: Generate fingerprints
            exact_hash = self.generate_exact_hash(canonical_rule)
            logsource_key, proposed_service = self.normalize_logsource(proposed_rule.get("logsource", {}))

            # Try deterministic semantic precompute for proposed rule (enables precomputed-atom path)
            proposed_sem = None
            if _sigma_compare_rules_available:
                try:
                    from src.services.sigma_semantic_precompute import extract_semantic_fields

                    proposed_sem = extract_semantic_fields(proposed_rule, require_canonical_class=False)
                except Exception:
                    semantic_extraction_failed = True
                    logger.warning(
                        "sigma_novelty: semantic atom extraction failed", exc_info=True
                    )
                    _warnings.append("semantic_precompute_failed: semantic atom extraction unavailable")

            use_deterministic = proposed_sem is not None
            canonical_class = proposed_sem["canonical_class"] if proposed_sem else None

            # Guard (exact_hash degeneracy): a rule with no extractable behavioral
            # atoms has no fingerprint to compare. Its canonical form is empty, so
            # generate_exact_hash collapses every such rule onto one value — which
            # would falsely short-circuit to DUPLICATE and suppress a novel rule.
            # Without atoms we cannot assert duplication, so report NOVEL.
            semantic_atoms = canonical_rule.detection.get("atoms") or []
            sem_atoms = (proposed_sem or {}).get("positive_atoms") or []
            if not semantic_extraction_failed and not semantic_atoms and not sem_atoms:
                _warnings.append(
                    "no_atoms_extracted: insufficient detection content to assess novelty; treated as NOVEL"
                )
                return {
                    "novelty_label": NoveltyLabel.NOVEL,
                    "novelty_score": 1.0,
                    "logsource_key": logsource_key,
                    "canonical_class": canonical_class,
                    "exact_hash": exact_hash,
                    "top_matches": [],
                    "canonical_rule": asdict(canonical_rule),
                    "total_candidates_evaluated": 0,
                    "behavioral_matches_found": 0,
                    "engine_used": "deterministic" if use_deterministic else "legacy",
                    # Machine-readable flag (not just the free-text warning, which
                    # downstream summarize_rule_novelty drops): this rule could not be
                    # assessed at all. Routing must treat it as inconclusive →
                    # needs_review, NOT a confident pending novel. Fail open, not silent.
                    "no_atoms_extracted": True,
                    "warnings": _warnings,
                }

            # Step 3: Retrieve candidates (deterministic: by canonical_class, no limit; else: logsource_key + top_k)
            logger.debug(
                f"Retrieving candidates for logsource_key: '{logsource_key}'"
                + (f", canonical_class: '{canonical_class}'" if canonical_class else "")
            )
            candidates = self.retrieve_candidates(
                exact_hash=exact_hash,
                logsource_key=logsource_key,
                top_k=top_k,
                canonical_class=canonical_class,
                use_deterministic=use_deterministic,
            )
            logger.debug(f"Retrieved {len(candidates)} candidates")

            # Step 4: Compute similarity metrics for each candidate
            matches = []
            for candidate in candidates:
                # Check for exact hash match first (duplicate detection)
                is_exact_match = isinstance(candidate, dict) and candidate.get("exact_hash_match", False)

                # If exact hash match, short-circuit to duplicate (skip similarity computation)
                if is_exact_match:
                    matches.append(
                        {
                            "rule_id": candidate.get("rule_id", "") if isinstance(candidate, dict) else "",
                            "exact_hash_match": True,
                            "similarity": 1.0,
                            "atom_jaccard": 1.0,
                            "logic_shape_similarity": 1.0,
                            "similarity_engine": "legacy",
                            "semantic_details": None,
                            # Spec Item 6 (P2-C): inherit phase1_path from the candidate (set to
                            # "exact_hash" by retrieve_candidates). Downstream gate skips this path.
                            "phase1_path": candidate.get("phase1_path") if isinstance(candidate, dict) else None,
                        }
                    )
                    continue

                # Prefer precomputed-atom path when both sides have atoms; else full compare
                used_deterministic = False
                det_match = None
                candidate_pos = candidate.get("positive_atoms") if isinstance(candidate, dict) else None
                candidate_neg = candidate.get("negative_atoms") if isinstance(candidate, dict) else []
                candidate_surface = (candidate.get("surface_score") or 1) if isinstance(candidate, dict) else 1
                candidate_sem = None

                if proposed_sem is not None and candidate_pos is not None:
                    # Pure set math via the single precomputed-atom scorer
                    # (shared with /sigma-ab-test /compare). Returns None when
                    # the sigma_similarity primitives are unavailable.
                    det_match = self.compare_precomputed_semantics(
                        proposed_sem,
                        {
                            "positive_atoms": candidate_pos,
                            "negative_atoms": candidate_neg or [],
                            "surface_score": candidate_surface,
                            "canonical_class": candidate.get("canonical_class") if isinstance(candidate, dict) else None,
                        },
                    )
                elif proposed_sem is not None and isinstance(candidate, dict):
                    candidate_sem = self._semantic_fields_for_rule(candidate, require_canonical_class=False)
                    if candidate_sem is not None:
                        det_match = self.compare_precomputed_semantics(proposed_sem, candidate_sem)

                if det_match is not None:
                    used_deterministic = True
                    atom_jaccard = det_match["atom_jaccard"]
                    logic_similarity = det_match["logic_shape_similarity"]
                    service_penalty = det_match["service_penalty"]
                    filter_penalty = det_match["filter_penalty"]
                    weighted_sim = det_match["similarity"]
                    weighted_before_penalties = det_match["weighted_before_penalties"]

                if not used_deterministic:
                    logger.debug(
                        "sigma_novelty: semantic extraction unavailable for candidate %s; skipping comparison",
                        candidate.get("rule_id", "") if isinstance(candidate, dict) else "",
                    )
                    continue

                if weighted_sim >= threshold:
                    # Explainability from the same semantic atom sets, whether
                    # they were stored at index time or computed live here.
                    explainability = {
                        "shared_atoms": det_match["shared_atoms"],
                        "added_atoms": det_match["added_atoms"],
                        "removed_atoms": det_match["removed_atoms"],
                        "filter_differences": det_match["filter_differences"],
                    }

                    match_dict = {
                        "rule_id": candidate.get("rule_id", "") if isinstance(candidate, dict) else "",
                        "atom_jaccard": atom_jaccard,
                        "logic_shape_similarity": logic_similarity,
                        "similarity": weighted_sim,
                        "service_penalty": service_penalty,
                        "filter_penalty": filter_penalty,
                        "weighted_before_penalties": weighted_before_penalties,
                        "similarity_engine": "deterministic" if used_deterministic else "legacy",
                        # Spec Item 6 (P2-C): inherit Phase 1 retrieval path from the candidate so
                        # the downstream gate at sigma_matching_service.py:551 can scope itself.
                        "phase1_path": candidate.get("phase1_path") if isinstance(candidate, dict) else None,
                        "semantic_details": det_match["semantic_details"],
                        **explainability,
                    }

                    matches.append(match_dict)

            # Sort by similarity (descending)
            matches.sort(key=lambda x: x["similarity"], reverse=True)

            # Step 5: Classify novelty
            novelty_label, novelty_score = self.classify_novelty(exact_hash, matches)

            # Metadata for empty-state differentiation (corpus unavailable vs no behavioral overlap)
            def _jaccard(m: dict) -> float:
                sd = m.get("semantic_details")
                return sd.get("jaccard", m.get("atom_jaccard", 0.0)) if sd else m.get("atom_jaccard", 0.0)

            behavioral_matches_found = sum(1 for m in matches if _jaccard(m) > 0)
            engine_used = (
                "deterministic" if any(m.get("similarity_engine") == "deterministic" for m in matches) else "legacy"
            )

            return {
                "novelty_label": novelty_label,
                "novelty_score": novelty_score,
                "logsource_key": logsource_key,
                "canonical_class": canonical_class,
                "exact_hash": exact_hash,
                "top_matches": matches[:10],  # Top 10 for explainability
                "canonical_rule": asdict(canonical_rule),  # For debugging
                "total_candidates_evaluated": len(candidates),
                "behavioral_matches_found": behavioral_matches_found,
                "engine_used": engine_used,
                **({"warnings": _warnings} if _warnings else {}),
            }

        except Exception as e:
            logger.error(f"Failed to assess novelty: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {
                "novelty_label": NoveltyLabel.NOVEL,
                "novelty_score": 1.0,
                "logsource_key": "",
                "canonical_class": None,
                "error": "Novelty assessment failed",
                "top_matches": [],
                "total_candidates_evaluated": 0,
                "behavioral_matches_found": 0,
                "engine_used": "legacy",
            }

    def compare_precomputed_semantics(self, sem_a: dict[str, Any], sem_b: dict[str, Any]) -> dict[str, Any] | None:
        """Pairwise comparison of two precomputed semantic-field dicts (pure set math).

        Single scorer for the precomputed-atom path: assess_novelty's stored-atom
        branch and /sigma-ab-test /compare both call this, so live-parse and
        precomputed scoring cannot diverge (the two-extractor polarity bug).

        Inputs are dicts shaped like precompute_semantic_fields() output /
        SigmaRuleTable semantic columns: canonical_class, positive_atoms,
        negative_atoms, surface_score. Returns None when the sigma_similarity
        primitives are unavailable.

        Filter (negative) atoms are counted exactly once: they never enter the
        positive jaccard; their entire effect is the filter_penalty term
        (similarity = jaccard * containment - filter_penalty).
        """
        if compute_containment is None or _sigma_filter_penalty is None:
            return None

        # Normalize atom identities: lowercase values AND resolve field aliases.
        # Proposed atoms may use snake_case fields (LLM-generated) while stored
        # SigmaHQ atoms use canonical process.* namespace. Both sides need
        # normalization for correct comparison.
        a1 = {_normalize_atom_identity(a) for a in (sem_a.get("positive_atoms") or [])}
        a2 = {_normalize_atom_identity(a) for a in (sem_b.get("positive_atoms") or [])}
        f1 = {_normalize_atom_identity(a) for a in (sem_a.get("negative_atoms") or [])}
        f2 = {_normalize_atom_identity(a) for a in (sem_b.get("negative_atoms") or [])}
        surface_a = float(sem_a.get("surface_score") or 0)
        surface_b = float(sem_b.get("surface_score") or 0)

        intersection = a1 & a2
        union = a1 | a2
        if len(union) == 0:
            atom_jaccard = 0.0
            logic_similarity = 0.65
            filter_penalty = 0.0
            weighted_sim = 0.0
            weighted_before_penalties = 0.0
            overlap_ratio_a, overlap_ratio_b = 0.0, 0.0
            reason_flags = ["no_shared_atoms"]
        else:
            atom_jaccard = len(intersection) / len(union)

            # Value-based soft matching: when strict atoms don't overlap,
            # check if the same executable value appears in process-exe
            # fields on both sides (e.g. process.image vs process.command_line).
            if atom_jaccard == 0.0:
                soft = _soft_exe_jaccard_from_atom_strings(a1, a2, union)
                if soft > 0.0:
                    atom_jaccard = soft

            # For containment, use actual intersection size (0 for soft matches)
            # but ensure soft matches still get reasonable containment
            effective_intersection = len(intersection)
            if effective_intersection == 0 and atom_jaccard > 0:
                effective_intersection = max(1, round(atom_jaccard * len(union)))

            containment_factor, overlap_ratio_a, overlap_ratio_b = compute_containment(
                effective_intersection, len(a1), len(a2), surface_a, surface_b
            )
            logic_similarity = containment_factor
            filter_penalty = _sigma_filter_penalty(f1, f2, len(a1), len(a2))
            weighted_sim = max(0.0, min(1.0, (atom_jaccard * containment_factor) - filter_penalty))
            weighted_before_penalties = weighted_sim + filter_penalty
            reason_flags = [] if atom_jaccard > 0 else ["no_shared_atoms"]

        # Explainability from the same normalized sets; set ops run on raw
        # identities first, display-format only at emit.
        added = a2 - a1
        removed = a1 - a2
        filter_diff = (f1 | f2) - (f1 & f2)

        return {
            "atom_jaccard": atom_jaccard,
            "logic_shape_similarity": logic_similarity,
            "similarity": weighted_sim,
            "service_penalty": 0.0,
            "filter_penalty": filter_penalty,
            "weighted_before_penalties": weighted_before_penalties,
            "similarity_engine": "deterministic",
            "semantic_details": {
                "canonical_class": sem_a.get("canonical_class"),
                "jaccard": atom_jaccard,
                "containment_factor": logic_similarity,
                "filter_penalty": filter_penalty,
                "surface_score_a": surface_a,
                "surface_score_b": surface_b,
                "overlap_ratio_a": overlap_ratio_a,
                "overlap_ratio_b": overlap_ratio_b,
                "reason_flags": reason_flags,
            },
            "shared_atoms": [_atom_identity_to_display(a) for a in sorted(intersection)],
            "added_atoms": [_atom_identity_to_display(a) for a in sorted(added)],
            "removed_atoms": [_atom_identity_to_display(a) for a in sorted(removed)],
            "filter_differences": [_atom_identity_to_display(a) for a in sorted(filter_diff)],
        }

    def _semantic_fields_for_rule(
        self, rule_data: dict[str, Any], *, require_canonical_class: bool = False
    ) -> dict[str, Any] | None:
        """Live semantic extraction through the sigma_similarity package."""
        try:
            from src.services.sigma_semantic_precompute import extract_semantic_fields

            return extract_semantic_fields(rule_data, require_canonical_class=require_canonical_class)
        except Exception:
            logger.debug("sigma_novelty: live semantic extraction failed", exc_info=True)
            return None

    def _atom_identity_to_atom(self, atom_id: str, polarity: str) -> Atom:
        """Convert package atom identity into the legacy CanonicalRule atom shape."""
        segments = atom_id.split("|")
        field = segments[0] if segments else ""
        value = segments[-1] if len(segments) >= 2 else ""
        modifier_chain = segments[1:-1] if len(segments) >= 3 else []
        op = modifier_chain[0] if modifier_chain and modifier_chain[0] else "eq"
        return Atom(
            field=field,
            op=op,
            op_type="regex" if op == "re" else "literal",
            value=value,
            value_type=self._infer_value_type(value),
            polarity=polarity,
        )

    def _semantic_fields_from_canonical(self, canonical_rule: CanonicalRule) -> dict[str, Any]:
        """Build semantic-field dict from a CanonicalRule produced by this service."""
        positive_atoms = []
        negative_atoms = []
        for atom in canonical_rule.detection.get("atoms", []) or []:
            polarity = atom.get("polarity", "positive")
            identity = atom.get("identity")
            if identity is None:
                identity = self._atom_to_identity(atom)
            if polarity == "negative":
                negative_atoms.append(identity)
            else:
                positive_atoms.append(identity)

        return {
            "canonical_class": canonical_rule.detection.get("canonical_class"),
            "positive_atoms": sorted(positive_atoms),
            "negative_atoms": sorted(negative_atoms),
            "surface_score": canonical_rule.detection.get("surface_score") or len(positive_atoms) or 1,
        }

    def _atom_to_identity(self, atom: dict[str, Any] | Atom) -> str:
        """Best-effort compatibility conversion for pre-consolidation CanonicalRule atoms."""
        if isinstance(atom, Atom):
            field = atom.field
            op = atom.op
            value = atom.value
        else:
            field = atom.get("field", "")
            op = atom.get("op", "")
            value = atom.get("value", "")
        modifier = "" if op in ("", "eq") else op
        return f"{field}|{modifier}|{value}"

    def build_canonical_rule(self, rule_data: dict[str, Any]) -> CanonicalRule:
        """
        Build canonical rule from SIGMA rule data.

        Args:
            rule_data: Parsed SIGMA rule dictionary

        Returns:
            CanonicalRule object
        """
        # Normalize logsource
        logsource_key, _ = self.normalize_logsource(rule_data.get("logsource", {}))
        product, category = logsource_key.split("|") if "|" in logsource_key else ("", "")

        sem = self._semantic_fields_for_rule(rule_data, require_canonical_class=False)
        positive_atom_ids = sorted((sem or {}).get("positive_atoms") or [])
        negative_atom_ids = sorted((sem or {}).get("negative_atoms") or [])
        if sem is None:
            atom_entries = []
            canonical_class = None
            surface_score = 0
        else:
            atom_entries = []
            for atom_id in positive_atom_ids:
                atom_entries.append({**asdict(self._atom_identity_to_atom(atom_id, "positive")), "identity": atom_id})
            for atom_id in negative_atom_ids:
                atom_entries.append({**asdict(self._atom_identity_to_atom(atom_id, "negative")), "identity": atom_id})
            canonical_class = sem.get("canonical_class")
            surface_score = sem.get("surface_score") or 0

        return CanonicalRule(
            version=self.CANONICAL_VERSION,
            logsource={"product": product, "category": category},
            detection={
                "atoms": atom_entries,
                "logic": {
                    "engine": "sigma_similarity",
                    "surface_score": surface_score,
                },
                "canonical_class": canonical_class,
                "surface_score": surface_score,
            },
        )

    def normalize_logsource(self, logsource: dict[str, Any]) -> tuple[str, str | None]:
        """
        Normalize logsource to product|category key and extract service (v1.2).

        Args:
            logsource: Logsource dictionary

        Returns:
            Tuple of (logsource_key, service) where logsource_key is "product|category"
        """
        if not isinstance(logsource, dict):
            logger.warning(f"Invalid logsource type: {type(logsource)}, expected dict")
            return "|", None

        def _str_val(v: Any) -> str:
            if v is None:
                return ""
            return str(v).lower().strip()

        product = _str_val(logsource.get("product")) if logsource.get("product") else ""
        category = _str_val(logsource.get("category")) if logsource.get("category") else ""
        service = _str_val(logsource.get("service")) if logsource.get("service") else None

        logsource_key = f"{product}|{category}"
        logger.debug(f"Normalized logsource: {logsource} -> '{logsource_key}' (service: {service})")
        return logsource_key, service

    def _parse_field_with_modifiers(self, field_name: str) -> tuple[str, list[str]]:
        """Parse field name to extract base field and modifiers."""
        if "|" not in field_name:
            return field_name, []

        parts = field_name.split("|")
        base_field = parts[0]
        modifiers = parts[1:] if len(parts) > 1 else []

        return base_field, modifiers

    def _infer_value_type(self, value: Any) -> str:
        """Infer value type for atom."""
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, bool):
            return "bool"
        return "string"

    def parse_condition_ast(self, condition: str) -> dict[str, Any]:
        """
        Parse condition string into AST.

        Supports: and/or/not, parentheses, 1 of/all of macros.

        Args:
            condition: Condition string (e.g., "selection1 and (selection2 or selection3)")

        Returns:
            AST dictionary
        """
        if not condition:
            return {"type": "empty"}

        # Tokenize
        tokens = self._tokenize_condition(condition)

        # Parse into AST
        ast = self._parse_tokens(tokens)

        return ast

    def _tokenize_condition(self, condition: str) -> list[str]:
        """Tokenize condition string."""
        # Normalize whitespace
        condition = re.sub(r"\s+", " ", condition.strip())

        # Split on operators and parentheses
        tokens = []
        current = ""

        for char in condition:
            if char in "()" or char in "&|!":
                if current.strip():
                    tokens.append(current.strip())
                    current = ""
                tokens.append(char)
            else:
                current += char

        if current.strip():
            tokens.append(current.strip())

        return tokens

    def _parse_tokens(self, tokens: list[str]) -> dict[str, Any]:
        """Parse tokens into AST (simplified recursive descent)."""
        if not tokens:
            return {"type": "empty"}

        # Simple parser for: selection, and, or, not, parentheses, 1 of, all of
        # This is a simplified implementation - full parser would handle precedence

        i = 0

        def parse_expression():
            nonlocal i
            left = parse_term()

            while i < len(tokens) and tokens[i].lower() in ["and", "or", "&", "|"]:
                op = tokens[i].lower()
                if op in ["&", "and"]:
                    op = "and"
                elif op in ["|", "or"]:
                    op = "or"
                i += 1
                right = parse_term()
                left = {"type": op, "left": left, "right": right}

            return left

        def parse_term():
            nonlocal i
            if i >= len(tokens):
                return {"type": "empty"}

            if tokens[i] == "(":
                i += 1
                expr = parse_expression()
                if i < len(tokens) and tokens[i] == ")":
                    i += 1
                return expr
            if tokens[i].lower() == "not" or tokens[i] == "!":
                i += 1
                return {"type": "not", "operand": parse_term()}
            if tokens[i].lower().startswith("1 of"):
                # Macro: 1 of selection*
                i += 1
                pattern = tokens[i] if i < len(tokens) else ""
                i += 1
                return {"type": "1_of", "pattern": pattern}
            if tokens[i].lower().startswith("all of"):
                # Macro: all of selection*
                i += 1
                pattern = tokens[i] if i < len(tokens) else ""
                i += 1
                return {"type": "all_of", "pattern": pattern}
            # Selection reference
            sel = tokens[i]
            i += 1
            return {"type": "selection", "name": sel}

        return parse_expression()

    def canonicalize_detection_logic(self, detection: dict[str, Any], atoms: list[Atom]) -> dict[str, Any]:
        """
        Canonicalize detection logic into deterministic form.

        Args:
            detection: Detection dictionary
            atoms: List of extracted atoms

        Returns:
            Canonical logic dictionary
        """
        condition = detection.get("condition", "")

        # Parse condition into AST
        ast = self.parse_condition_ast(str(condition))

        # Expand macros (1 of selection*, all of selection*)
        ast = self._expand_macros(ast, detection)

        # Normalize AST (flatten nested AND/OR, sort deterministically)
        ast = self._normalize_ast(ast)

        # Convert to atom-index-based logic
        logic = self._convert_to_atom_logic(ast, atoms, detection)

        return logic

    def _expand_macros(self, ast: dict[str, Any], detection: dict[str, Any]) -> dict[str, Any]:
        """Expand Sigma macros (1 of selection*, all of selection*) into explicit logic."""
        if ast.get("type") == "1_of":
            # 1 of selection* → OR(selections matching pattern)
            pattern = ast.get("pattern", "")
            selections = self._find_selections_matching_pattern(detection, pattern)
            if len(selections) == 1:
                return {"type": "selection", "name": selections[0]}
            if len(selections) > 1:
                result = {"type": "or", "operands": []}
                for sel in selections:
                    result["operands"].append({"type": "selection", "name": sel})
                return result
        elif ast.get("type") == "all_of":
            # all of selection* → AND(selections matching pattern)
            pattern = ast.get("pattern", "")
            selections = self._find_selections_matching_pattern(detection, pattern)
            if len(selections) == 1:
                return {"type": "selection", "name": selections[0]}
            if len(selections) > 1:
                result = {"type": "and", "operands": []}
                for sel in selections:
                    result["operands"].append({"type": "selection", "name": sel})
                return result

        # Recursively expand children
        if "left" in ast:
            ast["left"] = self._expand_macros(ast["left"], detection)
        if "right" in ast:
            ast["right"] = self._expand_macros(ast["right"], detection)
        if "operand" in ast:
            ast["operand"] = self._expand_macros(ast["operand"], detection)
        if "operands" in ast:
            ast["operands"] = [self._expand_macros(op, detection) for op in ast["operands"]]

        return ast

    def _find_selections_matching_pattern(self, detection: dict[str, Any], pattern: str) -> list[str]:
        """Find selection keys matching pattern (e.g., 'selection*')."""
        selections = []

        # Simple pattern matching (supports * wildcard)
        # Escape regex special characters except *
        pattern_escaped = re.escape(pattern).replace(r"\*", ".*")

        try:
            pattern_re = re.compile(f"^{pattern_escaped}$")
        except re.error:
            # If pattern is invalid, fall back to simple string matching
            logger.warning(f"Invalid pattern '{pattern}', using simple matching")
            pattern_prefix = pattern.replace("*", "")
            for key in detection:
                if key != "condition" and key.startswith(pattern_prefix):
                    selections.append(key)
            return sorted(selections)

        for key in detection:
            if key != "condition" and pattern_re.match(key):
                selections.append(key)

        return sorted(selections)  # Deterministic order

    def _normalize_ast(self, ast: dict[str, Any]) -> dict[str, Any]:
        """Normalize AST: flatten nested AND/OR, sort deterministically."""
        if ast.get("type") in ["and", "or"]:
            # Collect all operands (flatten nested)
            operands = []
            self._collect_operands(ast, ast["type"], operands)

            # Sort deterministically
            operands.sort(key=lambda x: json.dumps(x, sort_keys=True))

            # Rebuild as binary tree or n-ary
            if len(operands) == 1:
                return operands[0]
            if len(operands) == 2:
                return {"type": ast["type"], "left": operands[0], "right": operands[1]}
            # Build balanced tree
            return self._build_balanced_tree(operands, ast["type"])
        if "operand" in ast:
            ast["operand"] = self._normalize_ast(ast["operand"])
        elif "left" in ast and "right" in ast:
            ast["left"] = self._normalize_ast(ast["left"])
            ast["right"] = self._normalize_ast(ast["right"])

        return ast

    def _collect_operands(self, node: dict[str, Any], op_type: str, operands: list[dict[str, Any]]):
        """Collect all operands of same type (flatten nested)."""
        if node.get("type") == op_type:
            if "left" in node:
                self._collect_operands(node["left"], op_type, operands)
            if "right" in node:
                self._collect_operands(node["right"], op_type, operands)
            if "operands" in node:
                for op in node["operands"]:
                    self._collect_operands(op, op_type, operands)
        else:
            operands.append(node)

    def _build_balanced_tree(self, operands: list[dict[str, Any]], op_type: str) -> dict[str, Any]:
        """Build balanced binary tree from operands."""
        if len(operands) == 1:
            return operands[0]
        if len(operands) == 2:
            return {"type": op_type, "left": operands[0], "right": operands[1]}
        mid = len(operands) // 2
        left = self._build_balanced_tree(operands[:mid], op_type)
        right = self._build_balanced_tree(operands[mid:], op_type)
        return {"type": op_type, "left": left, "right": right}

    def _convert_to_atom_logic(
        self, ast: dict[str, Any], atoms: list[Atom], detection: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert AST to atom-index-based logic."""
        # Map selections to atom indices, preserving field-level grouping
        # Fields in a selection are ANDed; values in a list are ORed (unless |all modifier)
        selection_to_atoms = {}
        atom_idx = 0

        for key, value in detection.items():
            if key == "condition":
                continue
            if not isinstance(value, dict):
                continue

            # Group atoms by field (fields are ANDed, values within field are ORed/ANDed based on modifier)
            field_groups = []
            for field_name, field_value in value.items():
                base_field, modifiers = self._parse_field_with_modifiers(field_name)
                has_all = "all" in [m.lower() for m in modifiers]

                if isinstance(field_value, list):
                    field_indices = list(range(atom_idx, atom_idx + len(field_value)))
                    atom_idx += len(field_value)
                    # If |all modifier, values are ANDed; otherwise ORed
                    if has_all:
                        field_groups.append({"AND": [{"ATOM": idx} for idx in field_indices]})
                    else:
                        field_groups.append({"OR": [{"ATOM": idx} for idx in field_indices]})
                else:
                    field_indices = [atom_idx]
                    atom_idx += 1
                    field_groups.append({"ATOM": field_indices[0]})

            # All fields in a selection are ANDed together
            if len(field_groups) == 1:
                selection_to_atoms[key] = field_groups[0]
            else:
                selection_to_atoms[key] = {"AND": field_groups}

        # Convert AST to use atom indices
        def convert_node(node):
            if node.get("type") == "selection":
                sel_name = node.get("name", "")
                if sel_name in selection_to_atoms:
                    # selection_to_atoms now contains pre-built logic structure
                    return selection_to_atoms[sel_name]
                return {"ATOM": 0}  # Fallback
            if node.get("type") in ["and", "or"]:
                left = convert_node(node.get("left", {}))
                right = convert_node(node.get("right", {}))
                op = node["type"].upper()
                return {op: [left, right]}
            if node.get("type") == "not":
                operand = convert_node(node.get("operand", {}))
                return {"NOT": operand}
            return {}

        return convert_node(ast)

    def generate_exact_hash(self, canonical_rule: CanonicalRule) -> str | None:
        """Generate SHA256 hash of canonical JSON, or None when the rule has no atoms.

        Atom-less canonical rules (keyword-only Sigma detections the deterministic
        extractor doesn't model) collapse to a degenerate canonical form that would
        hash-collide across unrelated rules. Returning None keeps sigma_rules.exact_hash
        NULL for those rows, and SQL NULL = NULL is false, so the column cannot host
        false-DUPLICATE matches. Item 11 of the 2026-06-01 audit follow-up.
        """
        atoms = canonical_rule.detection.get("atoms") or []
        if not atoms:
            return None
        canonical_json = json.dumps(asdict(canonical_rule), sort_keys=True, separators=(",", ":"))
        hash_obj = hashlib.sha256(canonical_json.encode("utf-8"))
        return hash_obj.hexdigest()

    def retrieve_candidates(
        self,
        exact_hash: str,
        logsource_key: str,
        top_k: int = 20,
        canonical_class: str | None = None,
        use_deterministic: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Retrieve candidate rules for comparison.

        Hard gate: same logsource_key (or canonical_class when use_deterministic).
        When use_deterministic and canonical_class provided: filter by canonical_class, no top_k limit.

        Args:
            exact_hash: Exact hash of proposed rule
            logsource_key: Logsource key (product|category)
            top_k: Maximum number of candidates (ignored when use_deterministic)
            canonical_class: Resolved telemetry class (for deterministic mode)
            use_deterministic: If True, filter by canonical_class and return all (no limit)

        Returns:
            List of candidate rule dictionaries (includes positive_atoms, negative_atoms, surface_score when available)
        """
        if not self.db_session:
            logger.warning("No database session provided, returning empty candidates")
            return []

        try:
            from src.database.models import SigmaRuleTable

            # First, check for exact hash match (duplicate). Skip when the proposed
            # hash is None: SQLAlchemy translates `column == None` to SQL `IS NULL`,
            # which would match every atom-less row (NULL per Item 11) and return
            # one as a false DUPLICATE. SQL NULL = NULL is false; mirror that
            # contract in Python by short-circuiting the branch.
            if exact_hash is not None:
                try:
                    exact_match = (
                        self.db_session.query(SigmaRuleTable).filter(SigmaRuleTable.exact_hash == exact_hash).first()
                    )
                    if exact_match:
                        out = {
                            "rule_id": exact_match.rule_id,
                            "title": exact_match.title,
                            "logsource": exact_match.logsource,
                            "detection": exact_match.detection,
                            "exact_hash_match": True,
                            # Spec Item 6 (P2-C): tag the Phase 1 retrieval path so the downstream
                            # gate in sigma_matching_service.py can decide whether to enforce.
                            "phase1_path": "exact_hash",
                        }
                        if hasattr(exact_match, "positive_atoms") and exact_match.positive_atoms is not None:
                            out["positive_atoms"] = exact_match.positive_atoms
                            out["negative_atoms"] = getattr(exact_match, "negative_atoms", None) or []
                            out["surface_score"] = getattr(exact_match, "surface_score", None) or 1
                        return [out]
                except Exception:
                    logger.warning(
                        "sigma_novelty: exact hash DB lookup failed, skipping duplicate check", exc_info=True
                    )

            # Build query. Track which Phase 1 path produced the candidates so the downstream
            # gate in sigma_matching_service.py can decide whether to enforce (Spec Item 6 P2-C).
            candidates = []
            phase1_path = "logsource_fallback"
            if use_deterministic and canonical_class:
                # Deterministic mode: filter by canonical_class, no limit
                try:
                    if hasattr(SigmaRuleTable, "canonical_class"):
                        candidates = (
                            self.db_session.query(SigmaRuleTable)
                            .filter(SigmaRuleTable.canonical_class == canonical_class)
                            .all()
                        )
                        if candidates:
                            phase1_path = "canonical_class"
                except Exception:
                    logger.warning(
                        "sigma_novelty: canonical_class DB query failed, falling back to logsource_key", exc_info=True
                    )
                if not candidates and logsource_key and logsource_key != "|":
                    # Fallback to logsource_key + limit when canonical_class column missing or no matches.
                    # order_by(rule_id) gives a stable sort so the same logsource_key returns the
                    # same top-k across runs / replicas / after VACUUM. Spec Item 7 (P1).
                    candidates = (
                        self.db_session.query(SigmaRuleTable)
                        .filter(SigmaRuleTable.logsource_key == logsource_key)
                        .order_by(SigmaRuleTable.rule_id)
                        .limit(top_k)
                        .all()
                    )
                    phase1_path = "logsource_fallback"
            else:
                if not logsource_key or logsource_key == "|":
                    logger.warning(f"Invalid logsource_key '{logsource_key}', returning no candidates")
                    return []
                try:
                    # Same stability requirement as the canonical_class-empty fallback above.
                    candidates = (
                        self.db_session.query(SigmaRuleTable)
                        .filter(SigmaRuleTable.logsource_key == logsource_key)
                        .order_by(SigmaRuleTable.rule_id)
                        .limit(top_k)
                        .all()
                    )
                    phase1_path = "logsource_fallback"
                except Exception as e:
                    logger.error(f"Failed to query candidates by logsource_key '{logsource_key}': {e}")
                    return []

            if not candidates:
                return []

            def _row_to_candidate(c):
                out = {
                    "rule_id": c.rule_id,
                    "title": c.title,
                    "logsource": c.logsource,
                    "detection": c.detection,
                    "exact_hash": getattr(c, "exact_hash", None),
                    "phase1_path": phase1_path,  # Spec Item 6 (P2-C): downstream gate scoping
                }
                if hasattr(c, "positive_atoms") and c.positive_atoms is not None:
                    out["positive_atoms"] = c.positive_atoms
                    out["negative_atoms"] = getattr(c, "negative_atoms", None) or []
                    out["surface_score"] = getattr(c, "surface_score", None) or 1
                return out

            return [_row_to_candidate(c) for c in candidates]

        except Exception as e:
            logger.error(f"Failed to retrieve candidates: {e}")
            return []

    # Fields that reference the same executable/binary — a value like '\rundll32.exe'
    # appearing in any of these fields targets the same process, so cross-field matches
    # should contribute partial jaccard credit.
    _PROCESS_EXE_FIELDS: set[str] = {
        "image",
        "parentimage",
        "originalfilename",
        "commandline",
        "parentcommandline",
        "process.image",
        "process.parent_image",
        "process.command_line",
        "process.parent_command_line",
        "process.original_file_name",
        # Historical title-cased variants from pre-consolidation canonical JSON
        "Image",
        "ParentImage",
        "OriginalFileName",
        "CommandLine",
        "ParentCommandLine",
    }

    def compute_atom_jaccard(self, rule1: CanonicalRule, rule2: CanonicalRule) -> float:
        """
        Compute Jaccard similarity over positive atoms only using semantic atom identities.

        Args:
            rule1: First canonical rule
            rule2: Second canonical rule

        Returns:
            Jaccard similarity (0-1)
        """
        result = self.compare_precomputed_semantics(
            self._semantic_fields_from_canonical(rule1),
            self._semantic_fields_from_canonical(rule2),
        )
        return result["atom_jaccard"] if result is not None else 0.0

    def _atom_to_key(self, atom: dict[str, Any] | Atom) -> str:
        """Convert atom to normalized key for comparison (v1.2: includes op_type)."""
        if isinstance(atom, Atom):
            field = atom.field
            op = atom.op
            op_type = atom.op_type
            value = atom.value
        else:
            field = atom.get("field", "")
            op = atom.get("op", "")
            op_type = atom.get("op_type", "literal")
            value = atom.get("value", "")

        # Normalize backslashes in Windows paths for literal values
        # Double backslashes (from YAML/JSON escaping) should match single backslashes
        if op_type == "literal" and isinstance(value, str) and "\\" in value:
            # Normalize all consecutive backslashes (2+) to single backslash
            # This handles C:\\Users\\... matching C:\Users\...
            # Uses regex to handle any number of consecutive backslashes
            normalized_value = re.sub(r"\\+", r"\\", value)
        else:
            normalized_value = value

        return f"{field}|{op}|{op_type}|{normalized_value}"

    def compute_logic_shape_similarity(self, rule1: CanonicalRule, rule2: CanonicalRule) -> float:
        """
        Compute similarity of logic AST shapes (v1.2: enhanced metrics).

        Args:
            rule1: First canonical rule
            rule2: Second canonical rule

        Returns:
            Similarity score (0-1)
        """
        logic1 = rule1.detection.get("logic", {})
        logic2 = rule2.detection.get("logic", {})

        # Convert to normalized string representations
        str1 = json.dumps(logic1, sort_keys=True)
        str2 = json.dumps(logic2, sort_keys=True)

        if str1 == str2:
            return 1.0

        # Enhanced metrics (v1.2)
        metrics1 = self._compute_logic_metrics(logic1)
        metrics2 = self._compute_logic_metrics(logic2)

        # Weighted distance calculation
        distances = []
        weights = {"node_count": 0.3, "and_count": 0.2, "or_count": 0.2, "not_count": 0.1, "max_depth": 0.2}
        normalization_factor = 10.0

        for metric_name, weight in weights.items():
            val1 = metrics1.get(metric_name, 0)
            val2 = metrics2.get(metric_name, 0)
            max_val = max(val1, val2, 1)
            diff = abs(val1 - val2) / (max_val + normalization_factor)
            distances.append(weight * diff)

        similarity = 1.0 - sum(distances)

        return max(0.0, min(1.0, similarity))

    def _compute_logic_metrics(self, logic: dict[str, Any]) -> dict[str, int]:
        """Compute enhanced logic metrics (v1.2)."""
        return {
            "node_count": self._count_nodes(logic),
            "and_count": self._count_operator(logic, "AND"),
            "or_count": self._count_operator(logic, "OR"),
            "not_count": self._count_operator(logic, "NOT"),
            "max_depth": self._compute_logic_depth(logic),
        }

    def _count_nodes(self, logic: dict[str, Any]) -> int:
        """Count total nodes in logic tree."""
        if "ATOM" in logic:
            return 1
        if "AND" in logic or "OR" in logic:
            operands = logic.get("AND", logic.get("OR", []))
            return 1 + sum(self._count_nodes(op) for op in operands)
        if "NOT" in logic:
            return 1 + self._count_nodes(logic["NOT"])
        return 0

    def _count_operator(self, logic: dict[str, Any], op_name: str) -> int:
        """Count occurrences of specific operator."""
        count = 0
        if op_name in logic:
            count = 1
            if op_name == "NOT":
                count += self._count_operator(logic[op_name], op_name)
            else:
                operands = logic.get(op_name, [])
                for op in operands:
                    count += self._count_operator(op, op_name)
        elif "AND" in logic or "OR" in logic:
            operands = logic.get("AND", logic.get("OR", []))
            for op in operands:
                count += self._count_operator(op, op_name)
        elif "NOT" in logic:
            count += self._count_operator(logic["NOT"], op_name)

        return count

    def _compute_logic_depth(self, logic: dict[str, Any]) -> int:
        """Compute maximum depth of logic tree."""
        if "ATOM" in logic:
            return 1
        if "AND" in logic or "OR" in logic:
            operands = logic.get("AND", logic.get("OR", []))
            if operands:
                return 1 + max(self._compute_logic_depth(op) for op in operands)
            return 1
        if "NOT" in logic:
            return 1 + self._compute_logic_depth(logic["NOT"])
        return 0

    def compute_similarity_metrics(self, rule1: CanonicalRule, rule2: CanonicalRule) -> dict[str, Any]:
        """
        Compute similarity metrics between two canonical rules.

        Args:
            rule1: First canonical rule
            rule2: Second canonical rule

        Returns:
            Dictionary with similarity metrics
        """
        semantic_result = self.compare_precomputed_semantics(
            self._semantic_fields_from_canonical(rule1),
            self._semantic_fields_from_canonical(rule2),
        )
        atom_jaccard = semantic_result["atom_jaccard"] if semantic_result else 0.0
        logic_similarity = semantic_result["logic_shape_similarity"] if semantic_result else 0.0

        # Check logsource match
        logsource_match = rule1.logsource.get("product") == rule2.logsource.get("product") and rule1.logsource.get(
            "category"
        ) == rule2.logsource.get("category")

        return {
            "atom_overlap": atom_jaccard,
            "logic_similarity": logic_similarity,
            "logsource_match": logsource_match,
            "weighted_similarity": self.compute_weighted_similarity(atom_jaccard, logic_similarity),
        }

    def compute_weighted_similarity(
        self, atom_jaccard: float, logic_similarity: float, service_penalty: float = 0.0, filter_penalty: float = 0.0
    ) -> float:
        """
        Compute weighted similarity score with penalties (v1.2).

        Args:
            atom_jaccard: Atom Jaccard similarity (0-1)
            logic_similarity: Logic shape similarity (0-1)
            service_penalty: Service mismatch penalty (0-1)
            filter_penalty: Filter divergence penalty (0-1)

        Returns:
            Weighted similarity (0-1), clamped to [0.0, 1.0]
        """
        similarity = 0.70 * atom_jaccard + 0.30 * logic_similarity - service_penalty - filter_penalty
        return max(0.0, min(1.0, similarity))

    def classify_novelty(self, exact_hash: str, matches: list[dict[str, Any]]) -> tuple[str, float]:
        """
        Classify novelty based on exact hash and similarity metrics.

        Args:
            exact_hash: Exact hash of proposed rule
            matches: List of match dictionaries with similarity metrics

        Returns:
            Tuple of (novelty_label, novelty_score)
        """
        if not matches:
            return (NoveltyLabel.NOVEL, 1.0)

        top_match = matches[0]
        # Exact-hash duplicates score 0.0 (definitionally identical); every other
        # label uses the complement of weighted similarity as the novelty score.
        if top_match.get("exact_hash_match"):
            return (NoveltyLabel.DUPLICATE, 0.0)

        # Single source of truth for the legacy thresholds (shared with ai.py).
        label = classify_match_novelty(top_match)
        weighted_sim = top_match.get("similarity", 0.0)
        return (label, 1.0 - weighted_sim)

    def generate_explainability(
        self, proposed: CanonicalRule, candidate: CanonicalRule, _candidate_metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate explainability output showing differences.

        Args:
            proposed: Proposed canonical rule
            candidate: Candidate canonical rule
            _candidate_metadata: Metadata about candidate rule (reserved for future use)

        Returns:
            Dictionary with explainability fields
        """
        result = self.compare_precomputed_semantics(
            self._semantic_fields_from_canonical(proposed),
            self._semantic_fields_from_canonical(candidate),
        )
        if result is None:
            return {"shared_atoms": [], "added_atoms": [], "removed_atoms": [], "filter_differences": []}
        return {
            "shared_atoms": result["shared_atoms"],
            "added_atoms": result["added_atoms"],
            "removed_atoms": result["removed_atoms"],
            "filter_differences": result["filter_differences"],
        }

    def _atom_to_string(self, atom: dict[str, Any]) -> str:
        """Convert atom to human-readable string (v1.2)."""
        field = atom.get("field", "")
        op = atom.get("op", "")
        value = atom.get("value", "")

        if op:
            return f"{field}|{op}:{value}"
        return f"{field}:{value}"

    def _compute_service_penalty(self, service1: str | None, service2: str | None) -> float:
        """
        Compute service mismatch penalty (v1.2).

        Penalty applied only if both services are present and different.
        No penalty if either is missing.

        Returns:
            Penalty value (0.0 or SERVICE_PENALTY)
        """
        if service1 and service2:
            if service1 != service2:
                return self.SERVICE_PENALTY
        return 0.0

    def _compute_filter_penalty(self, rule1: CanonicalRule, rule2: CanonicalRule) -> float:
        """
        Compute filter divergence penalty (v1.2).

        Penalizes rules that differ in NOT logic (negative atoms).

        Returns:
            Penalty value (0.0 to max_penalty)
        """
        atoms1 = rule1.detection.get("atoms", [])
        atoms2 = rule2.detection.get("atoms", [])

        # Filter to negative atoms only
        negative_atoms1 = [a for a in atoms1 if a.get("polarity", "positive") == "negative"]
        negative_atoms2 = [a for a in atoms2 if a.get("polarity", "positive") == "negative"]

        if not negative_atoms1 and not negative_atoms2:
            return 0.0

        # Compute Jaccard similarity for negative atoms
        set1 = {self._atom_to_key(a) for a in negative_atoms1}
        set2 = {self._atom_to_key(a) for a in negative_atoms2}

        if not set1 and not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)
        filter_jaccard = intersection / union if union > 0 else 0.0

        # Apply penalty if below threshold
        jaccard_threshold = 0.5
        max_penalty = 0.10

        if filter_jaccard < jaccard_threshold:
            penalty = max_penalty * (1.0 - filter_jaccard)
            return min(penalty, max_penalty)

        return 0.0
