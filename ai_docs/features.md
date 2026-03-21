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

**Wake word**: `"palio"`

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
Loop contínuo:
  1. STT ouve microfone
  2. Detecta wake word "palio"
  3. Extrai o comando após a wake word
  4. Duck de áudio reduz o volume
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
| "pausa", "para" | Pausar |
| "toca", "play", "continua" | Retomar |
| "que música é essa" | Info da faixa atual |

**Requisito**: Linux + bluez + `python3-dbus`

---

### Pareamento Bluetooth por Voz
**Descrição**: Fluxo completo de pareamento de dispositivos Bluetooth controlado por voz, com persistência em `data/devices.json`.

**Componentes Envolvidos**: `modules/bluetooth/pairing.py`

**Modos**:
- **Manual** (`"modo parear"`): scan ao vivo → usuário escolhe dispositivo → pair + trust + connect + salva
- **Automático** (`"pareamento automático"`): conecta o último sink e source salvos
- **Gerenciamento**: listar, remover, reconectar dispositivos salvos

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

### Migração de Saída de Áudio: Bluetooth → 3.5mm AUX
**Descrição**: Trocar a saída de áudio do Rock Pi para o rádio do carro de Bluetooth A2DP para cabo 3.5mm direto na entrada AUX do rádio.

**Motivação**:
- Elimina o pareamento do rádio — só o celular precisa ser pareado
- Resolve o problema do primeiro boot (áudio sempre disponível, sem depender de Bluetooth)
- Conexão mais estável, sem dropout de Bluetooth
- Menos carga no chip Bluetooth (uma conexão ao invés de duas)

**Arquitetura atual:**
```
Celular → Bluetooth A2DP (entrada) → Rock Pi → Bluetooth A2DP (saída) → Rádio
```
**Arquitetura alvo:**
```
Celular → Bluetooth A2DP (entrada) → Rock Pi → 3.5mm cabo → Rádio AUX
```

**Impacto no código:**
- Role `"source"` em `modules/bluetooth/pairing.py` vira obsoleto (só haverá pareamento de entrada/celular)
- Docs e diagramas de integração precisam ser atualizados

**Pré-requisito físico**: Confirmar se o rádio do Fiat Palio tem entrada AUX 3.5mm.

**Status**: Aguardando confirmação do AUX no rádio.

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
