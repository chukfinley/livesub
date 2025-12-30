# livesub

Real-time transcription overlay for Linux desktop audio.

## Modes

- **Groq API** (default) - Fast, cloud-based, requires API key
- **Local** - Offline, uses faster-whisper, no API key needed

## Requirements

- Linux with PulseAudio/PipeWire
- Python 3.13+
- [uv](https://github.com/astral-sh/uv)

## Installation

```bash
git clone https://github.com/chukfinley/livesub.git
cd livesub
uv sync
```

For Groq API mode, create `.env`:
```bash
echo "GROQ=your_api_key_here" > .env
```

## Usage

```bash
# Groq API (fast, cloud)
./livesub

# Local Whisper (offline)
./livesub --local

# Local with larger model (better accuracy)
./livesub --local --model medium
```

### Model sizes (--local)

| Model | Size | Speed |
|-------|------|-------|
| tiny | 75 MB | Fastest |
| base | 150 MB | Fast |
| small | 500 MB | Medium |
| medium | 1.5 GB | Slow |
| large | 3 GB | Slowest |

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
