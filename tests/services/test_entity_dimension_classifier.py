"""Unit tests for the generic entity-dimension classifier (Phase D).

Reuses the platform-gate scoring idea for the Domains and Products dimensions:
keyword/entity KB -> weighted multi-label with an evidence floor. See
docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md (Phase D).
"""

import pytest

from src.services.entity_dimension_classifier import (
    classify_dimension,
    classify_products,
)

pytestmark = [pytest.mark.unit]

_DOMAINS = [
    {"match": "active directory", "labels": ["Identity"], "weight": 2},
    {"match": "kerberos", "labels": ["Identity"], "weight": 2},
    {"match": "exchange", "labels": ["Email"], "weight": 2},
    {"match": "kubernetes", "labels": ["Cloud"], "weight": 2},
    {"match": "okta", "labels": ["Identity", "Cloud"], "weight": 2},
]
_DOMAIN_LABELS = ["Identity", "Cloud", "Network", "Endpoint", "Email", "OT/ICS", "SaaS"]

_PRODUCTS = [
    {"match": "active directory", "product": "Active Directory"},
    {"match": "entra id", "product": "Entra ID"},
    {"match": "azure ad", "product": "Entra ID"},
    {"match": "cisco asa", "product": "Cisco ASA"},
]


def test_dimension_single_label():
    r = classify_dimension("Dumped creds from Active Directory and abused Kerberos.", _DOMAINS, _DOMAIN_LABELS)
    assert r.labels == ["Identity"]
    assert r.scores["Identity"] == 4.0
    assert "active directory" in r.evidence["Identity"]


def test_dimension_multi_label():
    r = classify_dimension("Compromised Exchange mailboxes then pivoted to Kubernetes.", _DOMAINS, _DOMAIN_LABELS)
    assert set(r.labels) == {"Email", "Cloud"}


def test_dimension_below_floor_is_empty():
    # A single weak signal (one match, weight 2 == floor) still counts; nothing matched -> empty.
    r = classify_dimension("No recognizable domain entities here.", _DOMAINS, _DOMAIN_LABELS)
    assert r.labels == []


def test_dimension_entry_with_two_labels_credits_both():
    r = classify_dimension("Okta SSO was abused for access.", _DOMAINS, _DOMAIN_LABELS)
    assert set(r.labels) >= {"Identity", "Cloud"}


def test_products_presence_based_dedup():
    products = classify_products("Targeted Active Directory; also Azure AD (Entra ID) and Cisco ASA.", _PRODUCTS)
    names = {p["product"] for p in products}
    assert names == {"Active Directory", "Entra ID", "Cisco ASA"}


def test_products_empty_when_none_present():
    assert classify_products("nothing notable", _PRODUCTS) == []
