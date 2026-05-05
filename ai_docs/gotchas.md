# Gotchas e Conhecimento Tácito

Armadilhas não documentadas, comportamentos contra-intuitivos e workarounds essenciais.

---

## Armadilhas Comuns

### Modelo Vosk não está no repositório
**Sintoma**: `O caminho do modelo não foi encontrado.` + `exit(1)` ao rodar.

**Causa**: `model-ptbr/` está no `.gitignore`. Em clone fresco, o modelo não existe.

**Solução**: Baixar de https://alphacephei.com/vosk/models e extrair como `./model-ptbr/`

Estrutura esperada:
```
model-ptbr/
├── am/
├── conf/
├── graph/
└── ...
```

---

### Taxa de amostragem do microfone causa reconhecimento ruim
**Sintoma**: Vosk retorna texto errado, palavras aleatórias, ou string vazia mesmo com fala clara.

**Causa mais comum**: Microfone opera em taxa muito diferente de 16kHz (ex: 192kHz), distorcendo o resampling.

**Diagnóstico**: Verificar no log de inicialização a taxa do microfone selecionado.
Para microfones a 44.1kHz ou 48kHz o resampling funciona bem (ratio limpo).
Para taxas muito altas (>96kHz), especificar microfone manualmente via `AUDIO_DEVICE=N`.

---

### `req.txt` não segue o nome padrão do pip
**Sintoma**: `pip install -r requirements.txt` falha com arquivo não encontrado.

**Causa**: O arquivo se chama `req.txt`. Candidato a renomear para `requirements.txt`.

**Solução**: `pip install -r req.txt`

---

### Buffer overflow do microfone é ignorado silenciosamente
**Sintoma**: Comandos ocasionalmente não detectados mesmo com fala clara.

**Causa**: `stream.read(CHUNK, exception_on_overflow=False)` descarta chunks se o sistema estiver lento.
Em hardware lento (Rock Pi 4B com modelo grande), o início de uma frase — incluindo a wake word — pode ser descartado.

**Localização**: `speech_to_text.py:92`

---

## Comportamentos Contra-Intuitivos

### `engine.runAndWait()` é quem realmente gera o arquivo WAV
`save_to_file()` apenas enfileira a operação. `runAndWait()` processa a fila e **gera** o arquivo.
O arquivo só existe após `runAndWait()` retornar. Não tentar reproduzir `output.wav` antes disso.

**Localização**: `main.py:16-19`

---

### Vosk aceita parâmetros inválidos sem erro
`{"beam": 15, "max-active": 10000}` são aceitos silenciosamente mesmo se incorretos.
- `beam: 15` — maior que o padrão; aumenta precisão às custas de latência (necessário no ambiente ruidoso do carro)
- `max-active: 10000` — aumentar muito pode causar OOM no Rock Pi 4B (4GB RAM)

---

### Bandpass no Whisper é aplicado APENAS ao cálculo de energia, não ao modelo
O `bandpass_filter()` (300–3400Hz) serve para isolar a voz humana do ruído de música ao calcular a energia do VAD.
**Mas o áudio enviado ao Whisper para transcrição é o raw resampled sem bandpass** — Whisper performa melhor sem o filtro.

```
chunk raw → resample_poly → bandpass → mean(abs) → VAD decision
chunk raw → resample_poly →                       → Whisper.transcribe()
```

Se aplicar bandpass no input do Whisper, a qualidade de transcrição cai. Não "simplificar" isso.

**Localização**: `whisper_backend.py:116-118`

---

### Arquitetura dois estágios: timeouts e comportamento
Ambos os backends (Vosk e Whisper) usam dois estágios com valores fixos:
- `DUCK_WAIT = 0.4s` — aguarda o duck efetivar antes de ouvir o comando (evita que o TTS do duck "vaze" para o STT)
- `COMMAND_TIMEOUT = 5.0s` — se o estágio 2 não receber fala em 5s, restaura volume e volta ao estágio 1

Se o timeout disparar sem comando, o `on_timeout_cb` é chamado (restaura duck) e o reconhecedor é resetado.

**Localização**: `speech_to_text.py:164-166` / `whisper_backend.py:35-36`

---

### `AcceptWaveform()` espera bytes, não numpy array
O áudio é convertido para numpy para o resampling, mas o Vosk exige bytes explicitamente.

```python
recognizer.AcceptWaveform(audio_data.tobytes())  # correto
recognizer.AcceptWaveform(audio_data)             # erro silencioso ou crash
```

**Localização**: `speech_to_text.py:102`

---

## Sequência de Inicialização (ordem obrigatória)

**STT**:
```
1. Verificar MODEL_PATH existe          → exit(1) se faltar
2. Carregar vosk.Model(...)             → lento (5-30s)
3. Inicializar pyaudio.PyAudio()
4. get_best_microphone()                → depende de (3); exit(1) se falhar
5. Abrir stream p.open(...)             → depende de (4); exit(1) se falhar
6. Criar KaldiRecognizer(model, 16000)  → depende de (2)
7. Loop while True                      → depende de (5) e (6)
```

---

## Configurações Não-Óbvias

**`CHUNK = 4096`** (`speech_to_text.py:37`): Chunks menores fragmentam fonemas e reduzem a precisão do Vosk.
4096 amostras @ 16kHz = ~256ms de áudio — balanço entre latência e precisão.
Não reduzir sem testar o impacto no reconhecimento.

**`beam: 15`** (`speech_to_text.py:32`): Acima do padrão do Vosk. Aumenta precisão no ambiente ruidoso do carro.

---

## Débitos Técnicos Ativos

- `req.txt` deveria ser `requirements.txt` (convenção pip)
- TTS com `espeak-ng` é funcional mas robótico — `piper-tts` (offline, modelos PT-BR) seria melhor no futuro
- Sem testes automatizados — `remove_acentos()` e `verificar_palavra()` seriam fáceis de cobrir (funções puras)
- Sem VAD (Voice Activity Detection) — o sistema processa continuamente mesmo com ruído de motor; implementar VAD reduziria falsos positivos e carga de CPU

---

## Debugging de Reconhecimento

Se o STT não reconhece corretamente:
1. Verificar no log qual microfone foi selecionado e sua taxa
2. Adicionar `print(result)` após `recognizer.Result()` para ver o JSON completo (há um `"DEBUG: Resultados do modelo:"` já no código)
3. Testar com fala mais devagar e articulada — o modelo small tem limitações
4. Verificar se `AUDIO_DEVICE=N` força o microfone correto

---

## Performance no Rock Pi 4B

- Vosk `small` (~30MB): ~0.5s de latência, precisão menor — útil se Whisper for lento demais
- Whisper `small` (~460MB): ~2-4s, alta precisão — padrão atual
- Whisper `medium`/`large`: 5-25s — inviável para uso em tempo real
- Ollama `llama3.2:3b`: ~1-3 tokens/s CPU-only no RK3399
- Vosk `large` (~1.5GB): pode ser lento e causar OOM com RAM de 4GB
- Vosk é lento para carregar (5-30s) — planejar indicador de "inicializando" no produto final
