# Palio-IA

Assistente de voz embarcado para um **Fiat Palio**, rodando em uma **Radxa Rock Pi 4B** (ARM64). Controle o carro por voz — música, Bluetooth e conversas — tudo **100% offline**, sem internet.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.x |
| Hardware | Radxa Rock Pi 4B — RK3399, ARM64 |
| SO | Debian 12 Bookworm (CLI, sem desktop) |
| STT | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (modelo `small`, PT-BR) |
| TTS (texto → fala) | [piper-tts](https://github.com/OHF-Voice/piper1-gpl) + modelo `pt_BR-faber-medium` |
| LLM | [Ollama](https://ollama.com/) com llama3.2:3b (local) |
| Áudio — captura | PyAudio |
| Áudio — reprodução | sounddevice + soundfile |
| Áudio — servidor | PipeWire + WirePlumber |
| Áudio — controle | pactl |
| Bluetooth — controle | bluez + bluetoothctl |
| Bluetooth — música | dbus-python (AVRCP via bluez DBus) |
| Resampling | scipy.signal.resample_poly |

---

## Comandos de voz

Todos os comandos começam com a wake word **"carro"**.

### Música
| Comando | Ação |
|---|---|
| carro próxima / passa / skip | Próxima faixa |
| carro volta / anterior | Faixa anterior |
| carro pausa / para / pare / parar | Pausar |
| carro toca / play / continua | Retomar |
| carro que música é essa | Nome e artista da faixa atual |

### Volume
| Comando | Ação |
|---|---|
| carro aumenta o volume | +10% |
| carro diminui o volume | -10% |
| carro volume [um a dez] | Define volume direto (ex: "volume cinco" → 50%) |

### Bluetooth
| Comando | Ação |
|---|---|
| carro modo de pareamento | Rock Pi fica visível por 60s para o celular conectar |
| carro conectar | Conecta ao último celular salvo |

### Conversa
Qualquer outro comando após "carro" é enviado ao LLM (Ollama). O assistente responde com a persona do próprio carro Palio — direto, informal, humor seco. O Palio aprende o nome do dono e preferências ao longo do tempo via `data/brain.md`.

---

## Requisitos de hardware

- **Radxa Rock Pi 4B** (ou equivalente ARM64 com Debian 12)
- **Microfone USB** — recomendado para isolamento de ruído
- **Cabo P2 (3.5mm)** — conectado da saída de áudio do Rock Pi à entrada AUX do rádio
- **Rádio com entrada AUX** — Fiat Palio com entrada P2

---

## Instalação

### 1. Dependências do sistema

```bash
sudo apt install python3-dbus bluez bluez-utils portaudio19-dev \
                 pipewire wireplumber libspa-0.2-bluetooth
```

### 2. Ambiente Python

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r req.txt
```

> O `--system-site-packages` é obrigatório para acessar o `python3-dbus` instalado via apt.

### 3. piper-tts (TTS offline)

Os wheels ARM64 e o modelo de voz já estão incluídos no projeto (pastas `wheels/` e `models/`):

```bash
pip install --no-index --find-links=wheels/ piper-tts
```

### 4. Modelo Whisper

O modelo `small` (~460MB) é baixado automaticamente na primeira execução pelo `faster-whisper`.

### 5. Ollama (LLM local)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
ollama serve
```

> O sistema funciona sem Ollama — música e Bluetooth continuam operando normalmente.

---

## Como rodar

```bash
venv/bin/python3 main.py
```

### Com debug (mostra tudo que o STT reconhece)

```bash
venv/bin/python3 main.py --debug
```

O sistema toca dois bipes ao iniciar e fica aguardando a wake word **"carro"**.

### Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `AUDIO_DEVICE` | auto | Índice do microfone (listar: `python3 -c "import pyaudio; p=pyaudio.PyAudio(); [print(i, p.get_device_info_by_index(i)['name']) for i in range(p.get_device_count()) if p.get_device_info_by_index(i)['maxInputChannels']>0]"`) |
| `WHISPER_MODEL` | `small` | Modelo Whisper: `small`, `medium`, `large-v3` |
| `WHISPER_SILENCE_THRESHOLD` | `400` | Limiar de amplitude para detectar silêncio |
| `WHISPER_SILENCE_DURATION` | `0.8` | Segundos de silêncio para encerrar utterance |
| `PIPER_MODEL` | `models/pt_BR-faber-medium.onnx` | Caminho para o modelo piper (relativo ao `main.py`) |

---

## Versão atual

**v0.5.0**
