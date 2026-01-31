"""
Model inference service for observable extraction models.

Loads trained models and runs inference on article text.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ObservableModelInference:
    """Service for running inference with observable extraction models."""

    def __init__(self, model_path: str | None = None, model_name: str = "CMD", model_version: str | None = None):
        """
        Initialize the inference service.

        Args:
            model_path: Path to the trained model directory
            model_name: Name of the model (e.g., "CMD", "PROC_LINEAGE")
            model_version: Version identifier for the model
        """
        self.model_path = Path(model_path) if model_path else None
        self.model_name = model_name
        self.model_version = model_version
        self._model = None
        self._model_loaded = False

    def load_model(self) -> bool:
        """
        Load the model from disk.

        Returns:
            True if model loaded successfully, False otherwise
        """
        if self._model_loaded:
            return True

        if not self.model_path:
            logger.error(f"Model path is None for {self.model_name} v{self.model_version}")
            return False

        if not self.model_path.exists():
            logger.error(f"Model path does not exist: {self.model_path}")
            logger.error(f"Attempted to find model at: {self.model_path}")
            logger.error("Model may not have been trained yet. Check training logs.")
            return False

        try:
            if self.model_name == "CMD":
                try:
                    from Workshop.inference.extractor import CmdExtractor
                except ImportError as e:
                    logger.error(f"Workshop module not available: {e}")
                    return False
                self._model = CmdExtractor(str(self.model_path))
                self._model_loaded = True
                logger.info(f"Loaded CMD model from {self.model_path}")
                return True
            logger.error(f"Unsupported model name: {self.model_name}")
            return False
        except Exception as e:
            logger.error(f"Failed to load model: {e}", exc_info=True)
            return False

    def extract(self, text: str) -> list[dict]:
        """
        Extract observables from text.

        Args:
            text: Article text to extract from

        Returns:
            List of extracted observables, each with:
            - start: Character start position
            - end: Character end position
            - text: Extracted span text
            - label: Observable type label
        """
        if not self._model_loaded:
            if not self.load_model():
                return []

        try:
            if self.model_name == "CMD":
                result = self._model.extract(text)
                return result.get("spans", [])
            logger.error(f"Unsupported model name: {self.model_name}")
            return []
        except Exception as e:
            logger.error(f"Error during extraction: {e}", exc_info=True)
            return []

    @staticmethod
    def find_model_path(model_name: str, model_version: str | None = None) -> Path | None:
        """
        Find the path to a trained model.

        Models are stored in Workshop/models/{model_key}/{version} where model_key
        is typically "bert_base", "roberta_base", or "secbert".

        Args:
            model_name: Name of the model (e.g., "CMD")
            model_version: Version identifier (if None, uses latest)

        Returns:
            Path to model directory, or None if not found
        """
        base_dir = Path("Workshop/models")

        # Model keys to check (in order of preference)
        model_keys = ["bert_base", "roberta_base", "secbert"]

        if model_version:
            # Try each model_key with the specified version
            for model_key in model_keys:
                model_path = base_dir / model_key / model_version
                if model_path.exists() and (
                    (model_path / "pytorch_model.bin").exists() or (model_path / "model.safetensors").exists()
                ):
                    return model_path

            # Fallback: Check if model was saved directly under base_dir (wrong location from old training)
            fallback_path = base_dir / model_version
            if fallback_path.exists() and (
                (fallback_path / "pytorch_model.bin").exists() or (fallback_path / "model.safetensors").exists()
            ):
                logger.warning(f"Found model in incorrect location: {fallback_path}. Consider retraining to fix path.")
                return fallback_path

            # If specific version not found, log available versions
            logger.warning(f"Model version {model_version} not found. Checking for available versions...")
            for model_key in model_keys:
                model_type_dir = base_dir / model_key
                if model_type_dir.exists():
                    versions = [d.name for d in model_type_dir.iterdir() if d.is_dir() and d.name != "CHANGELOG.md"]
                    if versions:
                        logger.warning(f"Available versions in {model_key}: {sorted(versions, reverse=True)[:5]}")

        # Try to find latest version across all model_keys
        latest_path = None
        latest_version = None

        for model_key in model_keys:
            model_type_dir = base_dir / model_key
            if not model_type_dir.exists():
                continue

            # Find most recent version directory (exclude files like CHANGELOG.md)
            versions = [d for d in model_type_dir.iterdir() if d.is_dir() and d.name != "CHANGELOG.md"]
            if not versions:
                continue

            # Sort by name (assuming timestamp-based naming)
            versions.sort(key=lambda x: x.name, reverse=True)
            candidate = versions[0]

            # Verify it's a valid model directory (has model files)
            if (candidate / "pytorch_model.bin").exists() or (candidate / "model.safetensors").exists():
                # Keep the most recent across all model_keys
                if latest_version is None or candidate.name > latest_version:
                    latest_version = candidate.name
                    latest_path = candidate

        if latest_path:
            logger.info(f"Using latest available model: {latest_path}")

        return latest_path
