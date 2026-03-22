# Funcionalidades

## Funcionalidades Implementadas

### Reconhecimento de Voz Offline (STT)
**Descrição**: Captura áudio contínuo do microfone e converte fala em texto usando o modelo Vosk PT-BR localmente, sem depender de internet.

**Componentes Envolvidos**:
- `speech_to_text.py` — módulo principal do STT
- `model-ptbr/` — modelo Vosk (deve ser baixado manualmente)
- `PyAudio` — captura do microfone
- `scipy.signal.resample` — ajuste de taxa de amostragem

**Fluxo de execução**:
1. Detecta o melhor microfone disponível (mais próximo de 16kHz)
2. Abre stream de áudio com a taxa nativa do microfone
3. Lê chunks de 4096 amostras em loop contínuo
4. Se taxa do microfone != 16kHz, reamostra para 16kHz (Vosk exige)
5. Alimenta o recognizer Vosk com os bytes de áudio
6. Quando `AcceptWaveform()` retorna `True`, processa o resultado final
7. Extrai texto reconhecido do JSON de resultado

**Dependências**: Modelo Vosk PT-BR em `./model-ptbr/`

---

### Auto-seleção de Microfone
**Descrição**: Itera por todos os dispositivos de áudio disponíveis e seleciona automaticamente o microfone cuja taxa nativa é mais próxima de 16kHz.

**Componentes Envolvidos**: `speech_to_text.py` — função `get_best_microphone()`

**Comportamento**: Se nenhum microfone for encontrado, o programa encerra com `exit(1)`.

---

### Resampling de Áudio
**Descrição**: Converte áudio capturado na taxa nativa do microfone para 16kHz (taxa exigida pelo Vosk).

**Componentes Envolvidos**: `speech_to_text.py` — função `resample_audio()`

---

### Wake Word + Detecção de Comando
**Descrição**: Após o STT converter fala em texto, verifica se a wake word está presente e aciona o dispatcher.

**Wake word**: `"carro"`

**Normalização**: Usa `verificar_palavra()` que remove acentos e ignora maiúsculas antes de comparar.

---

### Síntese de Voz Offline (TTS)
**Descrição**: Converte texto em fala usando `pyttsx3` offline, salva em arquivo WAV temporário e reproduz via `sounddevice`.

**Componentes Envolvidos**: `main.py` — função `falar()`

**Fluxo**:
1. Inicializa engine pyttsx3
2. Configura taxa: 160 palavras/minuto, volume: 1.0
3. Salva texto como `output.wav` via `engine.save_to_file()`
4. Reproduz com `sounddevice` + `soundfile`
5. Remove `output.wav` após reprodução

---

### Normalização de Texto (Utilitário)
**Descrição**: Funções auxiliares para comparação de strings sem sensibilidade a acentos ou capitalização.

**Componentes Envolvidos**: `speech_to_text.py`

```python
remove_acentos(texto)              # Normaliza NFD e remove diacríticos
verificar_palavra(frase, palavra)  # Busca substring ignorando acentos e case
```

---

### Orquestrador Principal
**Descrição**: `main.py` integra todos os módulos em um único loop de execução contínua.

**Fluxo**:
```
Boot:
  1. Toca som de boot simples (dois bipes curtos)
  2. Sistema fica aguardando

Loop contínuo:
  1. STT ouve microfone
  2. Detecta wake word "carro"
  3. Duck de áudio reduz volume para 20% imediatamente
  4. Extrai o comando após a wake word
  5. Dispatcher roteia para música, pareamento ou LLM
  6. TTS fala a resposta
  7. Duck restaura o volume
  8. Volta ao passo 1
```

---

### Dispatcher de Intenção
**Descrição**: Roteador central que recebe o texto do STT e decide qual módulo executar.

**Componentes Envolvidos**: `modules/core/dispatcher.py`

**Prioridade de roteamento**:
1. Modo pareamento ativo → `PairingManager`
2. Comando de pareamento/dispositivos → `PairingManager`
3. Comando de música mapeado → `BluetoothMusicController`
4. Nenhum dos anteriores → `OllamaClient` (LLM)

---

### Controle de Música via Bluetooth (AVRCP)
**Descrição**: Controla o player de música do celular conectado via Bluetooth AVRCP usando bluez + dbus.

**Componentes Envolvidos**: `modules/bluetooth/music.py`

**Comandos reconhecidos**:
| Frase dita | Ação |
|---|---|
| "próxima", "passa", "skip" | Próxima faixa |
| "volta", "anterior" | Faixa anterior |
| "pausa", "para", "pare", "parar" | Pausar |
| "toca", "play", "continua" | Retomar |
| "que música é essa" | Info da faixa atual |

