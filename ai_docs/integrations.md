# Integrações

## Hardware

### Radxa ROCK 4B (Hardware de Deploy)
**Tipo**: Single-board computer (SBC) ARM64

**Especificações**:
- CPU: Rockchip RK3399 — Cortex-A72 dual-core 1.8GHz + Cortex-A53 quad-core 1.4GHz
- RAM: 4GB LPDDR4
- Armazenamento: SD card 32GB
- SO: Debian 12 Bookworm ARM64 (CLI, sem desktop) — imagem oficial Radxa
- Conectividade: WiFi 802.11ac, Bluetooth 5.0, USB 3.0

**Compatibilidade**: Qualquer placa que rode Debian 12 Bookworm ARM64 é compatível.

**Papel no sistema**: Computador principal embarcado dentro do carro. Executa todos os processos Python — STT, TTS, LLM (Ollama), controle Bluetooth.

**Dependências críticas para o deploy**:
```bash
sudo apt install python3-dbus bluez bluez-utils espeak-ng portaudio19-dev \
                 pipewire wireplumber libspa-0.2-bluetooth
```

---

### Microfone
**Tipo**: Dispositivo de entrada de áudio (USB recomendado)

**Integração via**: `PyAudio` — detecta e seleciona automaticamente o melhor dispositivo

**Requisito**: Taxa de amostragem >= 16kHz. Microfones USB são recomendados por terem melhor isolamento de ruído.

---

## Modelo de Voz (Vosk PT-BR)

**Tipo**: Modelo de reconhecimento de fala local

**Localização**: `./model-ptbr/` (não versionado no git)

**Origem**: https://alphacephei.com/vosk/models

**Modelos disponíveis para PT-BR**:
| Modelo | Tamanho | Recomendado para |
|--------|---------|-----------------|
| `vosk-model-small-pt-0.3` | ~30MB | Deploy (ARM64) |
| `vosk-model-pt-fb-v0.1.1-20220516_2113` | ~1.5GB | Maior precisão |

**Dependência crítica**: Sem o modelo o sistema não inicializa (`exit(1)`).

---

## Celular via Bluetooth

**Tipo**: Dispositivo Android/iOS conectado via Bluetooth

**Protocolos**:
- **A2DP** — recebe o stream de áudio do celular no Rock Pi (Rock Pi age como sink/destino)
- **AVRCP** — controla o player de música do celular (próxima, anterior, pausa, play, info)

**Implementação**: `modules/bluetooth/music.py` via dbus + bluez

**Requisitos**:
```bash
sudo apt install bluez bluez-utils python3-dbus
```

**Pareamento**: Gerenciado por voz via `modules/bluetooth/pairing.py`.
- O Rock Pi fica em modo visível/pareável aguardando o celular conectar (não o contrário)
- Apenas 1 dispositivo salvo por vez em `data/devices.json`
- Sem conexão automática no boot — aguarda comando "carro conectar"

---

## Stack de Áudio (PipeWire)

**Servidor de áudio**: PipeWire

**Arquitetura**:
```
[Celular] → BT A2DP sink → PipeWire → loopback → saída analógica (P2) → [Rádio do carro]
                                           ↑
                                 TTS misturado aqui
```

**Saída física**: Cabo P2 (3.5mm) conectado diretamente na entrada AUX do rádio do Fiat Palio. O rádio **não** é pareado via Bluetooth.

**Controle de volume**: `pactl` com `@DEFAULT_SINK@` — aponta para o sink analógico (P2). Usado pelo `AudioDuck` e futuro controle de volume por voz.

**Requisitos**:
```bash
sudo apt install pipewire wireplumber libspa-0.2-bluetooth
```

---

## Ollama (LLM Local)

**Tipo**: Servidor de LLM local

**Propósito**: Responder perguntas e processar comandos não mapeados em linguagem natural

**Modelo padrão**: `llama3.2:3b` (~2GB, ~1-3 tokens/s no RK3399)

**Interface**: API REST local
```
POST http://localhost:11434/api/chat
```

**Instalação**:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
```

**Implementação**: `modules/llm/client.py` — mantém histórico multi-turno, injeta system prompt da persona Palio.

**Fallback**: Se Ollama não estiver rodando, o sistema responde "Meu cérebro tá offline agora." Os demais módulos (música, pareamento) continuam funcionando normalmente.

---

## pyttsx3 + espeak-ng (TTS)

**Engine no Linux/ARM64**: `espeak-ng`

```bash
sudo apt install espeak-ng
```

**Nota**: A qualidade do espeak-ng é funcional mas robótica. Para voz mais natural no futuro, considerar `piper-tts` (offline, modelos PT-BR disponíveis).

---

## Diagrama de Integração

```
                    ┌─────────────────────────────────────────┐
                    │           Debian 12 ARM64                │
                    │                                          │
  [Mic USB] ────────┤→ PyAudio → Vosk (model-ptbr) → STT     │
                    │                    ↓                     │
                    │           Dispatcher de intenção         │
                    │          /          |          \          │
                    │   Música      Pareamento      LLM        │
                    │      ↓            ↓            ↓        │
                    │  AVRCP BT    bluetoothctl    Ollama      │
                    │      \            |           /          │
                    │       ↘          ↓          ↙           │
                    │         pyttsx3 + espeak-ng (TTS)        │
                    │              ↓                           │
                    │       sounddevice → sink P2              │
                    │                                          │
                    │  [BT A2DP sink] ←── [Celular]           │
                    │  música + AVRCP → cabo P2 → [Rádio]     │
                    └─────────────────────────────────────────┘
```

---

## Resiliência e Tratamento de Falhas

| Componente | Falha | Comportamento |
|---|---|---|
| Modelo Vosk | Pasta ausente | `exit(1)` com mensagem clara |
| Microfone | Nenhum encontrado | `exit(1)` |
| Stream de áudio | Erro ao abrir | `exit(1)` |
| Buffer overflow | Silencioso | `exception_on_overflow=False` |
| Ollama offline | Indisponível | Fallback: "Meu cérebro tá offline." Música/pareamento continuam |
| Bluetooth indisponível | Não conectado | Dispatcher informa via TTS: "Não tem nenhum celular conectado." |
| dbus-python ausente | ImportError | Log de erro + BT indisponível (sistema continua sem BT) |
