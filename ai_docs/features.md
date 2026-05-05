# Funcionalidades

## Funcionalidades Implementadas

### Reconhecimento de Voz Offline (STT)
**Descrição**: Captura áudio contínuo do microfone e converte fala em texto localmente via faster-whisper, sem depender de internet.

**Modelos disponíveis** (via `WHISPER_MODEL`):

| Modelo | Precisão | Latência (notebook) | Latência (Rock Pi 4B) |
|---|---|---|---|
| `small` (padrão, ~460MB) | Alta | ~1s | ~2-4s |
| `medium` (~1.5GB) | Muito alta | ~2s | ~5-8s |
| `large-v3` (~3GB) | Máxima | ~4s | ~15-25s |

**Componentes**:
- `speech_to_text.py` — utilitários de áudio compartilhados (resample, bandpass, pré-ênfase, fuzzy match, seleção de mic)
- `modules/stt/whisper_backend.py` — loop STT com VAD por energia
- `PyAudio` — captura do microfone
- `scipy.signal.resample_poly` — resampling para 16kHz (ratio limpo 3:1 a 48kHz)

**Arquitetura dois estágios**:
- **Estágio 1** — sempre ouvindo, procura apenas a wake word
- **Estágio 2** — após wake word, captura o próximo utterance como comando; timeout 5s
- `DUCK_WAIT = 0.4s` entre wake word e início do estágio 2

**Filtro passa-banda** (`bandpass_filter()` em `speech_to_text.py:53-62`):
- Filtra áudio para faixa de voz humana (300–3400Hz)
- Reduz bleeding de música tocando no carro
- No Whisper: aplicado APENAS para cálculo de energia (VAD) — o áudio enviado ao modelo é raw resampled


**Fluxo Whisper** (`CHUNK=1024`):
1. Detecta o melhor microfone (respeita `AUDIO_DEVICE`), captura preferencial a 48kHz
2. Para cada chunk: resample → bandpass → calcula energia (VAD)
3. Quando energia > threshold: acumula chunks em `speech_buffer` (com pre-buffer de 0.3s)
4. Ao detectar silêncio (`WHISPER_SILENCE_DURATION=0.8s`): aplica `pre_emphasis_filter()` e transcreve com Whisper (sem bandpass, com pré-ênfase + `initial_prompt`)
5. Checa wake word com fuzzy matching (75%) → entra estágio 2

---

### Seleção de Microfone
**Descrição**: Itera por todos os dispositivos de áudio disponíveis e seleciona automaticamente o microfone cuja taxa nativa é mais próxima de 16kHz.

**Componentes Envolvidos**: `speech_to_text.py` — função `get_best_microphone()`

**Comportamento**:
- Se `AUDIO_DEVICE=N` estiver definido, usa o dispositivo N diretamente (override manual)
- Caso contrário, auto-seleção inteligente com prioridades:
  1. Descarta dispositivos Monitor (loopback de saída)
  2. Prefere hardware real sobre virtuais (`pulse`, `pipewire`, `default`, `sysdefault`)
  3. Dentro de cada grupo, escolhe pelo `defaultSampleRate` mais próximo de 16kHz
  4. Se só sobrarem virtuais, usa o melhor entre eles
- Se nenhum microfone encontrado, encerra com `exit(1)`

---

### Resampling de Áudio
**Descrição**: Converte áudio capturado na taxa nativa do microfone para 16kHz (taxa exigida pelo Whisper).

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

