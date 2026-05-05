# Gotchas e Conhecimento Tácito

Armadilhas não documentadas, comportamentos contra-intuitivos e workarounds essenciais.

---

## Armadilhas Comuns

### Taxa de amostragem do microfone causa reconhecimento ruim
**Sintoma**: Whisper retorna texto errado, palavras aleatórias, ou string vazia mesmo com fala clara.

**Causa mais comum**: Microfone opera em taxa muito diferente de 16kHz (ex: 192kHz), distorcendo o resampling.

**Diagnóstico**: Verificar no log de inicialização a taxa do microfone selecionado.
Para microfones a 44.1kHz ou 48kHz o resampling funciona bem (ratio limpo).
Para taxas muito altas (>96kHz), especificar microfone manualmente via `AUDIO_DEVICE=N`.

---

### `req.txt` não segue o nome padrão do pip
**Sintoma**: `pip install -r requirements.txt` falha com arquivo não encontrado.

**Causa**: O arquivo se chama `req.txt`.

**Solução**: `pip install -r req.txt`

---

### Buffer overflow do microfone é ignorado silenciosamente
**Sintoma**: Comandos ocasionalmente não detectados mesmo com fala clara.

**Causa**: `stream.read(CHUNK, exception_on_overflow=False)` descarta chunks se o sistema estiver lento.
Em hardware lento (Rock Pi 4B), o início de uma frase — incluindo a wake word — pode ser descartado.

**Localização**: `whisper_backend.py`

---

## Comportamentos Contra-Intuitivos

### `engine.runAndWait()` é quem realmente gera o arquivo WAV
`save_to_file()` apenas enfileira a operação. `runAndWait()` processa a fila e **gera** o arquivo.
O arquivo só existe após `runAndWait()` retornar. Não tentar reproduzir `output.wav` antes disso.

**Localização**: `main.py`

---

### Bandpass no Whisper é aplicado APENAS ao cálculo de energia, não ao modelo
O `bandpass_filter()` (300–3400Hz) serve para isolar a voz humana do ruído de música ao calcular a energia do VAD.
**Mas o áudio enviado ao Whisper para transcrição não passa por bandpass** — Whisper performa melhor sem o filtro.
O que SIM é aplicado antes do Whisper é o `pre_emphasis_filter()` (coef=0.97) — este realça consoantes/fricativas e melhora precisão.

```
chunk raw → resample_poly → bandpass → mean(abs)    → VAD decision
chunk raw → resample_poly → pre_emphasis_filter      → Whisper.transcribe()
```

Se aplicar bandpass no input do Whisper, a qualidade de transcrição cai. Não "simplificar" isso.

**Localização**: `whisper_backend.py`

---

### Arquitetura dois estágios: timeouts e comportamento
- `DUCK_WAIT = 0.4s` — aguarda o duck efetivar antes de ouvir o comando (evita que o TTS do duck "vaze" para o STT)
- `COMMAND_TIMEOUT = 5.0s` — se o estágio 2 não receber fala em 5s, restaura volume e volta ao estágio 1

Se o timeout disparar sem comando, o `on_timeout_cb` é chamado (restaura duck) e o buffer de fala é resetado.

**Localização**: `whisper_backend.py`

---

## Sequência de Inicialização (ordem obrigatória)

**STT (Whisper)**:
```
1. Carregar WhisperModel(...)           → lento na primeira vez (download do modelo)
2. Inicializar pyaudio.PyAudio()
3. get_best_microphone()                → depende de (2); exit(1) se falhar
4. Abrir stream p.open(...)             → depende de (3); exit(1) se falhar
5. Loop while True                      → depende de (1) e (4)
```

---

## Configurações Não-Óbvias

**`CHUNK = 1024`** (`whisper_backend.py`): Chunks pequenos permitem VAD responsivo.
O Whisper acumula chunks no `speech_buffer` até detectar silêncio — o tamanho do chunk afeta a granularidade do VAD, não a qualidade da transcrição.

**`initial_prompt`** (`whisper_backend.py`): Vocabulário real do sistema injetado em cada transcrição.
Enviesa o modelo para os comandos conhecidos, reduzindo erros fonéticos. Não remover ou esvaziar.

**`pre_emphasis_filter` coef=0.97**: Valor clássico para pré-ênfase de fala. Valores menores (0.9) realçam menos; valores maiores (0.99) podem distorcer. Não alterar sem testar.

---

## Débitos Técnicos Ativos

- `req.txt` deveria ser `requirements.txt` (convenção pip)
- TTS com `espeak-ng` é funcional mas robótico — `piper-tts` (offline, modelos PT-BR) seria melhor no futuro
- Sem testes automatizados — `remove_acentos()` e `verificar_palavra()` seriam fáceis de cobrir (funções puras)

---

## Debugging de Reconhecimento

Se o STT não reconhece corretamente:
1. Verificar no log qual microfone foi selecionado e sua taxa
2. Rodar com `--debug` para ver tudo que o Whisper transcreve em tempo real
3. Testar com fala mais devagar e articulada — o modelo `small` tem limitações
4. Verificar se `AUDIO_DEVICE=N` força o microfone correto
5. Considerar `WHISPER_MODEL=medium` para maior precisão (latência ~5-8s no Rock Pi)

---

## Performance no Rock Pi 4B

- Whisper `small` (~460MB): ~2-4s, alta precisão — padrão atual
- Whisper `medium` (~1.5GB): ~5-8s — melhor precisão, latência maior
- Whisper `large-v3`: ~15-25s — inviável para uso em tempo real
- Ollama `llama3.2:3b`: ~1-3 tokens/s CPU-only no RK3399
