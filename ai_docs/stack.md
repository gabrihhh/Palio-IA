# Stack Tecnológica

## Linguagens e Runtime

| Tecnologia | Versão | Papel |
|---|---|---|
| Python | 3.x | Linguagem principal do projeto |

## Hardware Alvo

- **Dispositivo**: Radxa ROCK 4B (RK3399, Cortex-A72 dual-core 1.8GHz + Cortex-A53 quad-core)
- **SO**: Debian 12 Bookworm ARM64 (CLI, sem desktop)
- **Imagem**: Radxa ROCK 4B Debian 12 Bookworm (oficial Radxa)
- **Armazenamento**: SD card 32GB
- **Ambiente de produção**: Embarcado dentro do carro (Fiat Palio)
- **Compatibilidade**: Qualquer placa ARM64 rodando Debian 12 Bookworm

## Bibliotecas Principais

### Reconhecimento de Voz (STT)

| Biblioteca | Versão | Propósito |
|---|---|---|
| `vosk` | 0.3.45 | Motor de reconhecimento de fala offline (modelo PT-BR) |
| `pyaudio` | 0.2.14 | Captura de áudio do microfone em tempo real |
| `numpy` | 2.1.1 | Manipulação de arrays de áudio (conversão de bytes) |
| `scipy` | 1.15.1 | Resampling de áudio (resample para 16kHz) |

### Síntese de Voz (TTS)

| Biblioteca | Versão | Propósito |
|---|---|---|
| `pyttsx3` | 2.98 | Motor de síntese de fala offline (text-to-speech) |
| `sounddevice` | 0.5.0 | Reprodução do arquivo WAV gerado |
| `soundfile` | 0.13.1 | Leitura de arquivos WAV |

### LLM

| Biblioteca | Versão | Propósito |
|---|---|---|
| `requests` | 2.32.3 | Requisições HTTP para a API REST do Ollama |

### Bluetooth

| Biblioteca | Versão | Propósito |
|---|---|---|
| `dbus-python` | (via apt) | Controle AVRCP via bluez DBus (Linux somente) |

> Instalado via `apt install python3-dbus`. O venv é criado com `--system-site-packages` para ter acesso.

## Modelo de Voz

- **Engine**: Vosk com modelo `vosk-model-small-pt-0.3`
- **Localização esperada**: `./model-ptbr/` na raiz do projeto
- **Tamanho**: ~30 MB
- **Frequência de amostragem requerida**: 16.000 Hz
- **Gitignore**: `model-ptbr/` está no `.gitignore` — deve ser baixado manualmente

## Modelo LLM

- **Engine**: Ollama com modelo `llama3.2:3b`
- **Performance esperada**: ~1-3 tokens/segundo no RK3399 (CPU-only)
- **API**: REST local em `http://127.0.0.1:11434`
- **Instalação**: `curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.2:3b`

## Stack de Áudio

| Componente | Tecnologia | Papel |
|---|---|---|
| Servidor de áudio | PipeWire | Mixing e roteamento de áudio |
| Gerenciamento BT | WirePlumber | Conecta dispositivos BT ao PipeWire automaticamente |
| Plugin Bluetooth | libspa-0.2-bluetooth | Suporte A2DP no PipeWire |
| Controle de volume | pactl | CLI para ajustar sinks/sources (usado pelo AudioDuck) |
| TTS engine | espeak-ng | Backend do pyttsx3 no Linux |

## Ferramentas de Desenvolvimento

- **Gerenciador de dependências**: `pip` com `req.txt`
- **Ambiente virtual**: `venv/` criado com `--system-site-packages` (necessário para `python3-dbus`)
- **Controle de versão**: Git

## Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                          Palio-IA                               │
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────────────────────┐  │
│  │ speech_to_text   │    │            main.py               │  │
│  │      .py         │    │                                  │  │
│  │                  │    │  TTS (pyttsx3 + espeak-ng)       │  │
│  │  Microfone       │    │  Reprodução (sounddevice)        │  │
│  │  PyAudio         │    │  AudioDuck (pactl/PipeWire)      │  │
│  │  Resample        │───▶│                                  │  │
│  │  Vosk PT-BR      │    │  dispatcher.py                   │  │
│  │  Wake word       │    │    ├── música → music.py (AVRCP) │  │
│  └──────────────────┘    │    ├── parear → pairing.py       │  │
│                          │    └── conversa → client.py LLM  │  │
│                          └──────────────────────────────────┘  │
│                                                                 │
│  Fluxo de áudio:                                                │
│  [Celular] → A2DP sink → PipeWire → loopback → A2DP source → [Rádio] │
└─────────────────────────────────────────────────────────────────┘
```

## Decisões Arquiteturais

### Por que Vosk e não Whisper?
- Vosk tem modelo PT-BR e roda em ARM com latência baixa
- Whisper é pesado demais para o RK3399 em tempo real

### Por que pyttsx3 e não gTTS?
- `gTTS` requer internet; `pyttsx3` funciona offline
- Princípio fundamental do projeto: 100% offline

### Por que sounddevice + soundfile?
- Cross-platform e funcional no Linux/ARM64
- `winsound` foi removido na v0.0.8 por ser Windows-only

### Por que asyncio foi removido?
- pyttsx3 e sounddevice são síncronos por natureza
- O fluxo principal é sequencial (wake word → STT → dispatcher → TTS)

### Por que PipeWire e não PulseAudio?
- Padrão moderno no Ubuntu 22.04+
- Suporte nativo a múltiplos perfis Bluetooth simultâneos (sink + source)
- WirePlumber gerencia conexões automaticamente

### Por que Ollama e não rodar o modelo direto?
- Ollama gerencia o ciclo de vida do modelo (carregamento, offload)
- API REST simples; fácil de trocar o modelo no futuro
- Mantém o modelo em memória entre chamadas (latência menor)
