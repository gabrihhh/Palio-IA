# Funcionalidades

## Funcionalidades Implementadas

### Reconhecimento de Voz Offline (STT)
**Descrição**: Captura áudio contínuo do microfone e converte fala em texto localmente, sem depender de internet. Suporta dois backends intercambiáveis via `STT_BACKEND`.

**Backends disponíveis**:

| Backend | Variável | Precisão | Latência (notebook) | Latência (Rock Pi 4B) |
|---|---|---|---|---|
| faster-whisper `small` | `STT_BACKEND=whisper` (padrão) | Alta | ~1s | ~2-4s |
| Vosk PT-BR | `STT_BACKEND=vosk` | Média | ~0.5s | ~0.5s |

**Componentes**:
- `speech_to_text.py` — backend Vosk + funções compartilhadas (resample, fuzzy match, seleção de mic)
- `modules/stt/whisper_backend.py` — backend Whisper com VAD por energia
- `PyAudio` — captura do microfone
- `scipy.signal.resample_poly` — resampling para 16kHz (ratio limpo 3:1 a 48kHz)

**Arquitetura dois estágios (ambos os backends)**:
- **Estágio 1** — sempre ouvindo, procura apenas a wake word
- **Estágio 2** — após wake word, captura o próximo utterance como comando; timeout 5s
- `DUCK_WAIT = 0.4s` entre wake word e início do estágio 2

**Filtro passa-banda** (`bandpass_filter()` em `speech_to_text.py:53-62`):
- Filtra áudio para faixa de voz humana (300–3400Hz)
- Reduz bleeding de música tocando no carro
- No Whisper: aplicado APENAS para cálculo de energia (VAD) — o áudio enviado ao modelo é raw resampled
- No Vosk: aplicado antes do `KaldiRecognizer`

**Fluxo Whisper** (`CHUNK=1024`):
1. Detecta o melhor microfone (respeita `AUDIO_DEVICE`), captura preferencial a 48kHz
2. Para cada chunk: resample → bandpass → calcula energia (VAD)
3. Quando energia > threshold: acumula chunks em `speech_buffer` (com pre-buffer de 0.3s)
4. Ao detectar silêncio (`WHISPER_SILENCE_DURATION=0.8s`): transcreve buffer com Whisper (sem bandpass)
5. Checa wake word com fuzzy matching (75%) → entra estágio 2

**Fluxo Vosk** (`CHUNK=4096`):
1. Detecta microfone, captura preferencial a 48kHz
2. Lê chunks em loop: resample_poly → bandpass → `KaldiRecognizer`
3. Quando `AcceptWaveform()` retorna `True`, processa resultado final
4. Checa wake word → entra estágio 2

---

### Seleção de Microfone
**Descrição**: Itera por todos os dispositivos de áudio disponíveis e seleciona automaticamente o microfone cuja taxa nativa é mais próxima de 16kHz.

**Componentes Envolvidos**: `speech_to_text.py` — função `get_best_microphone()`

**Comportamento**:
- Se `AUDIO_DEVICE=N` estiver definido, usa o dispositivo N diretamente (sem auto-seleção)
- Caso contrário, auto-seleciona por proximidade de taxa com 16kHz
- Se nenhum microfone for encontrado, encerra com `exit(1)`

**Listar dispositivos disponíveis**:
```bash
AUDIO_DEVICE=2 venv/bin/python3 -c "import pyaudio; p=pyaudio.PyAudio(); [print(f'[{i}]', p.get_device_info_by_index(i)['name']) for i in range(p.get_device_count()) if p.get_device_info_by_index(i)['maxInputChannels']>0]; p.terminate()"
```

---

### Resampling de Áudio
**Descrição**: Converte áudio capturado na taxa nativa do microfone para 16kHz (taxa exigida pelo Vosk e Whisper).

**Componentes Envolvidos**: `speech_to_text.py` — função `resample_audio()`

**Implementação**: `scipy.signal.resample_poly` com ratio calculado via `gcd`. Prefere captura a 48kHz (ratio 3:1 com 16kHz, sem artefatos de borda). Resultado sempre em `int16`.

---

### Wake Word + Detecção de Comando
**Descrição**: Após o STT converter fala em texto, verifica se a wake word está presente e aciona o dispatcher.

**Wake word**: `"carro"`

**Detecção**: `verificar_palavra()` em `speech_to_text.py` usa dois métodos combinados:
1. **Correspondência exata** (substring) — remove acentos e ignora maiúsculas
2. **Fuzzy matching** (fallback) — usa `difflib.SequenceMatcher` com limiar de 75% para aceitar erros fonéticos do STT (ex: "carla" → "carro", "caro" → "carro")

---

### Síntese de Voz Offline (TTS)
**Descrição**: Converte texto em fala usando `pyttsx3` offline, salva em arquivo WAV temporário e reproduz via `sounddevice`.

