# Hugging Face Hub Integration for FindTuna Fine-tuning

This integration replaces Google Drive with Hugging Face Hub for model storage and sharing, providing a more streamlined and professional approach to model management.

## 🎯 Benefits of Hugging Face Hub

- **No Google Drive Required**: Eliminates dependency on Google Drive
- **Professional Model Sharing**: Industry-standard platform for ML models
- **Version Control**: Built-in versioning and model management
- **Easy Access**: Models accessible via simple Python imports
- **Team Collaboration**: Built-in sharing and collaboration features
- **Public/Private Models**: Choose visibility for your models
- **Model Cards**: Automatic documentation and metadata

## 🚀 Quick Start

### 1. Setup Hugging Face Hub
```bash
# Run the setup script
./setup_huggingface_hub.sh

# Or manually install
pip install huggingface_hub
```

### 2. Get Your Token
1. Create account at: https://huggingface.co/join
2. Get token at: https://huggingface.co/settings/tokens
3. Set environment variable:
```bash
export HF_TOKEN=your_token_here
```

### 3. Use the Interface
1. Start fine-tuning UI: `python3 configurable_fine_tune_ui.py`
2. Open http://localhost:5003
3. Check "Push model to Hugging Face Hub"
4. Enter model ID: `username/my-cti-model`
5. Start training

## 📊 Features

### Model Storage Options
- **Local Only**: Save models locally (default)
- **Hugging Face Hub**: Push to Hub for sharing and collaboration
- **Both**: Save locally AND push to Hub

### Training Methods
- **Local Training**: CPU/MPS training with local storage
- **Colab GPU Training**: Free GPU training with Hub push support

### Model Sharing
- **Public Models**: Available to everyone
- **Private Models**: Share with specific users
- **Organization Models**: Share within your team

## 🔧 Usage Examples

### Basic Training (Local Only)
```python
from src.utils.shared_training import FineTuningTrainer

trainer = FineTuningTrainer(device="cpu")
trainer_result, output_dir = trainer.fine_tune_model(
    "microsoft/Phi-3-mini-4k-instruct",
    training_data,
    epochs=3,
    learning_rate=5e-5,
    push_to_hub=False
)
```

### Training with Hub Push
```python
trainer_result, output_dir = trainer.fine_tune_model(
    "microsoft/Phi-3-mini-4k-instruct",
    training_data,
    epochs=3,
    learning_rate=5e-5,
    push_to_hub=True,
    hub_model_id="username/my-cti-model"
)
```

### Using Your Trained Model
```python
from transformers import AutoTokenizer, AutoModelForCausalLM

# Load from Hugging Face Hub
model = AutoModelForCausalLM.from_pretrained("username/my-cti-model")
tokenizer = AutoTokenizer.from_pretrained("username/my-cti-model")

# Use the model
inputs = tokenizer("Attackers ran powershell.exe", return_tensors="pt")
outputs = model.generate(**inputs, max_length=512)
response = tokenizer.decode(outputs[0], skip_special_tokens=True)
```

## 🌐 Web Interface

### Hugging Face Hub Status
- **Green**: Authenticated and ready to push models
- **Red**: Not authenticated - set HF_TOKEN to enable

### Training Options
- **Push to Hub**: Checkbox to enable Hub push
- **Model ID**: Enter your desired model ID (username/model-name)
- **Training Method**: Choose local or Colab GPU

### Results
- **Local Path**: Where model is saved locally
- **Hub URL**: Link to your model on Hugging Face Hub
- **Model Card**: Automatic documentation

## 📁 File Structure

```
src/utils/
├── shared_training.py          # Core training logic with Hub support
├── colab_integration.py        # Colab integration with Hub support
└── ...

colab_finetune_backend.ipynb   # Colab notebook with Hub integration
configurable_fine_tune_ui.py    # Web UI with Hub options
templates/
└── configurable_fine_tune.html # UI template with Hub controls
```

## 🔐 Authentication Methods

### Method 1: Environment Variable (Recommended)
```bash
export HF_TOKEN=your_token_here
```

### Method 2: Interactive Login
```bash
huggingface-cli login
```

### Method 3: Programmatic Login
```python
from huggingface_hub import login
login(token="your_token_here")
```

## 🎨 Model Naming Conventions

### Recommended Format
- `username/cti-hunt-model-v1`
- `organization/phi3-cti-detection`
- `username/sigma-rule-generator`

### Best Practices
- Use descriptive names
- Include version numbers
- Use hyphens instead of underscores
- Keep names concise but clear

## 🔄 Migration from Google Drive

### What Changed
- **Storage**: Google Drive → Hugging Face Hub
- **Authentication**: Google OAuth → HF Token
- **Sharing**: Drive links → Hub URLs
- **Access**: Drive API → Transformers library

### Migration Steps
1. Export models from Google Drive
2. Set up Hugging Face Hub authentication
3. Re-upload models to Hub with new naming
4. Update any scripts using old Drive paths

## 🛠️ Troubleshooting

### Authentication Issues
```bash
# Check token
echo $HF_TOKEN

# Test authentication
python3 -c "from huggingface_hub import whoami; print(whoami())"
```

### Model Push Failures
- Check token permissions
- Verify model ID format
- Ensure internet connection
- Check Hub storage limits

### Import Errors
```bash
# Install missing packages
pip install huggingface_hub transformers

# Update packages
pip install --upgrade huggingface_hub transformers
```

## 📈 Advanced Features

### Model Cards
- Automatic generation of model documentation
- Training metrics and parameters
- Usage examples and limitations
- Citation information

### Version Control
- Multiple model versions
- Easy rollback to previous versions
- Change tracking and history

### Team Collaboration
- Add collaborators to private models
- Organization-level sharing
- Permission management

## 🎯 Next Steps

1. **Set up authentication**: Get your HF token
2. **Test the integration**: Run a small training job
3. **Create your first model**: Train and push to Hub
4. **Share with team**: Add collaborators
5. **Build workflows**: Integrate with your CI/CD

## 📚 Resources

- [Hugging Face Hub Documentation](https://huggingface.co/docs/hub)
- [Transformers Library](https://huggingface.co/docs/transformers)
- [Model Cards Guide](https://huggingface.co/docs/hub/model-cards)
- [Token Management](https://huggingface.co/settings/tokens)

## 🆘 Support

For issues with Hugging Face Hub integration:
1. Check authentication status in the UI
2. Verify token permissions
3. Test with a simple model push
4. Review Hub documentation
5. Check network connectivity

The integration provides a professional, scalable solution for model management without the complexity of Google Drive setup.