**Requisito**: Linux + bluez + `python3-dbus`

---

### Pareamento Bluetooth por Voz
**Descrição**: Fluxo de pareamento de dispositivo Bluetooth (celular) controlado por voz, com persistência em `data/devices.json`. Apenas 1 dispositivo salvo por vez.

**Componentes Envolvidos**: `modules/bluetooth/pairing.py`

**Modos**:
- **Modo pareamento** (`"carro modo de pareamento"`): Rock Pi fica visível e pareável por 60s → usuário conecta pelo celular (inicia a conexão pelo lado do celular) → Rock Pi detecta a conexão, salva o dispositivo (sobrescreve o anterior) → confirma "Dispositivo conectado e salvo."
- **Conectar** (`"carro conectar"`): tenta conectar ao dispositivo salvo → "Dispositivo conectado." ou "Não foi possível achar o dispositivo."

**Comportamento no boot**: O sistema NÃO tenta conectar automaticamente ao ligar. Aguarda comando de voz.

**Persistência**: `data/devices.json` — guarda apenas 1 dispositivo (o último pareado).

---

### Audio Duck
**Descrição**: Reduz o volume do sink de saída ao detectar a wake word e restaura após o TTS terminar.

**Componentes Envolvidos**: `modules/bluetooth/audio_duck.py`

**Comportamento**:
- `on_wake_word()` → salva volume atual → aplica 20% instantaneamente
- `on_done()` → restaura volume original

**Requisito**: Linux + PipeWire + `pactl`

---

### LLM Local (Ollama)
**Descrição**: Responde perguntas e processa comandos não mapeados usando LLM local com persona "Palio".

**Componentes Envolvidos**: `modules/llm/client.py`, `modules/llm/persona.py`

**Modelo padrão**: `llama3.2:3b`

**Persona**: O assistente fala como se fosse o próprio carro Fiat Palio — direto, informal, humor seco.

**Requisito**: Ollama instalado e rodando (`ollama serve`)

---

## Funcionalidades Planejadas


---

### Controle de Volume por Voz
**Descrição**: Aumentar ou diminuir o volume do sistema por comando de voz.

**Componente preparado**: `modules/bluetooth/audio.py` — `BluetoothAudioController` (implementado, ainda não integrado ao dispatcher)

**Integração pendente**: Adicionar intents de volume no `dispatcher.py` e conectar ao `BluetoothAudioController`.

---

## Fora do Escopo (removido dos planos)

- **Navegação GPS** — complexidade alta, sem definição de integração, removido dos planos por enquanto
- **Chamadas telefônicas** — requer HFP, removido dos planos por enquanto
- **Clima / APIs externas** — o projeto é 100% offline; funcionalidades que exigem internet não serão implementadas

---

## Princípio fundamental

> **O projeto é 100% offline.** Toda feature nova deve funcionar sem conexão com internet. Qualquer funcionalidade que exija rede está fora do escopo.

---

## Revisão pós-primeiro teste no Rock Pi

**Após o primeiro uso real no carro**, fazer uma rodada de revisão/limpeza cobrindo:

- Ajuste fino do PipeWire (nome real do sink analógico, latência, volume padrão)
- Validar fluxo completo: boot → pareamento → música → TTS → duck → restaura
- Revisar tempos de espera no boot (ExecStartPre no systemd)
- Identificar qualquer comando de voz que o Vosk não esteja reconhecendo bem no ambiente real (ruído de carro, motor)
- Avaliar se o modelo Vosk small é suficiente ou se vale o modelo grande
- Checar se o AudioDuck está com o percentual certo (20%) no ambiente real
- Limpar qualquer workaround ou TODO deixado durante o desenvolvimento inicial

---

## Evolução do Projeto por Versão

| Versão | Descrição |
|--------|-----------|
| v0.0.1 | Criação dos módulos TTS e STT iniciais |
| v0.0.2 | TTS offline com pyttsx3 |
| v0.0.3 | Melhorias gerais |
| v0.0.4 | Comandos de voz básicos |
| v0.0.5 | Melhorias STT |
| v0.0.6 | STT offline com Vosk |
| v0.0.7 | Voz e reconhecimento configurados |
| v0.0.8 | Migração para sounddevice (cross-platform), remoção do winsound |
| v0.0.9 | Bluetooth AVRCP, pareamento por voz, LLM Ollama, AudioDuck, Dispatcher |
| v0.1.0 | Wake word "carro", arquitetura AUX P2, pareamento por modo descobrível, boot sound, setup.sh |
| v0.2.0 | Controle de volume por voz (aumenta, diminui, volume 1-10), README.md, PipeWire configurado |
