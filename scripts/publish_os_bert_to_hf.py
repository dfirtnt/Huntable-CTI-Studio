#!/usr/bin/env python3
"""
Publish OS-BERT model to HuggingFace Hub.

Usage:
    python scripts/publish_os_bert_to_hf.py \
        --model-dir models/os-bert \
        --repo-id your-username/os-bert \
        --commit-message "Initial release of OS-BERT"
"""

import argparse
import json
from pathlib import Path
from typing import Optional

try:
    from huggingface_hub import HfApi, create_repo, login
except ImportError:
    print("Error: huggingface_hub not installed. Install with: pip install huggingface_hub")
    exit(1)


def load_metadata(model_dir: Path) -> dict:
    """Load training metadata if available."""
    metadata_path = model_dir / "training_metadata.json"
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            return json.load(f)
    return {}


def create_model_card(model_dir: Path, repo_id: str, metadata: dict) -> str:
    """Create model card content."""
    base_model = metadata.get("base_model", "Unknown")
    num_labels = metadata.get("num_labels", 5)
    labels = metadata.get("labels", ["Windows", "Linux", "MacOS", "multiple", "Unknown"])
    training_samples = metadata.get("training_samples", "Unknown")
    test_samples = metadata.get("test_samples", "Unknown")
    
    test_metrics = metadata.get("test_metrics", {})
    accuracy = test_metrics.get("accuracy", 0.0)
    f1 = test_metrics.get("f1", 0.0)
    precision = test_metrics.get("precision", 0.0)
    recall = test_metrics.get("recall", 0.0)
    
    model_card = f"""---
license: apache-2.0
tags:
- cybersecurity
- threat-intelligence
- os-detection
- classification
- bert
- cti
datasets:
- custom
metrics:
- accuracy
- f1
- precision
- recall
---

# OS-BERT

Fine-tuned BERT model for operating system detection in cybersecurity threat intelligence articles.

## Model Description

OS-BERT is fine-tuned from {base_model} for multi-class OS classification. It identifies which operating system(s) a threat intelligence article focuses on.

**Base Model:** {base_model}  
**Task:** Multi-class classification  
**Classes:** {', '.join(labels)}  
**Number of Labels:** {num_labels}

## Intended Use

- **Primary Use**: Classify threat intelligence articles by target operating system
- **Domain**: Cybersecurity threat intelligence
- **Classes**: {', '.join(labels)}

## Training Data

- **Source**: CTI Scraper database (high-quality threat intelligence articles)
- **Labeling**: GPT-4o assisted labeling
- **Training Samples**: {training_samples}
- **Test Samples**: {test_samples}

## Performance

- **Accuracy**: {accuracy:.2%}
- **F1 Score**: {f1:.2%}
- **Precision**: {precision:.2%}
- **Recall**: {recall:.2%}

## Usage

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# Load model
tokenizer = AutoTokenizer.from_pretrained("{repo_id}")
model = AutoModelForSequenceClassification.from_pretrained("{repo_id}")
model.eval()

# Classify text
text = "Article content here..."
inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)

with torch.no_grad():
    outputs = model(**inputs)
    predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
    predicted_class = torch.argmax(predictions, dim=-1).item()

OS_LABELS = {labels}
print(f"Predicted OS: {{OS_LABELS[predicted_class]}}")
print(f"Confidence: {{predictions[0][predicted_class]:.2%}}")
```

## Limitations

- Trained on English-language threat intelligence articles
- May not generalize to other domains
- Requires sufficient context (recommended: 200+ characters)
- Performance depends on training data quality and quantity

## Citation

If you use this model, please cite:

```bibtex
@misc{{os-bert,
  author = {{CTI Scraper}},
  title = {{OS-BERT: Operating System Detection for Threat Intelligence}},
  year = {{2025}},
  publisher = {{HuggingFace}},
  howpublished = {{\\url{{https://huggingface.co/{repo_id}}}}}
}}
```

## License

Apache 2.0
"""
    return model_card


def main():
    parser = argparse.ArgumentParser(description="Publish OS-BERT to HuggingFace")
    parser.add_argument(
        '--model-dir',
        type=Path,
        required=True,
        help='Directory containing fine-tuned model'
    )
    parser.add_argument(
        '--repo-id',
        type=str,
        required=True,
        help='HuggingFace repository ID (e.g., username/os-bert)'
    )
    parser.add_argument(
        '--commit-message',
        type=str,
        default='Upload OS-BERT model',
        help='Commit message for upload'
    )
    parser.add_argument(
        '--token',
        type=str,
        default=None,
        help='HuggingFace token (or set HF_TOKEN env var)'
    )
    parser.add_argument(
        '--private',
        action='store_true',
        help='Make repository private'
    )
    
    args = parser.parse_args()
    
    if not args.model_dir.exists():
        print(f"Error: Model directory not found: {args.model_dir}")
        return
    
    # Check required files
    required_files = ["config.json", "pytorch_model.bin"]
    missing_files = [f for f in required_files if not (args.model_dir / f).exists()]
    if missing_files:
        print(f"Error: Missing required files: {missing_files}")
        print(f"Make sure you've fine-tuned the model first.")
        return
    
    print("="*80)
    print("PUBLISHING OS-BERT TO HUGGINGFACE")
    print("="*80)
    
    # Login
    print(f"\nLogging in to HuggingFace...")
    try:
        if args.token:
            login(token=args.token)
        else:
            login()  # Uses HF_TOKEN env var or prompts for token
    except Exception as e:
        print(f"Error logging in: {e}")
        print("Set HF_TOKEN environment variable or use --token flag")
        return
    
    # Load metadata
    metadata = load_metadata(args.model_dir)
    
    # Create model card
    print(f"\nCreating model card...")
    model_card = create_model_card(args.model_dir, args.repo_id, metadata)
    
    # Save model card
    readme_path = args.model_dir / "README.md"
    with open(readme_path, 'w') as f:
        f.write(model_card)
    print(f"✅ Model card saved to {readme_path}")
    
    # Create repository
    print(f"\nCreating repository: {args.repo_id}...")
    api = HfApi()
    try:
        create_repo(
            repo_id=args.repo_id,
            repo_type="model",
            private=args.private,
            exist_ok=True
        )
        print(f"✅ Repository created/exists")
    except Exception as e:
        print(f"⚠️  Repository creation: {e}")
    
    # Upload model
    print(f"\nUploading model to HuggingFace...")
    print(f"  Repository: {args.repo_id}")
    print(f"  Directory: {args.model_dir}")
    
    try:
        api.upload_folder(
            folder_path=str(args.model_dir),
            repo_id=args.repo_id,
            repo_type="model",
            commit_message=args.commit_message
        )
        print(f"\n✅ Model uploaded successfully!")
        print(f"✅ View at: https://huggingface.co/{args.repo_id}")
    except Exception as e:
        print(f"\n❌ Upload failed: {e}")
        return
    
    print(f"\n" + "="*80)
    print("PUBLICATION COMPLETE")
    print("="*80)
    print(f"\nYour model is now available at:")
    print(f"  https://huggingface.co/{args.repo_id}")
    print(f"\nTo use it:")
    print(f"  from transformers import AutoTokenizer, AutoModelForSequenceClassification")
    print(f"  tokenizer = AutoTokenizer.from_pretrained('{args.repo_id}')")
    print(f"  model = AutoModelForSequenceClassification.from_pretrained('{args.repo_id}')")


if __name__ == "__main__":
    main()

