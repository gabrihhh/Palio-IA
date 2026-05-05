# Design: Upgrade TTS pyttsx3+espeak-ng → piper-tts

**Data:** 2026-05-05
**Status:** Aprovado (pós-review)

---

## Problema

O TTS atual (`pyttsx3` + `espeak-ng`) usa síntese formântica — funcional, mas notavelmente robótico. Num assistente de voz usado diariamente no carro, a qualidade da voz impacta diretamente a experiência. O `piper-tts` (Open Home Foundation) usa redes neurais VITS com modelos PT-BR treinados em voz humana real, produzindo fala natural com entonação e ritmo adequados.

---

## Decisão

Substituição **completa** de `pyttsx3` por `piper-tts`. Sem fallback. O projeto é 100% offline — toda a instalação é empacotada previamente no notebook e transferida via pendrive para o Rock Pi.

**Pacote:** `OHF-Voice/piper1-gpl` (repositório oficial; `rhasspy/piper` foi arquivado em out/2025).
**Instalação:** wheel Python ARM64 — único formato de distribuição do novo projeto.
**Modelo:** `pt_BR-faber-medium` (~63 MB ONNX).

---

## O que muda no código

### Único arquivo alterado: `main.py`

**Remoção:**
- Import `pyttsx3`
- Função `falar()` do escopo do módulo (substituída por closure dentro de `inicializar()`)

**Adição:**
- Imports: `wave`, `tempfile`, `from piper import PiperVoice`
- Constantes no topo de `main.py`:
  ```python
  _BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
  PIPER_MODEL = os.getenv('PIPER_MODEL', os.path.join(_BASE_DIR, 'models', 'pt_BR-faber-medium.onnx'))
  ```
- `PiperVoice.load(PIPER_MODEL)` chamado **uma vez** em `inicializar()`
- `falar()` como **closure** dentro de `inicializar()` que captura `voice`
- `inicializar()` passa a retornar `(dispatcher, duck, volume, falar)` — 4 valores
- `criar_handler()` recebe `falar` como parâmetro explícito

### Por que closure e não parâmetro na assinatura de `falar`

`falar` é passada como `falar_cb: Callable[[str], None]` ao `Dispatcher` e ao `PairingManager`. Adicionar `voice` como parâmetro quebraria essa interface em duas camadas. A closure captura `voice` do escopo de `inicializar()` sem alterar nenhuma outra camada.

### Por que `inicializar()` retorna `falar`

`criar_handler()` referencia `falar` diretamente (para as chamadas internas em `on_comando`). Como `falar` agora é uma closure local de `inicializar()`, não existe mais no escopo do módulo. A solução é retorná-la de `inicializar()` e passá-la explicitamente para `criar_handler()`.

### Arquivo WAV temporário com `tempfile`

Em vez de `'output.wav'` (path relativo ao cwd — frágil em systemd), usa-se `tempfile.mkstemp()`:
- Cria arquivo temporário com nome único a cada chamada (`/tmp/palio_tts_XXXXXX.wav`)
- Resolve dependência de cwd (systemd não usa o diretório do projeto como cwd)
- Elimina race condition: `PairingManager` roda numa thread separada e pode chamar `falar()` simultaneamente ao loop principal; nomes únicos evitam colisão de arquivo

### Novo fluxo de `falar()` (closure)

```
texto
  → tempfile.mkstemp() → tmp_wav (path único)
  → wave.open(tmp_wav, 'wb') → voice.synthesize_wav(texto, wav_file)
  → sf.read(tmp_wav) → sd.play() + sd.wait()
  → os.remove(tmp_wav)
```

### Otimização: carregamento único do modelo

Hoje `pyttsx3.init()` é chamado a cada `falar()`. Com piper, o modelo ONNX (63 MB) é carregado **uma vez** no boot via `PiperVoice.load()` e reutilizado em todas as chamadas.

### API exata verificada (piper-tts 1.4.2)

```python
# src/piper/voice.py
def synthesize_wav(
    self,
    text: str,
    wav_file: wave.Wave_write,
    syn_config: Optional[SynthesisConfig] = None,
    set_wav_format: bool = True,         # configura sample rate/channels/width automaticamente
    include_alignments: bool = False,
) -> Optional[list[PhonemeAlignment]]
```

Chamada mínima: `voice.synthesize_wav(texto, wav_file)` — `set_wav_format=True` configura o WAV automaticamente.

---

## Dependências

### `req.txt`

| Ação | Pacote |
|---|---|
| Remover | `pyttsx3==2.98` |
| Adicionar | `piper-tts` |
| Adicionar | `onnxruntime` |

`pathvalidate` é dependência do piper-tts e instalada automaticamente — não precisa declarar separado.
`numpy` já está em `req.txt` — não duplicar.

---

## Empacotamento offline (executado no notebook com internet)

### Wheels a baixar

