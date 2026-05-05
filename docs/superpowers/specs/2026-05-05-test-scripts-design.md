# Design: Scripts de Teste Isolados (`test/`)

**Data:** 2026-05-05
**Status:** Aprovado (pós-review)

---

## Problema

Não há forma de testar componentes individuais (STT, TTS, LLM) sem rodar o sistema completo com wake word, duck de áudio e Bluetooth. Isso dificulta calibração, validação de voz e testes de integração com o Ollama antes de ir ao carro.

---

## Decisão

Criar três scripts independentes em `test/`, cada um testando um componente isolado. Sem wake word, sem duck de áudio, sem Bluetooth. Cada script importa dos módulos existentes — sem duplicação de código.

---

## Estrutura

```
test/
├── stt.py     # calibração STT — transcrição contínua em tempo real
├── tts.py     # teste de voz — fala um arquivo .txt ou texto inline
└── chat.py    # teste Ollama — conversa direta STT → LLM → TTS
```

**Todos os scripts são invocados da raiz do projeto:**
```bash
python test/stt.py
python test/tts.py arquivo.txt
python test/chat.py
```

---

## Mudança em `modules/stt/whisper_backend.py`

Adicionar parâmetro `bypass_wake_word: bool = False` a `iniciar_loop_stt()`.

**Assinatura atualizada:**
```python
def iniciar_loop_stt(
    on_comando: Callable[[str], None],
    on_wake_word_cb: Optional[Callable[[], None]] = None,
    on_timeout_cb: Optional[Callable[[], None]] = None,
    wake_word: str = "carro",
    debug: bool = False,
    bypass_wake_word: bool = False,   # NOVO
) -> None:
```

**Diff exato no loop** (bloco `if text:`, linha ~165 do arquivo atual):

```python
# ANTES:
if text:
    if stage == 1:
        if debug:
            print(f"[STT] {text}", flush=True)
        ...
        if verificar_palavra(text, wake_word):
            ...
            stage = 2
    elif stage == 2:
        on_comando(text)
        stage = 1

# DEPOIS:
if text:
    if bypass_wake_word:
        # Modo bypass: todo utterance vai direto para on_comando, sem estágios
        if debug:
            print(f"[STT] {text}", flush=True)
        on_comando(text)
    elif stage == 1:
        if debug:
            print(f"[STT] {text}", flush=True)
        ...
        if verificar_palavra(text, wake_word):
            ...
            stage = 2
    elif stage == 2:
        on_comando(text)
        stage = 1
```

`on_wake_word_cb` e `on_timeout_cb` são `Optional` e já tratados com `if on_wake_word_cb:` no código existente — passar `None` é seguro.

---

## Padrão comum dos scripts

Cada script começa com:
```python
import os, sys
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
```

Isso garante que imports como `from modules.stt.whisper_backend import iniciar_loop_stt` e `from speech_to_text import ...` funcionem independente do CWD ao invocar o script.

---

## Scripts

### `test/stt.py` — Calibração STT

**Invocação:**
```bash
python test/stt.py
```

**Comportamento:**
- Inicializa Whisper com as mesmas configs do sistema (`WHISPER_MODEL`, `WHISPER_SILENCE_THRESHOLD`, `WHISPER_SILENCE_DURATION`)
- Loop contínuo via `iniciar_loop_stt(..., bypass_wake_word=True)`
- `on_comando` imprime timestamp + texto transcrito
- Ctrl+C para sair (tratado sem stack trace)

**Saída:**
```
[STT] Iniciando calibração. Fale algo. Ctrl+C para sair.
[14:32:01] "próxima música"
[14:32:05] "carro que música é essa"
```

**Uso:** ajustar `WHISPER_SILENCE_THRESHOLD`, verificar precisão PT-BR, confirmar que "carro" é reconhecida.

---

### `test/tts.py` — Teste de Voz

**Invocação:**
```bash
python test/tts.py arquivo.txt        # lê e fala o arquivo
python test/tts.py "texto de teste"   # fala texto inline
```

**Comportamento:**
- Resolve `PIPER_MODEL` relativo ao `_PROJECT_ROOT` (não ao diretório `test/`)
- Carrega `PiperVoice`, gera WAV em `tempfile`, reproduz via sounddevice
- Encerra após falar

**Saída:**
```
[TTS] Modelo carregado: /.../.../models/pt_BR-faber-medium.onnx
[TTS] Falando: "Olá, eu sou o Palio..."
[TTS] Concluído.
```

**Path resolution:** `PIPER_MODEL = os.getenv('PIPER_MODEL', os.path.join(_PROJECT_ROOT, 'models', 'pt_BR-faber-medium.onnx'))`

---

### `test/chat.py` — Teste Ollama

**Invocação:**
```bash
python test/chat.py
```

**Comportamento:**
- Inicializa STT (Whisper), TTS (piper) e LLM (`OllamaClient`)
- Loop via `iniciar_loop_stt(..., bypass_wake_word=True)`
- `on_comando`: texto → `OllamaClient.chat()` → `_limpar_markdown()` → `falar()`
- Usa persona do Palio e `data/brain.md` normalmente
- Ctrl+C para sair

**Saída:**
```
[CHAT] STT, TTS e LLM prontos. Fale algo. Ctrl+C para sair.
[14:35:12] Você: "qual é a previsão do tempo?"
[14:35:14] Palio: "Sou um carro, não um meteorologista."
```

**`_limpar_markdown()`:** inlinada no `chat.py` (7 linhas) — não importa `main.py` para evitar side-effects da inicialização (`autoconnect_boot`, `create_controller`, etc.)

**`falar()`:** closure local idêntica à de `main.py:120-135`, capturando `voice = PiperVoice.load(...)`:
```python
def falar(texto: str) -> None:
    fd, tmp_wav = tempfile.mkstemp(suffix='.wav', prefix='palio_tts_')
    os.close(fd)
    try:
        with wave.open(tmp_wav, 'wb') as wav_file:
            voice.synthesize_wav(texto, wav_file)
        data, samplerate = sf.read(tmp_wav)
        sd.play(data, samplerate)
        sd.wait()
    except Exception as e:
        print(f"[CHAT] Erro TTS: {e}", flush=True)
    finally:
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)
```

---

## O que NÃO está incluso

- Duck de áudio — desnecessário fora do carro
- Wake word — propósito dos scripts é testar sem fricção
- Bluetooth — fora do escopo
- Framework de testes (pytest) — scripts de uso manual

---

## Atualização no CLAUDE.md

Adicionar seção "Scripts de Teste" documentando os três scripts, seus propósitos e como invocar cada um. Deixar claro que são ferramentas de desenvolvimento, não parte do sistema embarcado.
