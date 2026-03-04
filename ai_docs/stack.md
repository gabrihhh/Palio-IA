# Stack Tecnológica

## Linguagens e Runtime

| Tecnologia | Versão     | Papel                          |
|------------|------------|-------------------------------|
| Python     | 3.x        | Linguagem principal do projeto |

## Hardware Alvo

- **Dispositivo**: Rock Pi 4B (RK3399, ARM64 — Cortex-A72 quad-core 1.8GHz + Cortex-A53 quad-core)
- **SO**: Armbian 26.2.1 Minimal/IOT (Debian Bookworm, sem desktop)
- **Ambiente de produção**: Embarcado dentro do carro (Fiat Palio)
- **Ambiente de desenvolvimento**: Windows (PC do desenvolvedor)
- **Chip Bluetooth**: AP6256 — suporta múltiplas conexões simultâneas

## Bibliotecas Principais

### Reconhecimento de Voz (STT)

| Biblioteca   | Versão  | Propósito                                                  |
|--------------|---------|------------------------------------------------------------|
| `vosk`       | 0.3.45  | Motor de reconhecimento de fala offline (modelo PT-BR)    |
| `pyaudio`    | 0.2.14  | Captura de áudio do microfone em tempo real               |
| `numpy`      | 2.1.1   | Manipulação de arrays de áudio (conversão de bytes)       |
| `scipy`      | 1.15.1  | Resampling de áudio (resample para 16kHz)                 |

### Síntese de Voz (TTS)

| Biblioteca   | Versão  | Propósito                                                  |
|--------------|---------|------------------------------------------------------------|
| `pyttsx3`    | 2.98    | Motor de síntese de fala offline (text-to-speech)         |
| `sounddevice`| 0.5.0   | Reprodução do arquivo WAV gerado (cross-platform)         |
| `soundfile`  | 0.13.1  | Leitura de arquivos WAV (cross-platform)                  |

> `winsound` foi removido — substituído por `sounddevice` + `soundfile` para compatibilidade com Linux/ARM.

### LLM

| Biblioteca   | Versão  | Propósito                                                  |
|--------------|---------|------------------------------------------------------------|
| `requests`   | 2.32.3  | Requisições HTTP para a API REST do Ollama                |

### Bluetooth

| Biblioteca   | Versão  | Propósito                                                  |
|--------------|---------|------------------------------------------------------------|
| `dbus-python` | (via apt) | Controle AVRCP via bluez DBus (Linux somente)           |

> Instalado via `apt install python3-dbus`. O venv é criado com `--system-site-packages` para ter acesso.

### Utilitários de Desenvolvimento (Windows)

| Biblioteca    | Versão  | Propósito                            |
|---------------|---------|--------------------------------------|
| `colorama`    | 0.4.6   | Saída colorida no terminal Windows   |

## Modelo de Voz

- **Engine**: Vosk com modelo `vosk-model-small-pt-0.3`
- **Localização esperada**: `./model-ptbr/` na raiz do projeto
- **Tamanho**: ~31 MB (modelo small)
- **Frequência de amostragem requerida**: 16.000 Hz
- **Download automático**: feito pelo `setup.sh`
- **Gitignore**: `model-ptbr/` está no `.gitignore`

## Modelo LLM

- **Engine**: Ollama com modelo `llama3.2:3b`
- **Performance esperada**: ~1-3 tokens/segundo no RK3399 (CPU-only)
- **Instalação automática**: feita pelo `setup.sh`
- **API**: REST local em `http://127.0.0.1:11434`

## Stack de Áudio

| Componente         | Tecnologia              | Papel                                           |
|--------------------|-------------------------|-------------------------------------------------|
| Servidor de áudio  | PipeWire                | Mixing e roteamento de áudio                    |
| Gerenciamento BT   | WirePlumber             | Conecta automaticamente dispositivos BT ao PipeWire |
| Plugin Bluetooth   | libspa-0.2-bluetooth    | Suporte A2DP no PipeWire                        |
| Controle de volume | pactl                   | CLI para ajustar sinks/sources                  |
| TTS engine         | espeak-ng               | Backend do pyttsx3 no Linux                     |

## Ferramentas de Desenvolvimento

- **Gerenciador de dependências**: `pip` com `req.txt`
- **Ambiente virtual**: `venv/` criado com `--system-site-packages` (necessário para `python3-dbus`)
- **Controle de versão**: Git
- **Editor configurado**: OpenCode (`.opencode/`)

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
│  │  PyAudio         │    │                                  │  │
│  │  Resample        │───▶│  dispatcher.py                   │  │
│  │  Vosk PT-BR      │    │    ├── música → music.py (AVRCP) │  │
│  │  Wake word       │    │    └── conversa → client.py LLM  │  │
│  └──────────────────┘    └──────────────────────────────────┘  │
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
- Backend `espeak-ng` no Linux, SAPI5 no Windows (desenvolvimento)

### Por que sounddevice + soundfile e não winsound?
- `winsound` é Windows-only; `sounddevice` + `soundfile` são cross-platform
- Permite desenvolver e testar no Windows e rodar no Linux sem mudança de código

### Por que asyncio foi removido?
- pyttsx3 e sounddevice são síncronos por natureza
- O fluxo principal (wake word → STT → dispatcher → TTS) é naturalmente sequencial
- Adição futura de concorrência pode usar threads se necessário

### Por que PipeWire e não PulseAudio?
- PipeWire é o padrão moderno no Debian Bookworm
- Suporte nativo a múltiplos perfis Bluetooth simultâneos (sink + source)
- WirePlumber gerencia conexões automaticamente

### Por que Ollama e não rodar o modelo direto?
- Ollama gerencia o ciclo de vida do modelo (carregamento, offload)
- API REST simples; fácil de trocar o modelo no futuro
- Mantém o modelo em memória entre chamadas (latência menor)
