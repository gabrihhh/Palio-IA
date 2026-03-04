# Integrações

## Hardware

### Rock Pi 4B (Hardware de Deploy)
**Tipo**: Single-board computer (SBC) ARM64

**Especificações relevantes**:
- CPU: Rockchip RK3399 — Cortex-A72 dual-core 1.8GHz + Cortex-A53 quad-core 1.4GHz
- RAM: 4GB LPDDR4 (típico)
- SO: Linux (Debian/Ubuntu ARM64)
- Conectividade: WiFi 802.11ac, Bluetooth 5.0, USB 3.0, GPIO

**Papel no sistema**: Computador principal embarcado dentro do carro. Executa todos os processos Python — STT, TTS, LLM (Ollama), e futuramente controle de Bluetooth/GPIO.

**Status**: Hardware disponível, ainda não configurado completamente para o projeto.

**Dependências críticas para o deploy**:
- Python 3.x instalado
- Modelo Vosk PT-BR baixado em `./model-ptbr/`
- `espeak` ou `espeak-ng` instalado (backend do pyttsx3 no Linux)
- `portaudio19-dev` instalado (dependência do PyAudio no Linux)
- Ollama instalado (para integração LLM futura)

---

### Microfone
**Tipo**: Dispositivo de entrada de áudio (USB ou integrado)

**Integração via**: `PyAudio` — detecta e seleciona automaticamente o melhor dispositivo

**Requisito**: Taxa de amostragem >= 16kHz. Microfones USB são recomendados por terem melhor isolamento de ruído.

**Posicionamento físico**: A SER DEFINIDO — posicionamento no carro afeta diretamente a qualidade do reconhecimento (ruído de motor, vento, música).

---

## Modelo de Voz (Vosk PT-BR)

**Tipo**: Modelo de reconhecimento de fala local (arquivo de dados)

**Localização**: `./model-ptbr/` (pasta local, não versionada)

**Origem**: https://alphacephei.com/vosk/models

**Modelos disponíveis para PT-BR**:
| Modelo | Tamanho | Precisão | Velocidade | Recomendado para |
|--------|---------|----------|------------|-----------------|
| `vosk-model-small-pt-0.3` | ~30MB | Moderada | Rápida | Rock Pi 4B |
| `vosk-model-pt-fb-v0.1.1-20220516_2113` | ~1.5GB | Alta | Lenta | Desenvolvimento |

**Dependência**: Crítica — sem o modelo o sistema não inicializa.

**Protocolo**: Acesso local via filesystem (não há rede envolvida).

---

## Celular via Bluetooth

**Tipo**: Dispositivo Android/iOS conectado ao Rock Pi 4B

**Propósito**: Fonte de música e destino de áudio para o carro

**Protocolo planejado**: Bluetooth A2DP (Advanced Audio Distribution Profile) para receber o áudio do celular, AVRCP (Audio/Video Remote Control Profile) para controlar o player de música

**Status**: A SER CONFIGURADO

**Desafio técnico**: No Linux, o Rock Pi 4B precisa ser configurado como sink Bluetooth A2DP para receber o stream de áudio do celular. Isso requer:
- `bluez` e `bluez-utils` instalados
- `pulseaudio` ou `pipewire` com módulo Bluetooth
- Pareamento e configuração do perfil A2DP

**Controle de música (AVRCP)**:
```bash
# Biblioteca Python para controle AVRCP
# dbus-python + bluez DBus API
```

---

## Ollama (LLM Local) — Planejado

**Tipo**: Servidor de LLM local

**Propósito**: Responder perguntas e processar comandos não mapeados em linguagem natural

**Interface**: API REST local
```
POST http://localhost:11434/api/generate
POST http://localhost:11434/api/chat
```

**Modelos candidatos para Rock Pi 4B**:
| Modelo | Tamanho | Recursos | Adequação |
|--------|---------|----------|-----------|
| `llama3.2:3b` | ~2GB | ~2GB RAM | Boa para ARM |
| `mistral:7b-instruct-q4_K_M` | ~4GB | ~4-6GB RAM | Requer Rock Pi 4B 4GB+ |
| `phi3:mini` | ~2.3GB | ~2GB RAM | Boa alternativa leve |

**Fluxo de integração planejado**:
```python
import requests

def consultar_llm(pergunta, historico=[]):
    response = requests.post('http://localhost:11434/api/chat', json={
        "model": "llama3.2:3b",
        "messages": historico + [{"role": "user", "content": pergunta}],
        "stream": False
    })
    return response.json()['message']['content']
```

