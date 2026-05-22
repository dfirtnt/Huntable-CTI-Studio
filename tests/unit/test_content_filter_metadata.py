"""Contract tests for the model metadata sidecar.

The sidecar (`<model_path>.meta.json`) records which featurizer was used to
train each pkl, so load_model() can auto-align self.feature_version with the
on-disk model. Added 2026-05-21 after a class of train/serve skew bugs ("ML
processing failed") caused by inference paths using the wrong featurizer.

Locks the contract:
- train_model() writes the sidecar with the current feature_version
- load_model() reads the sidecar and overrides self.feature_version
- legacy pkls (no sidecar) default to v1, matching the historic training default
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


def _make_fake_model(tmp_path: Path) -> Path:
    """Drop a trivial sklearn estimator at tmp_path / 'fake.pkl'."""
    import numpy as np
    from sklearn.dummy import DummyClassifier

    clf = DummyClassifier(strategy="most_frequent")
    clf.fit(np.zeros((4, 5)), [0, 1, 0, 1])
    path = tmp_path / "fake.pkl"
    joblib.dump(clf, path)
    return path


class TestSidecarWrite:
    def test_train_model_writes_sidecar(self, tmp_path) -> None:
        """When train_model() succeeds it must drop a sidecar next to the pkl."""
        from src.utils.content_filter import ContentFilter

        # Build a tiny CSV to drive train_model()
        csv_path = tmp_path / "train.csv"
        csv_path.write_text(
            "highlighted_text,classification\n"
            "powershell -ep bypass -c IEX,Huntable\n"
            "sc delete SgrmAgent,Huntable\n"
            "regsvr32 /S C:\\foo.dll,Huntable\n"
            "Read our white paper today,Not Huntable\n"
            "Book a demo to learn more,Not Huntable\n"
            "Contact sales for a quote,Not Huntable\n"
            "Our managed platform empowers your team,Not Huntable\n"
            "Best in class solution,Not Huntable\n",
        )
        model_path = tmp_path / "model.pkl"

        cf = ContentFilter(model_path=str(model_path), feature_version="v3")
        result = cf.train_model(training_data_path=str(csv_path))

        assert result["success"] is True
        meta_path = tmp_path / "model.pkl.meta.json"
        assert meta_path.exists(), "train_model() did not write meta sidecar"

        meta = json.loads(meta_path.read_text())
        assert meta["feature_version"] == "v3"
        assert "saved_at" in meta


class TestSidecarRead:
    def test_load_model_aligns_to_sidecar_v3(self, tmp_path) -> None:
        """A pkl with a v3 sidecar must coerce a fresh ContentFilter to v3."""
        from src.utils.content_filter import ContentFilter

        model_path = _make_fake_model(tmp_path)
        meta_path = model_path.with_suffix(".pkl.meta.json")
        meta_path.write_text(json.dumps({"feature_version": "v3", "saved_at": "2026-05-21T00:00:00Z"}))

        # Instantiate with mismatched default to prove load_model() overrides
        cf = ContentFilter(model_path=str(model_path), feature_version="v1")
        assert cf.load_model() is True
        assert cf.feature_version == "v3", "load_model() must adopt sidecar version"

    def test_load_model_aligns_to_sidecar_v2(self, tmp_path) -> None:
        from src.utils.content_filter import ContentFilter

        model_path = _make_fake_model(tmp_path)
        meta_path = model_path.with_suffix(".pkl.meta.json")
        meta_path.write_text(json.dumps({"feature_version": "v2"}))

        cf = ContentFilter(model_path=str(model_path), feature_version="v3")
        cf.load_model()
        assert cf.feature_version == "v2"

    def test_load_model_no_sidecar_defaults_to_v1(self, tmp_path) -> None:
        """Legacy pkl with no sidecar must coerce to v1 (the historic default
        at training time), NOT the current __init__ default. Otherwise loading
        an old v1 pkl while ContentFilter defaults to v3 produces a feature
        shape mismatch -- the exact bug that broke chunk-debug on 2026-05-21."""
        from src.utils.content_filter import ContentFilter

        model_path = _make_fake_model(tmp_path)
        # Deliberately no meta sidecar

        cf = ContentFilter(model_path=str(model_path), feature_version="v3")
        cf.load_model()
        assert cf.feature_version == "v1", (
            "Legacy pkl must default to v1, not the current __init__ default. "
            "Otherwise restoring an old model produces silent shape mismatch."
        )

    def test_load_model_invalid_sidecar_defaults_to_v1(self, tmp_path) -> None:
        """Corrupt sidecar should fall through to legacy v1, not raise."""
        from src.utils.content_filter import ContentFilter

        model_path = _make_fake_model(tmp_path)
        meta_path = model_path.with_suffix(".pkl.meta.json")
        meta_path.write_text("not valid json {{{")

        cf = ContentFilter(model_path=str(model_path), feature_version="v3")
        cf.load_model()
        assert cf.feature_version == "v1"


class TestRoundTrip:
    def test_train_then_load_preserves_feature_version(self, tmp_path) -> None:
        """End-to-end: train at v3, then a fresh instance loads and reports v3."""
        from src.utils.content_filter import ContentFilter

        csv_path = tmp_path / "train.csv"
        csv_path.write_text(
            "highlighted_text,classification\n"
            "powershell -ep bypass IEX(New-Object Net.WebClient).DownloadString,Huntable\n"
            "schtasks /create /tn evil,Huntable\n"
            "HKLM\\Software\\Microsoft\\Run\\X,Huntable\n"
            "sc delete WinDefend,Huntable\n"
            "Read our white paper,Not Huntable\n"
            "Subscribe to our newsletter,Not Huntable\n"
            "Book a demo today,Not Huntable\n"
            "Contact sales now,Not Huntable\n",
        )
        model_path = tmp_path / "model.pkl"

        # Train at v3
        trainer = ContentFilter(model_path=str(model_path), feature_version="v3")
        assert trainer.train_model(training_data_path=str(csv_path))["success"]

        # Load with a different default; load_model() should switch us to v3
        loader = ContentFilter(model_path=str(model_path), feature_version="v1")
        assert loader.load_model()
        assert loader.feature_version == "v3"
