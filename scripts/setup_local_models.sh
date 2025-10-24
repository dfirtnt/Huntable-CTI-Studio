#!/bin/bash
# Model Setup Script for Local LLM Providers
# Downloads and manages models for MLX, llama.cpp, and LM Studio

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MODELS_DIR="models"
MLX_DIR="$MODELS_DIR/mlx"
GGUF_DIR="$MODELS_DIR/gguf"

# Model configurations
declare -A MLX_MODELS=(
    ["llama-3.2-1b-instruct"]="mlx-community/Llama-3.2-1B-Instruct-4bit"
    ["llama-3.2-3b-instruct"]="mlx-community/Llama-3.2-3B-Instruct-4bit"
    ["phi3-mini"]="mlx-community/Phi-3-mini-4k-instruct-4bit"
)

declare -A GGUF_MODELS=(
    ["llama-3.2-1b-instruct"]="microsoft/Llama-3.2-1B-Instruct-GGUF"
    ["llama-3.2-3b-instruct"]="microsoft/Llama-3.2-3B-Instruct-GGUF"
    ["phi3-mini"]="microsoft/Phi-3-mini-4k-instruct-gguf"
)

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  Local LLM Model Setup Script  ${NC}"
    echo -e "${BLUE}================================${NC}"
    echo
}

