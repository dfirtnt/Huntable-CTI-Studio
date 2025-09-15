# SousChef - LLM-Enhanced CyberChef

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Node.js Version](https://img.shields.io/badge/node-%3E%3D18.0.0-brightgreen.svg)](https://nodejs.org/)
[![CyberChef Fork](https://img.shields.io/badge/CyberChef-Fork-blue.svg)](https://github.com/gchq/CyberChef)

SousChef is a fork of the original [CyberChef](https://github.com/gchq/CyberChef) with integrated LLM capabilities, enabling natural language processing for cryptographic operations and data analysis.

## 🚀 Features

### Core CyberChef Capabilities
- **300+ Operations**: Complete suite of encoding, encryption, compression, and analysis tools
- **Web Interface**: Full-featured React-based UI with drag-and-drop recipe building
- **Node.js API**: Programmatic access to all operations
- **Batch Processing**: Handle multiple files and data streams
- **Recipe Sharing**: Save and load processing workflows

### LLM Enhancements
- **Natural Language Processing**: Convert prompts like "Decode base64 then redact 'secret'" into valid recipes
- **Intelligent Recipe Generation**: GPT-4 powered recipe creation from natural language descriptions
- **Recipe Explanation**: Understand what each recipe does in plain English
- **Error Correction**: Automatic recipe fixing and validation
- **CLI Interface**: Command-line tool for automation and scripting

## 📦 Installation

### Prerequisites
- Node.js 18.0.0 or higher
- OpenAI API key

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/dfirtnt/SousChef.git
   cd SousChef
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

4. **Start the web interface**
   ```bash
   npm run dev
   ```
   Open http://localhost:13337/CyberChef_v10.19.4.html

## 🛠️ Usage

### Web Interface
The full CyberChef web interface is available with all original features plus LLM enhancements:

- **Operations Panel**: Browse 300+ operations by category
- **Recipe Building**: Drag-and-drop operations to create processing chains
- **Natural Language Input**: Describe what you want to do in plain English
- **Auto-Bake**: Real-time processing with automatic execution

### CLI Usage

```bash
# Generate a recipe from natural language
npm run cli -- generate "Decode base64 then extract IP addresses"

# Execute a recipe
npm run cli -- execute recipe.json input.txt

# Batch process files
npm run cli -- batch recipe.json ./input-files/

# Interactive mode
npm run cli -- interactive
```

### API Usage

```javascript
import { SousChef } from './src/souschef/index.js';

const chef = new SousChef(process.env.OPENAI_API_KEY);

// Generate and execute in one call
const { recipe, result } = await chef.generateAndExecute(
  "Decode base64 then extract IP addresses",
  "SGVsbG8gV29ybGQ="
);

console.log('Recipe:', recipe);
console.log('Result:', result.output);
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for LLM features | Required |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4` |
| `OPENAI_TEMPERATURE` | Temperature for recipe generation | `0.1` |
| `OPENAI_MAX_TOKENS` | Maximum tokens per response | `2000` |
| `LOG_LEVEL` | Logging level | `info` |
| `PORT` | Web server port | `13337` |

### Recipe Schema

```json
{
  "steps": [
    {
      "op": "OperationNameExactlyAsInCyberChef",
      "args": [/* ordered args per op */]
    }
  ],
  "notes": "optional free text"
}
```

## 🏗️ Architecture

### Project Structure
```
SousChef/
├── src/
│   ├── core/           # Original CyberChef core
│   ├── web/            # React web interface
│   ├── node/           # Node.js API
│   └── souschef/       # LLM enhancements
│       ├── index.js    # Main SousChef class
│       ├── generator.js # Recipe generation
│       ├── orchestrator.js # Execution engine
│       ├── validation.js # Schema validation
│       └── cli.js      # Command-line interface
├── tests/              # Test suite
├── build/              # Pre-built web assets
└── docs/               # Documentation
```

### Key Components

- **SousChef**: Main orchestrator class combining LLM and CyberChef capabilities
- **RecipeGenerator**: GPT-4 powered natural language to recipe conversion
- **CyberChefOrchestrator**: Lightweight execution engine for recipes
- **Validation**: Schema validation and operation allowlist management

## 🧪 Testing

```bash
# Run all tests
npm test

# Run specific test suites
npm run test:unit
npm run test:integration
npm run test:e2e

# Test LLM features (requires API key)
npm run test:llm
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

### Code Standards

- Follow existing code style and patterns
- Add comprehensive tests for new features
- Update documentation for API changes
- Ensure all tests pass before submitting

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **GCHQ**: Original CyberChef creators and maintainers
- **OpenAI**: GPT-4 API for natural language processing
- **Contributors**: All community contributors and maintainers

## 🔗 Links

- [Original CyberChef](https://github.com/gchq/CyberChef)
- [CyberChef Web App](https://gchq.github.io/CyberChef/)
- [OpenAI API](https://platform.openai.com/)
- [Documentation](docs/)

## 📊 Status

- ✅ **Core CyberChef**: Fully functional with 300+ operations
- ✅ **LLM Integration**: Natural language recipe generation
- ✅ **Web Interface**: Complete React-based UI
- ✅ **CLI Tools**: Command-line automation
- ✅ **API**: Programmatic access
- 🚧 **Advanced Features**: Recipe variations, error correction
- 🚧 **Performance**: Optimization and caching

---

**SousChef** - The LLM-Enhanced Cyber Swiss Army Knife 🍳