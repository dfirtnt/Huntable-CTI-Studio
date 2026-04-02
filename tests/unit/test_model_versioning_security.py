"""
Security tests for MLModelVersionManager.

Covers:
- _validate_model_path(): path traversal prevention
- activate_version(): rejects paths outside models directory
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.utils.model_versioning import MLModelVersionManager

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# _validate_model_path() — static method, no DB needed
# ---------------------------------------------------------------------------


class TestValidateModelPath:
    """_validate_model_path: ensures paths stay within allowed directories."""

    def test_valid_path_within_models_dir(self, tmp_path):
        """A path inside models/ is accepted and returned resolved."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        artifact = models_dir / "content_filter_v3.pkl"
        artifact.write_bytes(b"fake")

        with patch.object(
            MLModelVersionManager,
            "ALLOWED_MODEL_DIRS",
            (str(models_dir),),
        ):
            result = MLModelVersionManager._validate_model_path(str(artifact))
        assert result == str(artifact.resolve())

    def test_rejects_path_traversal_with_dotdot(self, tmp_path):
        """A path containing ../ that escapes models/ is rejected."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        traversal_path = str(models_dir / ".." / "etc" / "passwd")

        with patch.object(
            MLModelVersionManager,
            "ALLOWED_MODEL_DIRS",
            (str(models_dir),),
        ):
            with pytest.raises(ValueError, match="outside the allowed directories"):
                MLModelVersionManager._validate_model_path(traversal_path)

    def test_rejects_absolute_path_outside_models(self):
        """An absolute path to /tmp is rejected."""
        with pytest.raises(ValueError, match="outside the allowed directories"):
            MLModelVersionManager._validate_model_path("/tmp/evil_model.pkl")

    def test_rejects_relative_path_escaping_models(self, tmp_path):
        """A relative path that resolves outside the models dir is rejected."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        # Path that resolves to tmp_path, not models_dir
        escape_path = str(models_dir / ".." / "secret.pkl")

        with patch.object(
            MLModelVersionManager,
            "ALLOWED_MODEL_DIRS",
            (str(models_dir),),
        ):
            with pytest.raises(ValueError, match="outside the allowed directories"):
                MLModelVersionManager._validate_model_path(escape_path)

    def test_accepts_nested_subdirectory(self, tmp_path):
        """A path in a subdirectory of models/ is accepted."""
        models_dir = tmp_path / "models"
        sub = models_dir / "versions" / "v3"
        sub.mkdir(parents=True)
        artifact = sub / "content_filter.pkl"
        artifact.write_bytes(b"fake")

        with patch.object(
            MLModelVersionManager,
            "ALLOWED_MODEL_DIRS",
            (str(models_dir),),
        ):
            result = MLModelVersionManager._validate_model_path(str(artifact))
        assert result == str(artifact.resolve())


# ---------------------------------------------------------------------------
# activate_version() — path validation integration
# ---------------------------------------------------------------------------


def _make_db_manager(session_mock=None):
    if session_mock is None:
        session_mock = AsyncMock()
        session_mock.execute = AsyncMock()
        session_mock.commit = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session_mock)
    cm.__aexit__ = AsyncMock(return_value=None)
    db_manager = Mock()
    db_manager.get_session = Mock(return_value=cm)
    return db_manager, session_mock


def _make_version(id=3, version_number=3, model_file_path=None, is_current=False):
    v = Mock()
    v.id = id
    v.version_number = version_number
    v.model_file_path = model_file_path
    v.is_current = is_current
    return v


class TestActivateVersionPathValidation:
    """activate_version rejects path-traversal artifacts."""

    @pytest.mark.asyncio
    async def test_rejects_traversal_path_in_activate(self, tmp_path):
        """activate_version raises ValueError when artifact path escapes models dir."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        # Create an artifact OUTSIDE models dir
        evil = tmp_path / "evil.pkl"
        evil.write_bytes(b"malicious")

        version = _make_version(model_file_path=str(evil))
        db_manager, _ = _make_db_manager()
        mgr = MLModelVersionManager(db_manager)

        with (
            patch.object(mgr, "get_version_by_id", AsyncMock(return_value=version)),
            patch("src.utils.model_versioning.os.path.exists", return_value=True),
            patch.object(
                MLModelVersionManager,
                "ALLOWED_MODEL_DIRS",
                (str(models_dir),),
            ),
        ):
            with pytest.raises(ValueError, match="outside the allowed directories"):
                await mgr.activate_version(version.id)

    @pytest.mark.asyncio
    async def test_accepts_valid_path_in_activate(self, tmp_path):
        """activate_version succeeds when artifact is within models dir."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        artifact = models_dir / "content_filter_v3.pkl"
        artifact.write_bytes(b"valid model")

        version = _make_version(model_file_path=str(artifact))
        db_manager, _ = _make_db_manager()
        mgr = MLModelVersionManager(db_manager)

        with (
            patch.object(mgr, "get_version_by_id", AsyncMock(return_value=version)),
            patch("src.utils.model_versioning.os.path.exists", return_value=True),
            patch("src.utils.model_versioning.os.makedirs"),
            patch("src.utils.model_versioning.shutil.copy2"),
            patch("src.web.dependencies.get_content_filter") as mock_cf,
            patch.object(
                MLModelVersionManager,
                "ALLOWED_MODEL_DIRS",
                (str(models_dir),),
            ),
        ):
            mock_cf.cache_clear = Mock()
            result = await mgr.activate_version(version.id)

        assert result is True
