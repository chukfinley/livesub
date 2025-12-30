# livesub

Real-time transcription overlay for Linux desktop audio using Groq Whisper API.

## Features

- Transcribes system audio (movies, YouTube, calls, etc.)
- Overlay window stays on top
- Two-line display with smart text fading
- Transcript history saved to file
- Filters common Whisper hallucinations

## Requirements

- Linux with PulseAudio/PipeWire
- Python 3.13+
- [uv](https://github.com/astral-sh/uv)
- Groq API key

## Installation

```bash
git clone https://github.com/chukfinley/livesub.git
cd livesub
uv sync
echo "GROQ=your_api_key_here" > .env
```

## Usage

```bash
./livesub
```

### Add to PATH

```bash
sudo ln -s $(pwd)/livesub /usr/local/bin/livesub
```

## Controls

- **ESC** - Quit
- **C** - Clear display
- **Drag** - Move window

## License

MIT