**Componentes Envolvidos**: `main.py` — funções `falar()` e `_limpar_markdown()`

**Fluxo**:
1. Resposta do dispatcher passa por `_limpar_markdown()` (`main.py`) — remove `**bold**`, `_itálico_`, `` `código` ``, `# títulos`, `- bullets`, `> blockquotes`
2. Inicializa engine pyttsx3
3. Configura taxa: 160 palavras/minuto, volume: 1.0
4. Salva texto como `output.wav` via `engine.save_to_file()`
5. Reproduz com `sounddevice` + `soundfile`
6. Remove `output.wav` após reprodução

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

### Controle de Volume por Voz
**Descrição**: Ajusta o volume do sink padrão do PipeWire via `pactl` por comandos de voz.

**Componentes Envolvidos**: `modules/bluetooth/audio.py` → `VolumeController`, `modules/core/dispatcher.py`

**Comandos reconhecidos**:
| Frase dita | Ação |
|---|---|
| "aumenta", "aumentar", "sobe", "mais volume" | +10% |
| "diminui", "diminuir", "desce", "abaixa" | -10% |
| "volume [um..dez]" | define absoluto (volume 7 = 70%, volume 10 = 100%) |

**Detalhe de implementação**: o volume é aplicado **após** `duck.on_done()` para não ser sobrescrito pela restauração do AudioDuck. O dispatcher armazena como `pending_volume` e o `main.py` consome depois do duck (`main.py:181-189`).

**Requisito**: Linux + PipeWire + `pactl`

---

## Funcionalidades Planejadas

### [PEQUENO] Comando de voz para resetar histórico da conversa
**Problema**: `OllamaClient.reset_history()` existe (`client.py:122`) mas não há nenhum comando de voz conectado a ele. O usuário não consegue limpar o contexto da conversa sem reiniciar o sistema.

**O que fazer**: adicionar intenção `"esquece"` / `"nova conversa"` / `"reseta"` no dispatcher (`dispatcher.py`) que chame `llm.reset_history()` e retorne algo como `"Pronto, esqueci tudo. Pode começar."`.

---

### [PEQUENO] `AUDIO_DEVICE` no serviço systemd
**Problema**: `palio-ia.service` não define `AUDIO_DEVICE`. No Rock Pi com múltiplos dispositivos de áudio (HDMI, analógico, USB), a auto-seleção pode escolher o dispositivo errado.

**O que fazer**: após identificar o índice correto do microfone no Rock Pi real, adicionar `Environment="AUDIO_DEVICE=N"` no `palio-ia.service` (e atualizar o `palio-ia.service` na raiz para referência).

---

### [MÉDIO] Auto-connect Bluetooth no boot
**Problema**: o usuário precisa dizer `"carro conectar"` toda vez que liga o carro. O sistema não tenta conectar ao dispositivo salvo automaticamente.

**Decisão pendente**: verificar se isso é realmente irritante no uso real antes de implementar — pode ser que o usuário prefira controle explícito. Se implementar, adicionar tentativa de conexão silenciosa em `main.py` durante `inicializar()`, após o boot sound, usando `pairing.conectar()`. Não falar nada se falhar (celular pode estar desligado).

---

### [MÉDIO] VAD (Voice Activity Detection) para o backend Vosk
**Problema**: o backend Vosk processa áudio continuamente sem filtrar períodos de silêncio ou ruído de fundo (motor, rádio, conversa). Isso aumenta falsos positivos e consumo de CPU no Rock Pi. O Whisper já tem VAD por energia; o Vosk não.

**O que fazer**: adaptar a lógica de VAD do `whisper_backend.py` para o loop Vosk em `speech_to_text.py` — usar `bandpass_filter()` + threshold de energia para só alimentar o `KaldiRecognizer` quando houver fala detectada.

---

### [GRANDE] Melhorar qualidade do TTS com piper-tts
**Problema**: `espeak-ng` é funcional mas soa robótico. `piper-tts` tem modelos PT-BR offline com qualidade significativamente superior.

**O que fazer**: instalar `piper-tts`, baixar um modelo PT-BR (ex: `pt_BR-faber-medium`), substituir a função `falar()` em `main.py` para usar piper em vez de pyttsx3+espeak-ng. Manter espeak-ng como fallback. Avaliar latência no Rock Pi 4B antes de adotar como padrão.

---

### [MÉDIO] Expor status do `BluetoothAudioController`
**Problema**: `audio.py` tem `BluetoothAudioController` completo (lista dispositivos BT, verifica loopback PipeWire, status de conexão) mas nunca é instanciado nem usado. Só `VolumeController` é usado.

**O que fazer**: decidir se esse status é útil — por exemplo, um comando `"carro status"` que fale o estado atual (celular conectado ou não, loopback ativo). Se não for necessário, remover a classe para reduzir código morto.

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

