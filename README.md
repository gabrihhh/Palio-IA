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
| TTS (texto → fala) | [piper-tts](https://github.com/OHF-Voice/piper1-gpl) + modelo `pt_BR-cadu-medium` |
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

A instalação é feita **100% offline na placa**. Tudo é preparado no PC (com internet) e transferido via pendrive (≥ 8 GB).

---

### Fase 1 — Preparar no PC (com internet)

#### 1.1 Clonar o repositório

```bash
git clone <url-do-repo> Palio-IA
cd Palio-IA
```

> `wheels/` e `models/` já estão no repo com tudo necessário para pip e piper-tts.

---

#### 1.2 Baixar o modelo Whisper small (~460 MB)

```bash
pip3 install huggingface_hub -q

python3 -m huggingface_hub download \
    Systran/faster-whisper-small \
    --local-dir Palio-IA/pendrive/whisper-small \
    --ignore-patterns "*.msgpack" "*.h5" "flax_model*" "tf_model*"
```

Resultado — pasta `Palio-IA/pendrive/whisper-small/` deve conter:
```
model.bin          ← ~460 MB (modelo principal)
config.json
tokenizer.json
vocabulary.json
preprocessor_config.json
```

---

#### 1.3 Baixar o binário Ollama ARM64

1. Acesse: `https://github.com/ollama/ollama/releases`
2. Baixe o arquivo `ollama-linux-arm64.tar.zst` da versão mais recente
3. Extraia e copie o binário:

```bash
# Extrair (o binário fica em bin/ollama dentro do tar)
tar --use-compress-program=zstd -xf ollama-linux-arm64.tar.zst

# Copiar para a pasta do pendrive com o nome correto
mkdir -p Palio-IA/pendrive/ollama
cp bin/ollama Palio-IA/pendrive/ollama/ollama
chmod +x Palio-IA/pendrive/ollama/ollama
```

> Para ver o conteúdo do tar antes de extrair:
> `tar --use-compress-program=zstd -tf ollama-linux-arm64.tar.zst | head`

---

#### 1.4 Baixar o modelo llama3.2:3b (~2 GB)

Requer Ollama instalado no PC. Se não tiver:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Fazer pull e copiar os arquivos do modelo:

```bash
ollama pull llama3.2:3b

# Copiar para a pasta do pendrive
# ~/.ollama/models/ contém subpastas manifests/ e blobs/ (o modelo em si)
cp -r ~/.ollama/models Palio-IA/pendrive/ollama/models
```

---

#### 1.5 Estrutura do pendrive antes de copiar

```
Palio-IA/
├── main.py
├── req-offline.txt
├── setup.sh
├── models/
│   └── pt_BR-cadu-medium.onnx     ← modelo TTS (já no repo, ~63 MB)
├── wheels/                         ← todos os pacotes pip ARM64 (já no repo)
│   ├── piper_tts-*.whl
│   ├── faster_whisper-*.whl
│   ├── ctranslate2-*.whl
│   ├── scipy-*.whl
│   └── ...
└── pendrive/                       ← você preencheu nos passos 1.2–1.4
    ├── whisper-small/
    │   ├── model.bin               ← ~460 MB
    │   ├── config.json
    │   └── ...
    └── ollama/
        ├── ollama                  ← binário ARM64
        └── models/
            ├── manifests/          ← índice do modelo
            └── blobs/              ← arquivos sha256-* (~2 GB)
```

Copie a pasta `Palio-IA/` inteira para o pendrive.

---

### Fase 2 — Instalar na placa (offline)

#### 2.1 Montar o pendrive

```bash
lsblk                        # identificar o dispositivo (ex: /dev/sda1)
mkdir -p /mnt/usb
mount /dev/sda1 /mnt/usb     # ajustar conforme lsblk

cp -r /mnt/usb/Palio-IA /root/Palio-IA
cd /root/Palio-IA
```

---

#### 2.2 Instalar dependências do sistema

> A placa precisa de internet **uma única vez** para este passo.
> Após isso, nunca mais precisa de rede.

```bash
apt update
apt install -y \
    python3 python3-pip python3-dev python3-venv \
    python3-dbus python3-pyaudio \
    portaudio19-dev libportaudio2 libportaudiocpp0 libsndfile1 \
    bluez bluez-tools \
    pipewire pipewire-pulse pipewire-audio-client-libraries \
    wireplumber libspa-0.2-bluetooth \
    alsa-utils libasound2-dev
```

---

#### 2.3 Criar o ambiente Python e instalar pacotes (offline)

```bash
cd /root/Palio-IA

# --system-site-packages dá acesso ao python3-pyaudio instalado pelo apt
python3 -m venv --system-site-packages venv

# Instala tudo a partir dos wheels locais — sem internet
venv/bin/pip install --no-index --find-links=wheels/ -r req-offline.txt
```

---

#### 2.4 Instalar Ollama e o modelo

```bash
# Instalar binário
cp /root/Palio-IA/pendrive/ollama/ollama /usr/local/bin/ollama
chmod +x /usr/local/bin/ollama

# Instalar modelo (copia para onde o Ollama espera encontrar)
mkdir -p /root/.ollama
cp -r /root/Palio-IA/pendrive/ollama/models /root/.ollama/models

# Verificar
ollama list    # deve mostrar: llama3.2:3b
```

---

#### 2.5 Instalar o modelo Whisper

```bash
mkdir -p /root/.cache/huggingface/hub

cp -r /root/Palio-IA/pendrive/whisper-small \
    /root/.cache/huggingface/hub/models--Systran--faster-whisper-small
```

> O serviço já tem `HF_HUB_OFFLINE=1` — o faster-whisper não tentará
> verificar atualizações na internet no boot.

---

#### 2.6 Configurar serviços e áudio

```bash
cd /root/Palio-IA

# Ativa git hooks
git config core.hooksPath .githooks

# Configura Bluetooth, PipeWire e serviços systemd
bash setup.sh
```

---

#### 2.7 Testar antes do reboot

```bash
cd /root/Palio-IA

# Testar TTS (deve falar pelo alto-falante)
venv/bin/python test/tts.py "Olá, eu sou o Palio."

# Testar STT (falar e ver a transcrição — Ctrl+C para sair)
venv/bin/python test/stt.py

# Testar ciclo completo STT → LLM → TTS
systemctl start ollama
venv/bin/python test/chat.py
```

---

#### 2.8 Reboot

```bash
reboot
```

Após o boot: **dois bipes** = sistema inicializou. Dizer **"carro, olá"** para o primeiro teste.

```bash
# Acompanhar logs em tempo real
journalctl -u palio-ia.service -f
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
| `PIPER_MODEL` | `models/pt_BR-cadu-medium.onnx` | Caminho para o modelo piper (relativo ao `main.py`) |

---

## Versão atual

**v0.5.0**
