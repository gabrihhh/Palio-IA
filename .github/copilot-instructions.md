# Copilot Instructions — Palio-IA

## What This Repository Is

Palio-IA is a Python voice assistant for an embedded car computer (Rock Pi 4B / Linux ARM64). It does fully-offline speech recognition (Vosk PT-BR model) and text-to-speech (pyttsx3). Development happens on Windows; the deploy target is Linux/ARM. The project is at v0.0.7 and consists of exactly two source files today.

**Trust these instructions. Only search the codebase if something here is incomplete or seems wrong.**

---

## Repository Layout

```
Palio-IA/
├── main.py               # TTS module — async falar(res), asyncio.run(main()) at bottom
├── speech_to_text.py     # STT module — Vosk loop; ALL code runs at module level (no __main__ guard)
├── req.txt               # pip dependencies (note: NOT requirements.txt)
├── .gitignore            # ignores: venv/, model-ptbr/
├── ai_docs/              # Project documentation (architecture, gotchas, rules, integrations)
│   ├── index.md          # Overview and module status table
│   ├── stack.md          # Tech stack and architecture diagram
│   ├── features.md       # Implemented + planned features
│   ├── business-rules.md # 6 critical rules (16kHz, wake word, normalisation, etc.)
│   ├── gotchas.md        # Known bugs, pitfalls, Linux porting notes ← READ THIS FIRST
│   ├── patterns.md       # Design patterns and file structure conventions
│   └── integrations.md   # Hardware, Bluetooth, Ollama, pyttsx3/espeak details
└── venv/                 # Local virtualenv — NOT in git
```

**No CI/CD pipelines exist.** No `.github/workflows/`. No linting config (no `.flake8`, `pyproject.toml`, `setup.cfg`, etc.). No test framework is installed.

---

## Environment Setup (run once per clone)

**Runtime:** Python 3.12.x, Windows (dev) / Linux ARM64 (deploy).

```bash
# 1. Create virtualenv
python -m venv venv

# 2. Activate — use forward slashes in bash on Windows
venv/Scripts/pip install -r req.txt          # Windows
# source venv/bin/pip install -r req.txt     # Linux/Rock Pi

# 3. Verify imports (validated — all pass)
venv/Scripts/python -c "import pyttsx3, vosk, pyaudio, numpy, scipy; print('OK')"
```

- On **Windows**: PyAudio installs without extra steps (wheel bundles PortAudio).
- On **Linux/ARM**: `sudo apt install portaudio19-dev python3-dev espeak espeak-ng` before pip install.
- The **dependency file is `req.txt`**, not `requirements.txt`. Always use `-r req.txt`.

### Vosk model (required to run speech_to_text.py)

The `model-ptbr/` folder is in `.gitignore` and is **never in the repo**. Running `speech_to_text.py` without it calls `exit(1)` at line 29.

```bash
# Download from https://alphacephei.com/vosk/models
# Extract so that the path model-ptbr/ exists at the repo root:
# Palio-IA/model-ptbr/am/, model-ptbr/conf/, model-ptbr/graph/, ...
```

---

## Running the Modules

```bash
# TTS — speaks "Passando a música", generates+plays+deletes output.wav
venv/Scripts/python main.py

# STT — requires microphone AND model-ptbr/ to be present
venv/Scripts/python speech_to_text.py
```

**`speech_to_text.py` cannot be safely imported** — all initialisation (model load, PyAudio init, microphone detection, stream open, infinite while loop) runs at module level. To reuse its functions, extract them into a class or guard with `if __name__ == "__main__":`.

---

## Validation (no test framework — use these manual checks)

```bash
# Validate pure utility functions (no hardware, no model needed — always safe)
venv/Scripts/python -c "
import unicodedata
def remove_acentos(t):
    return ''.join(c for c in unicodedata.normalize('NFD',t) if unicodedata.category(c)!='Mn')
def verificar_palavra(f,p):
    return remove_acentos(p).lower() in remove_acentos(f).lower()
assert remove_acentos('próxima') == 'proxima'
assert verificar_palavra('carro proxima musica','próxima')
assert not verificar_palavra('carro voltar','próxima')
print('PASS')
"

# Validate TTS file generation (no audio device needed)
venv/Scripts/python -c "
import pyttsx3, os
e=pyttsx3.init(); e.setProperty('rate',160); e.setProperty('volume',1)
e.save_to_file('teste','_test.wav'); e.runAndWait()
assert os.path.exists('_test.wav') and os.path.getsize('_test.wav')>0
os.remove('_test.wav'); print('PASS')
"
```

---

## Known Bugs — Do Not Introduce New Ones Like These

| Location | Bug | Fix |
|---|---|---|
| `main.py:24` | `await winsound.PlaySound(...)` — `winsound` returns `None`, not a coroutine | Remove `await`, or use `asyncio.get_event_loop().run_in_executor(None, winsound.PlaySound, ...)` |
| Both files | No `if __name__ == "__main__":` guard — code runs on import | Wrap executable code in the guard |
| `main.py` | `winsound` is Windows-only stdlib; does not exist on Linux/Rock Pi 4B | Replace with `subprocess.run(['aplay','output.wav'])` or `pygame.mixer` for Linux |

---

## Key Conventions

- **Language**: All comments, `print()` messages, variable names, and user-facing strings are in **Brazilian Portuguese**.
- **Wake word pattern**: `"[wake_word] [command]"` — current wake word is `"carro"` (planned: `"Palio"`).
- **Audio constants**: `TARGET_RATE = 16000` Hz (Vosk requirement), `CHUNK = 4096` samples.
- **TTS settings**: `rate=160` wpm, `volume=1.0` — fixed in code.
- **String comparison**: always use `verificar_palavra()` for command matching — never compare raw strings with accents.
- **No linting config** — match existing code style (snake_case functions, UPPER_CASE constants).
- **req.txt** is the canonical dependency file — add new packages there, pinned to exact versions.