| Arquivo | Fonte | Obs |
|---|---|---|
| `piper_tts-1.4.2-cp39-abi3-manylinux_2_17_aarch64*.whl` | GitHub Releases `OHF-Voice/piper1-gpl` v1.4.2 | download manual |
| wheel ARM64 do `onnxruntime>=1,<2` | PyPI | ver comando abaixo |

**Comando para baixar onnxruntime ARM64 offline (no notebook x86):**
```bash
pip download \
  --platform manylinux_2_17_aarch64 \
  --python-version 311 \
  --only-binary=:all: \
  "onnxruntime>=1,<2"
```
> Ajustar `--python-version` para a versão Python do Rock Pi (verificar com `python3 --version`).

`pathvalidate` é pure-Python — será baixada automaticamente pelo pip ao instalar piper-tts. Não precisa de wheel específico de plataforma.

### Modelo

| Arquivo | Fonte | Tamanho |
|---|---|---|
| `pt_BR-faber-medium.onnx` | Hugging Face `rhasspy/piper-voices` (`pt/pt_BR/faber/medium/`) | ~63 MB |
| `pt_BR-faber-medium.onnx.json` | Hugging Face `rhasspy/piper-voices` (`pt/pt_BR/faber/medium/`) | ~5 KB |

### Estrutura no projeto após instalação

```
Palio-IA/
├── models/
│   ├── pt_BR-faber-medium.onnx
│   └── pt_BR-faber-medium.onnx.json
├── main.py
└── req.txt
```

### Instalação no Rock Pi (sem internet)

```bash
# 1. Instalar wheels (executar na pasta onde estão os .whl)
pip install --no-index piper_tts-*.whl onnxruntime-*.whl

# 2. pathvalidate e demais deps pure-Python virão junto com piper_tts
#    Se pip reclamar de deps ausentes offline, baixar também:
#    pip download pathvalidate  (no notebook, sem flag de plataforma)
```

---

## Estrutura final relevante de `main.py`

```python
# Topo do arquivo
import wave
import tempfile
from piper import PiperVoice

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
PIPER_MODEL = os.getenv('PIPER_MODEL', os.path.join(_BASE_DIR, 'models', 'pt_BR-faber-medium.onnx'))


def inicializar() -> tuple[Dispatcher, object, object, Callable]:
    ...
    voice = PiperVoice.load(PIPER_MODEL)
    logger.info("TTS: modelo piper carregado.")

    def falar(texto: str) -> None:
        logger.info("TTS: '%s'", texto)
        fd, tmp_wav = tempfile.mkstemp(suffix='.wav', prefix='palio_tts_')
        os.close(fd)
        try:
            with wave.open(tmp_wav, 'wb') as wav_file:
                voice.synthesize_wav(texto, wav_file)
            data, samplerate = sf.read(tmp_wav)
            sd.play(data, samplerate)
            sd.wait()
        except Exception as e:
            logger.error("Erro ao reproduzir TTS: %s", e)
        finally:
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)

    dispatcher = Dispatcher(bluetooth=bt, llm=llm, falar_cb=falar, volume=volume)
    return dispatcher, duck, volume, falar


def criar_handler(dispatcher, duck, volume, falar):  # falar agora é parâmetro
    def on_wake_word(): duck.on_wake_word()
    def on_timeout():
        logger.info("Timeout: restaurando volume.")
        duck.on_done()
    def on_comando(texto):
        ...
        falar("Oi. Pode falar.")   # usa o falar recebido como parâmetro
        ...
        falar(_limpar_markdown(resposta))
        ...


# __main__
dispatcher, duck, volume, falar = inicializar()
on_comando, on_wake_word, on_timeout = criar_handler(dispatcher, duck, volume, falar)
```

---

## O que NÃO muda

- `_limpar_markdown()` — idêntica
- `tocar_boot()` — idêntica
- `Dispatcher`, `PairingManager`, `BluetoothMusicController`, `OllamaClient` — zero alterações
- Fluxo de duck de áudio — idêntico
- `modules/` inteiros — sem toque

---

## Configuração via env var

```bash
# Override do modelo (ex: para testar outro modelo PT-BR)
PIPER_MODEL=/caminho/absoluto/pt_BR-cadu-medium.onnx python main.py
```

---

## Riscos e mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Wheel ARM64 incompatível com glibc do Debian 12 | Baixa — manylinux_2_17 ≤ glibc do Bookworm | Testar `python -c "from piper import PiperVoice"` antes de ir ao carro |
| Latência do modelo no Rock Pi 4B | Média — esperado 0.8-1.5s | Aceitável para assistente de carro; testar na prática |
| Modelo não sintetiza PT-BR bem | Baixa — faber-medium testado pela comunidade | Trocar modelo via `PIPER_MODEL` sem alterar código |
| `onnxruntime` wheel versão errada | Baixa se `--python-version` correto | Verificar versão Python do Rock Pi antes de baixar |
