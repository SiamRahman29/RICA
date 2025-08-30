# RICA - Rather Intelligent Conversational Assistant

RICA is an intelligent conversational assistant with speech-to-text and text-to-speech capabilities that manages AI agentic functions. It provides both voice and text interfaces for user interaction and can coordinate different AI agents for various tasks.

## Features

- 🎤 **Speech-to-Text**: Convert voice input to text using advanced speech recognition
- 🔊 **Text-to-Speech**: Natural-sounding speech synthesis for responses
- 🤖 **AI Agent Management**: Coordinate different AI agents for specialized tasks
- 🔄 **Multi-Modal Interface**: Support for both voice and text input/output
- ⚙️ **Extensible Architecture**: Easy to add new AI agents and capabilities
- 🌐 **API Server**: RESTful API for integration with other applications
- 🎯 **Smart Routing**: Automatically route requests to appropriate AI agents

## Architecture

```
RICA
├── Core Components
│   ├── Assistant Manager
│   ├── Agent Manager
│   └── Configuration
├── Audio Processing
│   ├── Speech-to-Text
│   └── Text-to-Speech
├── AI Agents
│   ├── OpenAI Agent
│   ├── Function Agent
│   └── Custom Agents
└── API Interface
    ├── REST Endpoints
    └── WebSocket Support
```

## Requirements

- Python 3.9+
- Poetry (for dependency management)
- Microphone and speakers/headphones
- OpenAI API key

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd RICA
   ```

2. **Install Poetry (if not already installed):**
   ```bash
   pip install poetry
   ```

3. **Install dependencies:**
   ```bash
   poetry install
   ```

4. **Set up environment variables:**
   ```bash
   cp env.example .env
   # Edit .env with your OpenAI API key and other settings
   ```

## Configuration

Create a `.env` file with the following variables:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4

# Audio Configuration
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
AUDIO_CHUNK_SIZE=1024

# Speech Recognition
SPEECH_RECOGNITION_TIMEOUT=5.0
SPEECH_PHRASE_TIME_LIMIT=10.0

# Text-to-Speech
TTS_VOICE_ID=
TTS_SPEED=1.0

# Server Configuration
HOST=127.0.0.1
PORT=8000
DEBUG=false

# Logging
LOG_LEVEL=INFO
LOG_FILE=
```

## Usage

### Command Line Interface

1. **Interactive Mode (Default):**
   ```bash
   poetry run rica
   ```

2. **Voice-Only Mode:**
   ```bash
   poetry run rica --voice
   ```

3. **Text-Only Mode:**
   ```bash
   poetry run rica --text
   ```

4. **Show System Status:**
   ```bash
   poetry run rica --status
   ```

5. **Test Audio System:**
   ```bash
   poetry run rica --test-audio
   ```

### CLI Commands

- `voice` - Switch to voice input mode
- `text` - Switch to text input mode
- `status` - Show system status
- `quit` - Exit the application

### Python API

```python
from rica import RICA
from rica.core.config import Config

# Load configuration
config = Config.load_from_env()

# Initialize assistant
assistant = RICA(config)

# Start the assistant
await assistant.start()

# Process voice input
text = await assistant.process_voice_input()

# Process text input
response = await assistant.process_text_input("Hello, RICA!")

# Speak response
await assistant.speak_response(response)

# Stop the assistant
await assistant.stop()
```

## Development


### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test file
poetry run pytest tests/test_assistant.py
```

### Code Quality

```bash
# Format code
poetry run black src/ tests/

# Sort imports
poetry run isort src/ tests/

# Lint code
poetry run flake8 src/ tests/

# Type checking
poetry run mypy src/
```

## Troubleshooting

### Audio Issues

1. **No microphone detected:**
   - Check microphone permissions
   - Verify audio device selection
   - Run `rica --test-audio` to diagnose

2. **Speech recognition not working:**
   - Ensure internet connection (for Google Speech Recognition)
   - Check microphone volume and clarity
   - Verify audio sample rate settings

3. **Text-to-speech issues:**
   - Check speaker/headphone connections
   - Verify TTS voice availability
   - Test with `rica --test-audio`

### OpenAI Issues

1. **API key errors:**
   - Verify OPENAI_API_KEY in .env file
   - Check API key validity and quota
   - Ensure proper model access

### General Issues

1. **Import errors:**
   - Ensure Poetry environment is activated
   - Run `poetry install` to install dependencies
   - Check Python version compatibility

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the configuration options
