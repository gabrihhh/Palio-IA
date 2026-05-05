# Contexto Técnico

## Hardware

**Radxa ROCK 4B**
- CPU: RK3399 — Cortex-A72 dual-core 1.8GHz + Cortex-A53 quad-core 1.4GHz
- RAM: 4GB LPDDR4 | Armazenamento: SD card 32GB
- SO: Debian 12 Bookworm ARM64 (CLI, sem desktop) — imagem oficial Radxa
- Conectividade: WiFi 802.11ac, Bluetooth 5.0, USB 3.0
- Compatível com qualquer ARM64 rodando Debian 12 Bookworm

**Microfone**: USB recomendado (melhor isolamento de ruído). Auto-selecionado por proximidade com 16kHz.
Seleção manual via `AUDIO_DEVICE=N`. Listar dispositivos:
```bash
venv/bin/python3 -c "import pyaudio; p=pyaudio.PyAudio(); [print(f'[{i}]', p.get_device_info_by_index(i)['name']) for i in range(p.get_device_count()) if p.get_device_info_by_index(i)['maxInputChannels']>0]; p.terminate()" 2>/dev/null
```

## Arquitetura de Áudio

```
[Mic USB] → PyAudio → resample_poly → Whisper → texto
                                                         ↓
                                               dispatcher de intenção
                                              /          |          \
                                         Música      Pareamento    LLM
                                         AVRCP       bluetoothctl  Ollama
                                              \          |         /
                                               piper-tts ONNX (TTS)
                                                         ↓
                                              sounddevice → PipeWire → sink P2 → [Rádio]

[Celular] → A2DP BT sink → PipeWire → loopback → saída analógica P2 → [Rádio do Palio]
```

TTS e música do celular são misturados pelo PipeWire antes de sair pelo cabo P2.
O rádio do Palio **não** é pareado via Bluetooth — recebe áudio pelo cabo AUX.

## Stack

### STT — faster-whisper

| Modelo | Precisão PT-BR | Latência (Rock Pi 4B) | CHUNK |
|---|---|---|---|
| `small` (padrão, ~460MB, auto-download) | Alta | ~2-4s | 1024 |
| `medium` (~1.5GB) | Muito alta | ~5-8s | 1024 |
| `large-v3` (~3GB) | Máxima | ~15-25s | 1024 |

Selecionar via `WHISPER_MODEL=medium` (ou `large-v3`).

**Dois estágios + filtros**: arquitetura dois estágios (wake word separada do comando), filtro bandpass 300-3400Hz para VAD, pré-ênfase (coef=0.97) antes do modelo, `initial_prompt` com vocabulário do sistema. Ver `ai_docs/features.md` para detalhes.

### Bibliotecas Python

| Lib | Versão | Propósito |
|---|---|---|
| `faster-whisper` | latest | STT padrão — transformer offline |
| `pyaudio` | 0.2.14 | Captura de microfone em tempo real |
| `numpy` | 2.1.1 | Manipulação de arrays de áudio |
| `scipy` | 1.15.1 | `resample_poly` — resampling 48kHz→16kHz (ratio 3:1 limpo, sem artefatos) |
| `piper-tts` | latest | TTS neural offline — modelo ONNX PT-BR (`pt_BR-cadu-medium`) |
| `onnxruntime` | latest | Runtime ONNX para inferência do modelo piper |
| `sounddevice` | 0.5.0 | Reprodução de arquivo WAV |
| `soundfile` | 0.13.1 | Leitura de arquivo WAV |
| `requests` | 2.32.3 | API REST do Ollama |
| `dbus-python` | via apt | Controle AVRCP via bluez (Linux somente) |

### Stack de áudio do sistema

| Componente | Papel |
|---|---|
| PipeWire | Mixing e roteamento de áudio |
| WirePlumber | Conecta dispositivos BT ao PipeWire automaticamente |
| libspa-0.2-bluetooth | Suporte A2DP no PipeWire |
| pactl | Controle de volume de sinks (usado pelo AudioDuck) |

### LLM

- **Modelo padrão**: `llama3.2:3b` (~2GB, ~1-3 tokens/s no RK3399 CPU-only)
- **API**: `POST http://127.0.0.1:11434/api/chat`
- **Fallback**: Se Ollama offline → TTS "Meu cérebro tá offline agora." Música e pareamento continuam.
- **Instalação**: `curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.2:3b`

### Bluetooth

- **A2DP**: recebe stream de áudio do celular (Rock Pi age como sink/destino)
- **AVRCP**: controla player do celular (next, prev, pause, play, metadata)
- **Pareamento**: Rock Pi fica visível por 60s → celular inicia a conexão → Rock Pi detecta e salva em `data/devices.json` (apenas 1 device)
- **Boot**: tenta auto-connect silencioso ao dispositivo salvo; se falhar, aguarda `"carro conectar"`
- **Requer**: `python3-dbus` via apt; venv criado com `--system-site-packages`

## Setup Completo

```bash
# Dependências do sistema (Debian 12 ARM64)
sudo apt install python3-dbus bluez bluez-utils portaudio19-dev \
                 pipewire wireplumber libspa-0.2-bluetooth

# Python
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r req.txt

# Ativar git hooks (uma vez por clone)
git config core.hooksPath .githooks

# Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
```

## Resiliência e Falhas

| Componente | Falha | Comportamento |
|---|---|---|
| Microfone | Nenhum dispositivo encontrado | `exit(1)` |
| Stream de áudio | Erro ao abrir | `exit(1)` |
| Buffer overflow | Chunk descartado | `exception_on_overflow=False` — silencioso |
| Ollama offline | Indisponível | TTS "Meu cérebro tá offline." Outros módulos continuam |
| Bluetooth | Não conectado | TTS "Não tem nenhum celular conectado." |
| dbus-python | ImportError | Log de erro + BT indisponível; sistema continua sem BT |
