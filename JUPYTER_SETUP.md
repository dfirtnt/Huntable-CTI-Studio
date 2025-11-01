# Jupyter Notebook Setup for LMStudio Model Comparison

## Quick Fix for "No Pip Installer" Error

The notebook requires Jupyter and dependencies. They're installed in the `venv-test` virtual environment.

### Option 1: Use VS Code with venv-test

1. **Select Python Interpreter:**
   - Press `Cmd+Shift+P` (or `Ctrl+Shift+P`)
   - Type: `Python: Select Interpreter`
   - Choose: `./venv-test/bin/python` or the path to `venv-test`

2. **Verify:**
   - The interpreter path should show `venv-test` in the status bar
   - VS Code should recognize pip in that environment

### Option 2: Launch Jupyter from Terminal

```bash
cd /Users/starlord/CTIScraper
source venv-test/bin/activate
jupyter notebook lmstudio_model_comparison.ipynb
```

### Option 3: Use Jupyter Kernel (Already Configured)

The `ctiscraper` kernel is installed. In VS Code:
1. Open the notebook
2. Click the kernel selector (top right)
3. Select: **"Python 3 (CTIScraper)"**

## Dependencies Installed

- ✅ Jupyter
- ✅ IPython
- ✅ httpx (for LMStudio API)
- ✅ pandas (for CSV export)
- ✅ ipykernel

## Troubleshooting

**Still seeing "No Pip Installer"?**
- Make sure VS Code is using the `venv-test` interpreter
- Restart VS Code after selecting the interpreter
- Check VS Code Output panel for Python extension errors

**Kernel not found?**
- Reinstall: `source venv-test/bin/activate && python -m ipykernel install --user --name=ctiscraper`

