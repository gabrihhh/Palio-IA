# Instalação Offline — Palio-IA no Radxa ROCK 4B

Tudo preparado no PC (com internet) e transferido para a placa via pendrive.
A placa nunca precisa de internet.

---

## Premissas

- PC com Ubuntu/Debian e internet disponível
- Radxa ROCK 4B com Debian 12 Bookworm ARM64 já instalado no SD/eMMC
- Pendrive ≥ 8 GB (Whisper ~460 MB + llama3.2 ~2 GB + repo + wheels)

---

## Fase 1 — Preparação no PC

### 1.1 Clonar o repositório

```bash
git clone <url-do-repo> Palio-IA
cd Palio-IA
```

`wheels/` já contém todos os pacotes ARM64 necessários (piper-tts, onnxruntime,
faster-whisper, scipy, ctranslate2, etc.). Não precisa baixar mais nada de pip.

---

### 1.2 Baixar o modelo Whisper small (~460 MB)

```bash
pip3 install huggingface_hub -q
python3 -m huggingface_hub download \
    Systran/faster-whisper-small \
    --local-dir Palio-IA/pendrive/whisper-small \
    --ignore-patterns "*.msgpack" "*.h5" "flax_model*" "tf_model*"
```

Resultado esperado em `Palio-IA/pendrive/whisper-small/`:
```
config.json
model.bin          ← ~460 MB
tokenizer.json
vocabulary.json
preprocessor_config.json
```

---

### 1.3 Baixar o binário Ollama ARM64

Baixar e extrair direto para o pendrive com um comando:

```bash
mkdir -p /tmp/ollama-extract && curl -fsSL https://ollama.com/download/ollama-linux-arm64.tar.zst | tar --use-compress-program=zstd -x -C /tmp/ollama-extract && cp /tmp/ollama-extract/bin/ollama Palio-IA/pendrive/ollama/ollama && chmod +x Palio-IA/pendrive/ollama/ollama
```

> Se o `tar` reclamar do zstd: `sudo apt install zstd`

---

### 1.4 Baixar o modelo llama3.2:3b (~2 GB)

Requer Ollama instalado no PC. Se não tiver:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Fazer pull e copiar:

```bash
ollama pull llama3.2:3b

# O install.sh cria um usuário de sistema 'ollama' — modelos ficam em /usr/share/ollama
# Copiar para o pendrive (requer sudo)
mkdir -p Palio-IA/pendrive/ollama/models
sudo cp -r /usr/share/ollama/.ollama/models/. Palio-IA/pendrive/ollama/models/
```

> Resultado esperado: `pendrive/ollama/models/manifests/` e `pendrive/ollama/models/blobs/` (~2 GB).

---

### 1.5 Estrutura final do pendrive

Copiar a pasta `Palio-IA/` inteira para o pendrive. A estrutura deve ficar:

```
pendrive/
└── Palio-IA/
    ├── main.py
    ├── req-offline.txt
    ├── setup.sh
    ├── models/
    │   └── pt_BR-cadu-medium.onnx    ← modelo piper (já no repo)
    ├── wheels/                        ← todos os wheels ARM64 (já no repo)
    │   ├── piper_tts-*.whl
    │   ├── faster_whisper-*.whl
    │   ├── ctranslate2-*.whl
    │   ├── scipy-*.whl
    │   └── ...
    ├── pendrive/
    │   ├── whisper-small/             ← modelo Whisper (passo 1.2)
    │   │   ├── model.bin
    │   │   └── ...
    │   └── ollama/
    │       ├── ollama                 ← binário ARM64 (passo 1.3)
    │       └── models/               ← llama3.2:3b (passo 1.4)
    │           ├── manifests/
    │           └── blobs/
    └── ...
```

---

## Fase 2 — Instalação na placa (offline)

### 2.1 Montar o pendrive

```bash
# Listar dispositivos para identificar o pendrive
lsblk

# Montar (ajustar /dev/sda1 conforme listado)
mkdir -p /mnt/usb
mount /dev/sda1 /mnt/usb

# Copiar o projeto para /root
cp -r /mnt/usb/Palio-IA /root/Palio-IA
cd /root/Palio-IA
```

---

### 2.2 Instalar dependências do sistema (apt)

A placa precisa de internet pelo menos uma vez para o apt, **ou** usar Docker no PC para baixar os .deb antes (ver seção opcional abaixo).

**Opção A — Com internet na placa (recomendado para primeira instalação):**

```bash
apt update
apt install -y \
    python3 python3-pip python3-dev python3-venv \
    python3-dbus python3-pyaudio \
    portaudio19-dev libportaudio2 libportaudiocpp0 libsndfile1 \
    bluez bluez-tools \
    pipewire pipewire-pulse pipewire-audio-client-libraries \
    wireplumber libspa-0.2-bluetooth \
    alsa-utils libasound2-dev \
    git wget unzip curl
```

Após isso, a placa nunca mais precisa de internet.

**Opção B — Totalmente offline (via Docker no PC):**

```bash
# No PC, baixar todos os .deb ARM64 via Docker
docker run --rm --platform linux/arm64 \
    -v $(pwd)/apt-debs:/packages \
    debian:bookworm bash -c "
        apt update && \
        apt-get install -y --download-only \
            python3 python3-pip python3-dev python3-venv \
            python3-dbus python3-pyaudio \
            portaudio19-dev libportaudio2 libportaudiocpp0 libsndfile1 \
            bluez bluez-tools \
            pipewire pipewire-pulse pipewire-audio-client-libraries \
            wireplumber libspa-0.2-bluetooth \
            alsa-utils libasound2-dev && \
        cp /var/cache/apt/archives/*.deb /packages/
    "

# Adicionar apt-debs/ ao pendrive
# Na placa, instalar:
dpkg -i /mnt/usb/Palio-IA/apt-debs/*.deb
```