**Comportamento no boot**: `autoconnect_boot()` tenta conectar silenciosamente ao dispositivo salvo na inicialização. Ver seção [Auto-connect Bluetooth no Boot](#auto-connect-bluetooth-no-boot).

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

### Memória Persistente (brain.md)
**Descrição**: O LLM pode salvar informações sobre o dono entre sessões. O histórico de conversa some ao desligar o carro, mas o brain persiste em disco.

**Componentes Envolvidos**: `modules/llm/client.py`, `modules/llm/persona.py` (`MEMORY_INSTRUCTIONS`), `data/brain.md`

**Campos do brain.md**:
- `nome_dono` — primeiro nome do dono (uma linha)
- `notas` — lista livre de até 5 itens; ao atingir o limite, o mais antigo é descartado

**Mecanismo** — tag inline na resposta do LLM:
- `[MEMO: nome=Gabriel]` → salva nome do dono
- `[MEMO: nota=Gosta de rock]` → adiciona nota
- O `OllamaClient.chat()` extrai as tags antes de passar o texto para o TTS — elas são invisíveis para o usuário
- O LLM aprende quando usar as tags via `MEMORY_INSTRUCTIONS` no system prompt

**Fluxo no boot**:
1. `OllamaClient.__init__()` chama `_build_system_prompt()`
2. `_load_brain()` lê `data/brain.md`
3. Prompt composto = `SYSTEM_PROMPT` + `MEMORY_INSTRUCTIONS` + conteúdo do brain

**Regras de uso (instruídas ao LLM)**:
- Só salva nome quando o dono se apresentar ou confirmar
- Notas: apenas o que muda a forma de conversar (estilo, preferências, fatos marcantes)
- Nunca menciona a tag em voz alta

---

### Auto-connect Bluetooth no Boot
**Descrição**: Ao inicializar, o sistema tenta conectar silenciosamente ao dispositivo salvo em `data/devices.json`. Não fala nada independente do resultado — falhar é situação normal (celular desligado ou fora de alcance).

**Componentes Envolvidos**: `modules/bluetooth/pairing.py` → `autoconnect_boot()`, `main.py` → `inicializar()`

**Comportamento**:
- Sem dispositivo salvo → retorna sem fazer nada
- Com dispositivo salvo → tenta `_bt_connect(mac)` e loga o resultado
- Sucesso → atualiza `last_connected` em `devices.json`
- `"carro conectar"` continua funcionando como fallback manual

---

### Melhorias de Precisão STT (Whisper)
**Descrição**: Duas melhorias aplicadas ao pipeline Whisper para reduzir erros fonéticos (ex: "carro" → "karo", "mão" → "são").

**Componentes Envolvidos**: `speech_to_text.py` → `pre_emphasis_filter()`, `modules/stt/whisper_backend.py`

**Melhorias**:
- **Filtro de pré-ênfase** (`pre_emphasis_filter()`, coef=0.97): realça consoantes e fricativas antes da transcrição, tornando fonemas similares mais distinguíveis
- **`initial_prompt`**: vocabulário real do sistema injetado em toda chamada `model.transcribe()` — enviesa o modelo para os comandos conhecidos, reduzindo erros de transcrição fora do vocabulário esperado

---

### Seleção Inteligente de Microfone
**Descrição**: `get_best_microphone()` prioriza hardware USB real sobre dispositivos virtuais do PipeWire, evitando seleção acidental de loopbacks ou dispositivos genéricos.

**Componentes Envolvidos**: `speech_to_text.py` → `get_best_microphone()`

**Prioridades**:
1. `AUDIO_DEVICE=N` (override manual)
2. Descarta `Monitor` (loopback de saída)
3. Prefere hardware sobre virtuais (`pulse`, `pipewire`, `default`, `sysdefault`)
4. Desempate por taxa mais próxima de 16kHz

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

---

### Síntese de Voz Neural (TTS com piper-tts)
**Descrição**: Substituição completa de `pyttsx3+espeak-ng` por `piper-tts` (OHF-Voice/piper1-gpl), usando modelo ONNX neural PT-BR para voz natural.

**Componentes Envolvidos**: `main.py` — closure `falar()` dentro de `inicializar()`

**Modelo**: `pt_BR-faber-medium` (~63 MB ONNX), carregado uma vez no boot via `PiperVoice.load()`

**Fluxo**:
1. `PiperVoice.load(PIPER_MODEL)` no boot — modelo fica em memória durante toda a sessão
2. A cada chamada `falar(texto)`: `voice.synthesize_wav()` gera WAV em arquivo temporário único (`/tmp/palio_tts_XXXXXX.wav`)
3. Reprodução via `sounddevice` + `soundfile` — idêntico ao anterior
4. Arquivo temporário removido após reprodução

**Configuração**:
- `PIPER_MODEL` env var — override do caminho do modelo (padrão: `models/pt_BR-faber-medium.onnx` relativo ao `main.py`)

**Instalação offline** (pendrive → Rock Pi):
- Wheel ARM64: `piper_tts-1.4.2-*-aarch64*.whl` (GitHub Releases `OHF-Voice/piper1-gpl`)
- `onnxruntime` wheel ARM64 (via `pip download --platform manylinux_2_17_aarch64`)
- Modelo: `pt_BR-faber-medium.onnx` + `.onnx.json` (Hugging Face `rhasspy/piper-voices`)

**Decisão arquitetural**: `falar()` é closure dentro de `inicializar()` — captura `voice` sem alterar a assinatura `Callable[[str], None]` usada como callback no `PairingManager` e `Dispatcher`.

---

## Funcionalidades Planejadas

*(nenhuma no momento)*

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
- Identificar qualquer comando de voz que o Whisper não esteja reconhecendo bem no ambiente real (ruído de carro, motor)
- Checar se o AudioDuck está com o percentual certo (20%) no ambiente real
- Limpar qualquer workaround ou TODO deixado durante o desenvolvimento inicial