print_step() {
    echo -e "${YELLOW}[STEP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

check_dependencies() {
    print_step "Checking dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3 is required but not installed"
        exit 1
    fi
    
    # Check if we're on macOS (required for MLX and Metal)
    if [[ "$OSTYPE" != "darwin"* ]]; then
        print_error "This script is designed for macOS (Apple Silicon required for MLX)"
        exit 1
    fi
    
    print_success "Dependencies check passed"
}

create_directories() {
    print_step "Creating model directories..."
    
    mkdir -p "$MLX_DIR"
    mkdir -p "$GGUF_DIR"
    
    print_success "Directories created: $MLX_DIR, $GGUF_DIR"
}

install_packages() {
    print_step "Installing Python packages..."
    
    # Install huggingface-hub for model downloads
    pip3 install huggingface-hub --quiet
    
    # Install MLX (optional, will be installed if needed)
    if [[ "$1" == "--with-mlx" ]]; then
        print_info "Installing MLX packages..."
        pip3 install mlx-lm --quiet
        print_success "MLX packages installed"
    fi
    
    # Install llama-cpp-python (optional, will be installed if needed)
    if [[ "$1" == "--with-llamacpp" ]]; then
        print_info "Installing llama-cpp-python..."
        pip3 install llama-cpp-python --quiet
        print_success "llama-cpp-python installed"
    fi
    
    print_success "Package installation completed"
}

download_mlx_model() {
    local model_name=$1
    local hf_model=${MLX_MODELS[$model_name]}
    
    if [[ -z "$hf_model" ]]; then
        print_error "Unknown MLX model: $model_name"
        return 1
    fi
    
    print_step "Downloading MLX model: $model_name"
    
    local model_path="$MLX_DIR/$model_name"
    
    if [[ -d "$model_path" ]]; then
        print_info "Model already exists at $model_path"
        return 0
    fi
    
    # Download using huggingface-hub
    python3 -c "
from huggingface_hub import snapshot_download
import os

model_path = '$model_path'
hf_model = '$hf_model'

print(f'Downloading {hf_model} to {model_path}...')
snapshot_download(
    repo_id=hf_model,
    local_dir=model_path,
    local_dir_use_symlinks=False
)
print('Download completed!')
"
    
    print_success "MLX model downloaded: $model_name"
}

download_gguf_model() {
    local model_name=$1
    local hf_model=${GGUF_MODELS[$model_name]}
    
    if [[ -z "$hf_model" ]]; then
        print_error "Unknown GGUF model: $model_name"
        return 1
    fi
    
    print_step "Downloading GGUF model: $model_name"
    
    local model_path="$GGUF_DIR/$model_name.gguf"
    
    if [[ -f "$model_path" ]]; then
        print_info "Model already exists at $model_path"
        return 0
    fi
    
    # Download GGUF file
    python3 -c "
from huggingface_hub import hf_hub_download
import os

model_path = '$model_path'
hf_model = '$hf_model'

print(f'Downloading GGUF file from {hf_model}...')
downloaded_path = hf_hub_download(
    repo_id=hf_model,
    filename='*.gguf',
    local_dir='$GGUF_DIR',
    local_dir_use_symlinks=False
)
print(f'Download completed! File saved to: {downloaded_path}')
"
    
    print_success "GGUF model downloaded: $model_name"
}

setup_lmstudio_instructions() {
    print_step "LM Studio setup instructions"
    
    echo -e "${YELLOW}LM Studio Setup:${NC}"
    echo "1. Download LM Studio from: https://lmstudio.ai/"
    echo "2. Install and launch LM Studio"
    echo "3. Go to 'Models' tab and search for:"
    echo "   - llama-3.2-1b-instruct"
    echo "   - llama-3.2-3b-instruct"
    echo "4. Download the models you want to use"
    echo "5. Go to 'Server' tab and start the local server"
    echo "6. Set LMSTUDIO_ENABLED=true in your .env file"
    echo
}

verify_models() {
    print_step "Verifying downloaded models..."
    
    local verified=0
    local total=0
    
    # Check MLX models
    for model_name in "${!MLX_MODELS[@]}"; do
        total=$((total + 1))
        model_path="$MLX_DIR/$model_name"
        if [[ -d "$model_path" ]]; then
            print_success "MLX model verified: $model_name"
            verified=$((verified + 1))
        else
            print_info "MLX model not found: $model_name"
        fi
    done
    
    # Check GGUF models
    for model_name in "${!GGUF_MODELS[@]}"; do
        total=$((total + 1))
        model_path="$GGUF_DIR/$model_name.gguf"
        if [[ -f "$model_path" ]]; then
            print_success "GGUF model verified: $model_name"
            verified=$((verified + 1))
        else
            print_info "GGUF model not found: $model_name"
        fi
    done
    
    print_info "Verified $verified/$total models"
}

show_usage() {
    echo "Usage: $0 [OPTIONS] [MODELS...]"
    echo
    echo "Options:"
    echo "  --with-mlx        Install MLX packages"
    echo "  --with-llamacpp   Install llama-cpp-python packages"
    echo "  --all-models      Download all available models"
    echo "  --help           Show this help message"
    echo
    echo "Available models:"
    echo "  MLX models:"
    for model in "${!MLX_MODELS[@]}"; do
        echo "    - $model"
    done
    echo "  GGUF models:"
    for model in "${!GGUF_MODELS[@]}"; do
        echo "    - $model"
    done
    echo
    echo "Examples:"
    echo "  $0 --with-mlx --with-llamacpp --all-models"
    echo "  $0 llama-3.2-1b-instruct phi3-mini"
    echo "  $0 --with-mlx llama-3.2-1b-instruct"
}

main() {
    print_header
    
    # Parse arguments
    local install_mlx=false
    local install_llamacpp=false
    local download_all=false
    local models=()
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --with-mlx)
                install_mlx=true
                shift
                ;;
            --with-llamacpp)
                install_llamacpp=true
                shift
                ;;
            --all-models)
                download_all=true
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                models+=("$1")
                shift
                ;;
        esac
    done
    
    # If no models specified and not --all-models, show usage
    if [[ ${#models[@]} -eq 0 && "$download_all" != true ]]; then
        show_usage
        exit 0
    fi
    
    # Run setup steps
    check_dependencies
    create_directories
    
    # Install packages if requested
    local install_args=""
    if [[ "$install_mlx" == true ]]; then
        install_args="--with-mlx"
    fi
    if [[ "$install_llamacpp" == true ]]; then
        install_args="$install_args --with-llamacpp"
    fi
    
    if [[ -n "$install_args" ]]; then
        install_packages $install_args
    fi
    
    # Download models
    if [[ "$download_all" == true ]]; then
        print_step "Downloading all available models..."
        
        # Download all MLX models
        for model_name in "${!MLX_MODELS[@]}"; do
            download_mlx_model "$model_name"
        done
        
        # Download all GGUF models
        for model_name in "${!GGUF_MODELS[@]}"; do
            download_gguf_model "$model_name"
        done
    else
        # Download specified models
        for model in "${models[@]}"; do
            if [[ -n "${MLX_MODELS[$model]}" ]]; then
                download_mlx_model "$model"
            elif [[ -n "${GGUF_MODELS[$model]}" ]]; then
                download_gguf_model "$model"
            else
                print_error "Unknown model: $model"
            fi
        done
    fi
    
    # Show LM Studio instructions
    setup_lmstudio_instructions
    
    # Verify models
    verify_models
    
    print_success "Model setup completed!"
    echo
    print_info "Next steps:"
    echo "1. Set environment variables in your .env file:"
    echo "   MLX_ENABLED=true"
    echo "   LLAMACPP_ENABLED=true"
    echo "   LMSTUDIO_ENABLED=true"
    echo "2. Run the benchmark script:"
    echo "   python scripts/benchmark_llm_providers.py"
    echo "3. Test individual providers in the web UI settings"
}

# Run main function
main "$@"