---

### 2.3 Criar o ambiente Python e instalar pacotes

```bash
cd /root/Palio-IA

python3 -m venv --system-site-packages venv

# PyAudio vem do apt (python3-pyaudio via --system-site-packages)
# Todos os outros vêm dos wheels locais
venv/bin/pip install --no-index --find-links=wheels/ -r req-offline.txt
```

---

### 2.4 Instalar o Ollama

```bash
# Copiar binário
cp /mnt/usb/Palio-IA/pendrive/ollama/ollama /usr/local/bin/ollama
chmod +x /usr/local/bin/ollama

# Copiar modelo llama3.2:3b
mkdir -p /root/.ollama
cp -r /mnt/usb/Palio-IA/pendrive/ollama/models /root/.ollama/models

# Verificar
ollama list   # deve mostrar llama3.2:3b
```

---

### 2.5 Instalar o modelo Whisper

```bash
mkdir -p /root/.cache/huggingface/hub
cp -r /mnt/usb/Palio-IA/pendrive/whisper-small \
    /root/.cache/huggingface/hub/models--Systran--faster-whisper-small
```

> O `HF_HUB_OFFLINE=1` já está configurado no serviço systemd — o faster-whisper
> não tentará conectar à internet para verificar atualizações.

---

### 2.6 Ativar git hooks

```bash
cd /root/Palio-IA
git config core.hooksPath .githooks
```

---

### 2.7 Configurar Bluetooth

```bash
# AutoEnable no boot
BT_CONF="/etc/bluetooth/main.conf"
grep -q "AutoEnable=true" "$BT_CONF" || echo -e "\n[Policy]\nAutoEnable=true" >> "$BT_CONF"

systemctl enable bluetooth
systemctl restart bluetooth
```

---

### 2.8 Configurar PipeWire / áudio

```bash
bash /root/Palio-IA/scripts/bluetooth_config.sh
```

---

### 2.9 Configurar serviços systemd (boot automático)

```bash
bash /root/Palio-IA/setup.sh
# O setup.sh fará as seções 4 (venv), 7 (systemd) e 8 (áudio) normalmente.
# As seções 5 (Ollama) e 6 (BT) podem ser puladas — já feitas nos passos 2.4 e 2.7.
```

Ou configurar manualmente os serviços:

```bash
# Serviço Ollama
cat > /etc/systemd/system/ollama.service << 'EOF'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/ollama serve
Restart=on-failure
RestartSec=5
Environment="OLLAMA_HOST=127.0.0.1:11434"

[Install]
WantedBy=multi-user.target
EOF

# Serviço Palio-IA
cat > /etc/systemd/system/palio-ia.service << EOF
[Unit]
Description=Palio-IA Voice Assistant
After=bluetooth.target sound.target ollama.service
Wants=bluetooth.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/Palio-IA
ExecStartPre=/bin/sleep 8
ExecStart=/root/Palio-IA/venv/bin/python main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment="PYTHONUNBUFFERED=1"
Environment="XDG_RUNTIME_DIR=/run/user/0"
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus"
Environment="HF_HUB_OFFLINE=1"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ollama.service palio-ia.service
```

---

### 2.10 Teste antes do reboot

```bash
# Testar TTS
cd /root/Palio-IA
venv/bin/python test/tts.py "Olá, eu sou o Palio."

# Testar STT (Ctrl+C para sair)
venv/bin/python test/stt.py

# Testar ciclo completo STT → LLM → TTS (Ctrl+C para sair)
systemctl start ollama   # sobe o Ollama primeiro
venv/bin/python test/chat.py
```

---

### 2.11 Reboot e validação final

```bash
reboot
```

Após boot:
- **Dois bipes** = Palio-IA inicializou com sucesso
- Dizer **"carro, olá"** = resposta pelo alto-falante
- `journalctl -u palio-ia.service -f` = logs em tempo real

---

## Troubleshooting

| Sintoma | Causa provável | Solução |
|---|---|---|
| Sem bipes no boot | Serviço não iniciou | `journalctl -u palio-ia.service -n 50` |
| "Meu cérebro tá offline" ao falar | Ollama não subiu | `systemctl status ollama` → `journalctl -u ollama -n 20` |
| STT não reconhece nada | Microfone errado | `AUDIO_DEVICE=N venv/bin/python test/stt.py` — listar com `venv/bin/python3 -c "import pyaudio; p=pyaudio.PyAudio(); [print(i, p.get_device_info_by_index(i)['name']) for i in range(p.get_device_count()) if p.get_device_info_by_index(i)['maxInputChannels']>0]"` |
| Wake word não detecta | Threshold alto | `WHISPER_SILENCE_THRESHOLD=200 venv/bin/python test/stt.py` |
| Sem áudio na saída | Sink padrão errado | `pactl list sinks short` → `pactl set-default-sink <nome>` |
| Bluetooth não conecta no boot | BT não iniciou antes do Palio | `systemctl status bluetooth` → verificar `AutoEnable=true` em `/etc/bluetooth/main.conf` |
