# OS-BERT Fine-Tuning Guide

Complete guide for fine-tuning a BERT model for OS detection classification and publishing to HuggingFace.

## Overview

Fine-tuning BERT directly (vs. embeddings + classifier) trains the entire model end-to-end for OS classification. This can achieve better performance and produces a single model that can be published to HuggingFace.

## Architecture Comparison

### Current Approach (Embeddings + Classifier)
```
Article Content
    ↓
CTI-BERT (frozen) → Embedding (768-dim)
    ↓
RandomForest/LogisticRegression Classifier
    ↓
OS Label
```

### Fine-Tuned BERT Approach
```
Article Content
    ↓
BERT (fine-tuned) → Classification Head
    ↓
OS Label
```

**Advantages of Fine-Tuning:**
- End-to-end training (better feature learning)
- Single model file (easier deployment)
- Can publish to HuggingFace
- Better performance on domain-specific tasks
- Model learns task-specific representations

## Quick Start

### Step 1: Prepare Training Data

Use existing data preparation script:

```bash
python scripts/prepare_os_detection_training_data.py \
    --min-hunt-score 80.0 \
    --limit 200 \
    --output data/os_detection_training_data.json
```

**Recommended:** At least 100-200 samples per class for good performance.

### Step 2: Fine-Tune BERT

```bash
python scripts/finetune_os_bert.py \
    --data data/os_detection_training_data.json \
    --base-model ibm-research/CTI-BERT \
    --output-dir models/os-bert \
    --epochs 3 \
    --batch-size 16 \
    --learning-rate 2e-5 \
    --use-gpu
```

**Key Parameters:**
- `--base-model`: Starting model (CTI-BERT recommended for cybersecurity domain)
- `--epochs`: Training epochs (3-5 typically sufficient)
- `--batch-size`: Batch size (adjust based on GPU memory)
- `--learning-rate`: Learning rate (2e-5 is standard for BERT fine-tuning)
- `--use-gpu`: Enable GPU acceleration

### Step 3: Evaluate Model

The script automatically evaluates on a held-out test set and provides:
- Accuracy, F1, Precision, Recall
- Per-class classification report
- Confusion matrix

## Using the Fine-Tuned Model

### In Python

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# Load model
tokenizer = AutoTokenizer.from_pretrained("models/os-bert")
model = AutoModelForSequenceClassification.from_pretrained("models/os-bert")
model.eval()

# Classify text
text = "Article content here..."
inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)

with torch.no_grad():
    outputs = model(**inputs)
    predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
    predicted_class = torch.argmax(predictions, dim=-1).item()

OS_LABELS = ["Windows", "Linux", "MacOS", "multiple", "Unknown"]
print(f"Predicted OS: {OS_LABELS[predicted_class]}")
print(f"Confidence: {predictions[0][predicted_class]:.2%}")
```

### Integration with OSDetectionService

Modify `src/services/os_detection_service.py` to support fine-tuned models:

```python
# Add option to use fine-tuned model
def __init__(
    self,
    model_name: str = "ibm-research/CTI-BERT",
    use_finetuned: bool = False,
    finetuned_model_path: Optional[Path] = None,
    ...
):
    if use_finetuned and finetuned_model_path:
        self.model = AutoModelForSequenceClassification.from_pretrained(finetuned_model_path)
        # Use model directly for classification
    else:
        # Existing embedding + classifier approach
        ...
```

## Publishing to HuggingFace

### Prerequisites

1. **HuggingFace Account**: Create account at https://huggingface.co
2. **Install Hub Library**: `pip install huggingface_hub`
3. **Login**: `huggingface-cli login` (or set `HF_TOKEN` env var)

### Step 1: Create Model Card

Create `models/os-bert/README.md`:

```markdown
---
license: apache-2.0
tags:
- cybersecurity
- threat-intelligence
- os-detection
- classification
- bert
datasets:
- custom
metrics:
- accuracy
- f1
---

# OS-BERT

Fine-tuned BERT model for operating system detection in cybersecurity threat intelligence articles.

## Model Description

OS-BERT is fine-tuned from CTI-BERT (`ibm-research/CTI-BERT`) for multi-class OS classification. It identifies which operating system(s) a threat intelligence article focuses on.

## Intended Use

- **Primary Use**: Classify threat intelligence articles by target operating system
- **Domain**: Cybersecurity threat intelligence
- **Classes**: Windows, Linux, MacOS, multiple, Unknown

## Training Data

- **Source**: CTI Scraper database (high-quality threat intelligence articles)
- **Labeling**: GPT-4o assisted labeling
- **Training Samples**: [X] samples
- **Test Samples**: [Y] samples

## Performance

- **Accuracy**: [X]%
- **F1 Score**: [X]%
- **Precision**: [X]%
- **Recall**: [X]%

## Usage

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

tokenizer = AutoTokenizer.from_pretrained("your-username/os-bert")
model = AutoModelForSequenceClassification.from_pretrained("your-username/os-bert")

