"""Train SecBERT span extractor."""

from Workshop.training.train_common import run_training
from Workshop.utilities.tokenizer_utils import MODEL_PRESETS


if __name__ == "__main__":
    run_training("secbert", MODEL_PRESETS["secbert"])