**Status**: A IMPLEMENTAR

**Dependência**: Ollama instalado e rodando no Rock Pi 4B (`ollama serve`)

---

## Sistema Operacional do Carro (Som / GPIO)

### Sistema de Som
**Tipo**: Hardware de áudio do carro

**Integração**: O Rock Pi 4B conecta ao sistema de som do carro via entrada auxiliar (P2/P3.5mm) ou Bluetooth

**Saída de áudio TTS**: `pyttsx3` → `output.wav` → reprodução via placa de som do Rock Pi

### GPIO (Futuro)
**Tipo**: Pinos de entrada/saída do Rock Pi 4B

**Uso potencial**: Botão físico de ativação, LEDs de status, conexão com controles do volante

**Biblioteca**: `RPi.GPIO` ou `gpiod` para Linux

---

## APIs Externas Planejadas

### Clima
**Serviço**: OpenWeatherMap (ou similar)
**Endpoint**: `https://api.openweathermap.org/data/2.5/weather`
**Autenticação**: API Key
**Dependência de conectividade**: Requer internet — funcionalidade offline não disponível
**Status**: A SER IMPLEMENTADO

### Navegação GPS
**Integração**: A DEFINIR — possíveis abordagens:
1. Integração via ADB com Google Maps no celular
2. App de navegação no próprio Rock Pi (OsmAnd Linux)
3. API de direções (Google Maps API, OpenRouteService)

**Status**: A DEFINIR

---

## pyttsx3 e Engine de TTS do Sistema

**Tipo**: Biblioteca Python que usa engine nativa do SO

**No Windows (desenvolvimento)**:
- Engine: SAPI5 (Microsoft Speech API)
- Vozes disponíveis: depende das vozes instaladas no Windows

**No Linux/Rock Pi 4B (produção)**:
- Engine: `espeak` ou `espeak-ng`
- Instalação necessária: `sudo apt install espeak espeak-ng`
- Vozes PT-BR para espeak: `sudo apt install espeak-data`
- Qualidade de voz: Menor que SAPI5 — considerar alternativas como `piper-tts` para voz mais natural offline

**Nota**: Ao mudar de Windows para Linux, a voz do assistente soará diferente (espeak tem qualidade inferior à SAPI5). Para voz mais natural no Rock Pi, considerar:
- `piper-tts` — TTS offline de alta qualidade com modelos PT-BR
- `coqui-tts` — Alternativa open-source

---

## Diagrama de Integração

```
                    ┌─────────────────────────────────────────┐
                    │              Rock Pi 4B                  │
                    │                                          │
  [Microfone] ──────┤→ PyAudio → Vosk (model-ptbr) → STT     │
                    │                    ↓                     │
                    │           Detecção de intenção           │
                    │          /                    \          │
                    │   Comando             Pergunta           │
                    │   mapeado             livre              │
                    │      ↓                  ↓               │
                    │  Executa            Ollama               │
                    │  ação               (LLM local)          │
                    │      \                  /               │
                    │       ↘              ↙                  │
                    │         pyttsx3 (TTS)                    │
                    │              ↓                           │
  [Alto-falante] ←──┤       Reproduz resposta                  │
                    │                                          │
                    │  [Bluetooth] ←──→ [Celular]              │
                    │    A2DP (música)                          │
                    │    AVRCP (controle)                      │
                    │                                          │
                    │  [Internet?] → API Clima (opcional)      │
                    └─────────────────────────────────────────┘
```

---

## Resiliência e Tratamento de Falhas

| Componente | Falha | Comportamento Atual | Comportamento Ideal |
|------------|-------|---------------------|---------------------|
| Modelo Vosk | Pasta ausente | `exit(1)` | Mensagem clara + instrução de download |
| Microfone | Nenhum encontrado | `exit(1)` | Tentar novamente / modo fallback |
| Stream de áudio | Erro ao abrir | `exit(1)` | Tentar dispositivo alternativo |
| Buffer overflow | Silencioso | `exception_on_overflow=False` | Log + ignorar |
| Ollama offline | N/A (não implementado) | N/A | Fallback para comandos predefinidos |
| Bluetooth indisponível | N/A (não implementado) | N/A | Informar usuário via TTS |
| Internet indisponível | N/A | N/A | Desabilitar funções que requerem rede |
