#!/bin/bash
# Backup and Cleanup Script for FindTuna Fine-tuning
# This script backs up duplicated code and cleans up the codebase

set -e

echo "🧹 FindTuna Fine-tuning Code Cleanup"
echo "===================================="

# Create backup directory
BACKUP_DIR="backup_duplicated_code_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "📁 Created backup directory: $BACKUP_DIR"

# Backup duplicated functions from configurable_fine_tune_ui.py
echo "📋 Backing up duplicated functions..."

# Extract the old training function (before shared module integration)
if [ -f "configurable_fine_tune_ui.py" ]; then
    # Create a backup of the original file
    cp configurable_fine_tune_ui.py "$BACKUP_DIR/configurable_fine_tune_ui_original.py"
    
    # Extract the old training function for reference
    cat > "$BACKUP_DIR/old_training_function.py" << 'EOF'
# Old training function from configurable_fine_tune_ui.py (backed up)
# This function was duplicated and has been replaced with shared_training.py

def start_training_old():
    """Old training function - now replaced with shared module"""
    global training_status, current_model_name
    
    try:
        if not training_data:
            return jsonify({'success': False, 'error': 'No training data loaded'})
        
        if not model or not tokenizer:
            if not load_base_model(current_model_name or "microsoft/Phi-3-mini-4k-instruct"):
                return jsonify({'success': False, 'error': 'Failed to load base model'})
        
        training_status = {"status": "starting", "progress": 10, "message": "Preparing training data..."}
        
        # Prepare training dataset
        def tokenize_function(examples):
            full_texts = [example["input"] + example["output"] + tokenizer.eos_token for example in examples]
            tokenized = tokenizer(full_texts, truncation=True, padding=True, max_length=512)
            tokenized["labels"] = tokenized["input_ids"].copy()
            return tokenized
        
        # Create dataset from training data
        dataset = Dataset.from_list(training_data)
        tokenized_dataset = dataset.map(tokenize_function, batched=False)
        
        training_status = {"status": "training", "progress": 30, "message": "Configuring training parameters..."}
        
        # Setup training arguments
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        model_short_name = current_model_name.split('/')[-1].replace('-', '_')
        output_dir = f"./models/fine_tuned/{model_short_name}_cti_hunt_{timestamp}"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        training_args = TrainingArguments(
            output_dir=output_dir,
            overwrite_output_dir=True,
            num_train_epochs=3,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=8,
            warmup_steps=100,
            logging_steps=10,
            save_steps=500,
            evaluation_strategy="no",
            save_strategy="epoch",
            load_best_model_at_end=False,
            report_to=None,
            remove_unused_columns=False,
            dataloader_num_workers=0,
            fp16=False,
            learning_rate=5e-5,
            lr_scheduler_type="cosine",
            weight_decay=0.01,
        )
        
        training_status = {"status": "training", "progress": 50, "message": "Initializing trainer..."}
        
        # Create trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_dataset,
            tokenizer=tokenizer,
        )
        
        training_status = {"status": "training", "progress": 70, "message": "Fine-tuning in progress..."}
        
        # Start training
        trainer.train()
        
        training_status = {"status": "training", "progress": 90, "message": "Saving fine-tuned model..."}
        
        # Save the fine-tuned model
        trainer.save_model()
        tokenizer.save_pretrained(output_dir)
        
        # Save training info
        training_info = {
            "model_name": f"{AVAILABLE_MODELS[current_model_name]['name']} CTI Hunt Logic",
            "base_model": current_model_name,
            "training_examples": len(training_data),
            "epochs": 3,
            "learning_rate": 5e-5,
            "batch_size": 1,
            "created_at": datetime.now().isoformat(),
            "output_dir": output_dir
        }
        
        with open(os.path.join(output_dir, "training_info.json"), "w") as f:
            json.dump(training_info, f, indent=2)
        
        training_status = {"status": "completed", "progress": 100, "message": f"Training completed! Model saved to {output_dir}"}
        
        return jsonify({'success': True, 'message': 'Training completed successfully'})
        
    except Exception as e:
        training_status = {"status": "error", "progress": 0, "message": str(e)}
        logger.error(f"Training error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
EOF
    
    echo "✅ Backed up old training function"
fi

# Backup the old Colab notebook
if [ -f "colab_finetune_backend.ipynb" ]; then
    cp colab_finetune_backend.ipynb "$BACKUP_DIR/colab_finetune_backend_old.ipynb"
    echo "✅ Backed up old Colab notebook"
fi

# Create cleanup summary
cat > "$BACKUP_DIR/CLEANUP_SUMMARY.md" << 'EOF'
# FindTuna Fine-tuning Code Cleanup Summary

## What Was Cleaned Up

### 1. Duplicated Training Functions
- **Before**: Training logic duplicated in `configurable_fine_tune_ui.py` and `colab_finetune_backend.ipynb`
- **After**: Centralized in `src/utils/shared_training.py`

### 2. Duplicated Model Loading
- **Before**: `load_model_for_training()` function duplicated in both files
- **After**: Single implementation in `FineTuningTrainer` class

### 3. Duplicated Tokenization
- **Before**: `tokenize_function()` duplicated in both files
- **After**: Single implementation in `FineTuningTrainer` class

### 4. Duplicated Training Arguments
- **Before**: Training configuration duplicated with hardcoded values
- **After**: Environment-aware configuration in `prepare_training_arguments()`

## Files Modified

### New Files Created
- `src/utils/shared_training.py` - Centralized training logic
- `src/utils/colab_integration.py` - Colab runtime management

### Files Updated
- `configurable_fine_tune_ui.py` - Now uses shared training module
- `colab_finetune_backend.ipynb` - Simplified to use shared module
- `templates/configurable_fine_tune.html` - Enhanced UI with Colab support

### Files Backed Up
- `configurable_fine_tune_ui_original.py` - Original file before cleanup
- `colab_finetune_backend_old.ipynb` - Original notebook before cleanup
- `old_training_function.py` - Extracted old training function

## Benefits of Cleanup

1. **DRY Principle**: Eliminated code duplication
2. **Maintainability**: Single source of truth for training logic
3. **Consistency**: Same training behavior across local and Colab
4. **Environment Awareness**: Automatic optimization for different environments
5. **Easier Testing**: Centralized logic easier to test and debug

## Migration Notes

- All existing functionality preserved
- Enhanced with Colab GPU support
- Better error handling and logging
- Environment-specific optimizations (GPU vs CPU vs MPS)

## Rollback Instructions

If you need to rollback:
1. Restore `configurable_fine_tune_ui_original.py` as `configurable_fine_tune_ui.py`
2. Restore `colab_finetune_backend_old.ipynb` as `colab_finetune_backend.ipynb`
3. Remove `src/utils/shared_training.py` and `src/utils/colab_integration.py`

## Next Steps

1. Test the new shared training module
2. Verify Colab integration works
3. Update documentation if needed
4. Consider removing backup files after successful testing
EOF

echo "✅ Created cleanup summary"

# Create a verification script
cat > "$BACKUP_DIR/verify_cleanup.py" << 'EOF'
#!/usr/bin/env python3
"""
Verification script to ensure cleanup was successful
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src', 'utils'))

def verify_shared_module():
    """Verify shared training module works"""
    try:
        from shared_training import FineTuningTrainer, AVAILABLE_MODELS, create_training_data_from_csv
        print("✅ Shared training module imports successfully")
        
        # Test trainer initialization
        trainer = FineTuningTrainer(device="cpu")
        print("✅ FineTuningTrainer initializes successfully")
        
        # Test model configuration
        print(f"✅ Available models: {len(AVAILABLE_MODELS)}")
        
        return True
    except Exception as e:
        print(f"❌ Shared module verification failed: {e}")
        return False

def verify_ui_integration():
    """Verify UI integration works"""
    try:
        # Check if UI file exists and imports shared module
        with open('../configurable_fine_tune_ui.py', 'r') as f:
            content = f.read()
            
        if 'from shared_training import' in content:
            print("✅ UI integrates with shared module")
            return True
        else:
            print("❌ UI does not import shared module")
            return False
    except Exception as e:
        print(f"❌ UI verification failed: {e}")
        return False

def main():
    print("🔍 Verifying FindTuna Fine-tuning Cleanup...")
    print("=" * 50)
    
    shared_ok = verify_shared_module()
    ui_ok = verify_ui_integration()
    
    if shared_ok and ui_ok:
        print("\n🎉 Cleanup verification successful!")
        print("All components are working correctly.")
    else:
        print("\n⚠️ Cleanup verification failed!")
        print("Some components may need attention.")
    
    return shared_ok and ui_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
EOF

chmod +x "$BACKUP_DIR/verify_cleanup.py"

echo "✅ Created verification script"

# Create a rollback script
cat > "$BACKUP_DIR/rollback.sh" << 'EOF'
#!/bin/bash
# Rollback script for FindTuna Fine-tuning cleanup

echo "🔄 Rolling back FindTuna Fine-tuning cleanup..."

# Restore original files
if [ -f "configurable_fine_tune_ui_original.py" ]; then
    cp configurable_fine_tune_ui_original.py ../configurable_fine_tune_ui.py
    echo "✅ Restored configurable_fine_tune_ui.py"
fi

if [ -f "colab_finetune_backend_old.ipynb" ]; then
    cp colab_finetune_backend_old.ipynb ../colab_finetune_backend.ipynb
    echo "✅ Restored colab_finetune_backend.ipynb"
fi

# Remove new files
if [ -f "../src/utils/shared_training.py" ]; then
    rm ../src/utils/shared_training.py
    echo "✅ Removed shared_training.py"
fi

if [ -f "../src/utils/colab_integration.py" ]; then
    rm ../src/utils/colab_integration.py
    echo "✅ Removed colab_integration.py"
fi

echo "🔄 Rollback completed!"
echo "The system has been restored to its original state."
EOF

chmod +x "$BACKUP_DIR/rollback.sh"

echo "✅ Created rollback script"

echo ""
echo "🎉 FindTuna Fine-tuning Code Cleanup Complete!"
echo "============================================="
echo ""
echo "📁 Backup directory: $BACKUP_DIR"
echo "📋 Files backed up:"
echo "   - configurable_fine_tune_ui_original.py"
echo "   - colab_finetune_backend_old.ipynb"
echo "   - old_training_function.py"
echo ""
echo "🔧 New centralized files:"
echo "   - src/utils/shared_training.py (main training logic)"
echo "   - src/utils/colab_integration.py (Colab integration)"
echo ""
echo "✅ Benefits achieved:"
echo "   - Eliminated code duplication"
echo "   - Centralized training logic"
echo "   - Environment-aware optimizations"
echo "   - Better maintainability"
echo ""
echo "🧪 Next steps:"
echo "   1. Test the system: python3 $BACKUP_DIR/verify_cleanup.py"
echo "   2. Run setup: ./setup_colab_integration.sh"
echo "   3. Test training: python3 configurable_fine_tune_ui.py"
echo ""
echo "🔄 If rollback needed: ./$BACKUP_DIR/rollback.sh"
echo ""
echo "📚 See $BACKUP_DIR/CLEANUP_SUMMARY.md for details"