text = "Article content..."
inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
outputs = model(**inputs)
```

## Limitations

- Trained on English-language threat intelligence articles
- May not generalize to other domains
- Requires sufficient context (recommended: 200+ characters)

## Citation

If you use this model, please cite:

```bibtex
@misc{os-bert,
  author = {Your Name},
  title = {OS-BERT: Operating System Detection for Threat Intelligence},
  year = {2025},
  publisher = {HuggingFace},
  howpublished = {\url{https://huggingface.co/your-username/os-bert}}
}
```

## License

Apache 2.0
```

### Step 2: Upload Model

```python
from huggingface_hub import HfApi, create_repo
from pathlib import Path

# Initialize API
api = HfApi()

# Create repository (if doesn't exist)
repo_id = "your-username/os-bert"
try:
    create_repo(repo_id, repo_type="model", exist_ok=True)
except Exception as e:
    print(f"Repo may already exist: {e}")

# Upload model
api.upload_folder(
    folder_path="models/os-bert",
    repo_id=repo_id,
    repo_type="model",
    commit_message="Initial upload of OS-BERT fine-tuned model"
)
```

Or use CLI:

```bash
cd models/os-bert
huggingface-cli upload your-username/os-bert . --repo-type model
```

### Step 3: Verify Upload

Check your model at: `https://huggingface.co/your-username/os-bert`

## Naming Considerations

### "OS-BERT" Name

**Pros:**
- Clear and descriptive
- Follows BERT naming convention
- Easy to remember

**Considerations:**
- Check if name is already taken on HuggingFace
- Consider more specific name: `cti-os-bert`, `threat-intel-os-bert`
- Ensure it doesn't conflict with existing models

**Alternative Names:**
- `cti-os-bert` (emphasizes CTI domain)
- `threat-os-classifier` (more descriptive)
- `os-detection-bert` (explicit about task)

### HuggingFace Repository ID

Format: `username/model-name`

Examples:
- `your-username/os-bert`
- `your-username/cti-os-bert`
- `your-org/os-detection-bert`

## Best Practices

### 1. Training Data Quality

- **Minimum**: 50-100 samples per class
- **Recommended**: 200+ samples per class
- **Balance**: Ensure balanced class distribution
- **Quality**: Review LLM labels for accuracy

### 2. Hyperparameter Tuning

Common ranges:
- **Learning Rate**: 1e-5 to 5e-5 (start with 2e-5)
- **Batch Size**: 8-32 (adjust for GPU memory)
- **Epochs**: 3-5 (monitor for overfitting)
- **Max Length**: 512 (BERT standard)

### 3. Evaluation

- Use stratified train/test split
- Monitor validation metrics during training
- Use early stopping to prevent overfitting
- Evaluate on held-out test set
- Report per-class metrics

### 4. Model Card

Include:
- Model description and use case
- Training data details
- Performance metrics
- Limitations and biases
- Usage examples
- Citation information

### 5. Versioning

- Use semantic versioning (v1.0.0, v1.1.0, etc.)
- Tag releases on HuggingFace
- Document changes in model card

## Troubleshooting

### Low Performance

- **More Training Data**: Increase sample size
- **Better Labels**: Review and correct labeling errors
- **Hyperparameter Tuning**: Adjust learning rate, batch size
- **Different Base Model**: Try different BERT variants

### Overfitting

- **Early Stopping**: Use patience-based early stopping
- **Regularization**: Increase weight decay
- **More Data**: Collect more training samples
- **Data Augmentation**: Paraphrase or augment training texts

### GPU Memory Issues

- **Reduce Batch Size**: Lower `--batch-size`
- **Gradient Accumulation**: Use `gradient_accumulation_steps`
- **Mixed Precision**: Enable `fp16=True`
- **Shorter Sequences**: Reduce `--max-length`

## Comparison: Fine-Tuning vs. Embeddings + Classifier

| Aspect | Fine-Tuned BERT | Embeddings + Classifier |
|--------|----------------|------------------------|
| **Training** | End-to-end | Two-stage |
| **Model Size** | Single model | Model + classifier |
| **Performance** | Better (task-specific) | Good (frozen features) |
| **Deployment** | Easier (one model) | Two components |
| **HuggingFace** | Can publish | Cannot publish |
| **Training Time** | Longer | Faster |
| **Flexibility** | Less flexible | More flexible |

## Next Steps

1. **Collect More Data**: Increase training set size
2. **Hyperparameter Tuning**: Optimize learning rate, batch size
3. **Evaluate on Production**: Test on real articles
4. **Publish to HuggingFace**: Share with community
5. **Monitor Performance**: Track accuracy over time
6. **Iterate**: Retrain with more data and improvements

## Related Files

- `scripts/finetune_os_bert.py`: Fine-tuning script
- `scripts/prepare_os_detection_training_data.py`: Data preparation
- `src/services/os_detection_service.py`: Service implementation
- `docs/OS_DETECTION_CLASSIFIER_TRAINING.md`: Embeddings + classifier approach

