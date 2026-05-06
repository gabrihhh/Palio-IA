# Regras de Negócio

> Estas regras quebram o sistema silenciosamente se violadas. Verificar antes de implementar qualquer coisa.

## Regras Críticas

**1. STT exige 16kHz mono** — `whisper_backend.py`
- Qualquer outra taxa gera transcrição errada ou silêncio, sem lançar erro explícito
- O microfone é detectado na taxa nativa e resampleado automaticamente com `resample_poly`
- `TARGET_RATE = 16000` é a única taxa aceita

**2. Wake word obrigatória** — `whisper_backend.py:158`
- Nenhuma ação executa sem `"carro"` na frase reconhecida — sem exceções
- Verificada por substring exata (remove acentos + lowercase) + fuzzy match 75% como fallback
- A wake word é detectada no **estágio 1** (utterance separado); o comando é capturado no **estágio 2** (utterance seguinte)
- Se o STT não reconhecer "carro" corretamente, zero comandos funcionam

**3. Comparação sempre normalizada** — `speech_to_text.py`
- Acentos e maiúsculas sempre ignorados em comparações de comando
- `"próxima"` == `"proxima"` == `"PROXIMA"` para fins de detecção
- `verificar_palavra()` centraliza essa lógica — sempre usar ela, nunca comparar string direto

**4. Processamento apenas de utterances completos** — `whisper_backend.py:142-149`
- VAD por energia detecta início/fim de fala por silêncio (`WHISPER_SILENCE_DURATION=0.8s`)
- Transcreve o utterance completo de uma vez — evita processar fala incompleta
- Trade-off: latência aumenta (aguarda pausa natural antes de transcrever)

**5. TTS síncrono** — `main.py`
- `voice.synthesize_wav()` gera WAV em arquivo temporário (`/tmp/palio_tts_*.wav`) e reproduz de forma síncrona via `sounddevice`
- O modelo piper é carregado uma vez no boot (`inicializar()`) e reutilizado em todas as chamadas — não reinicializar por chamada

## Hierarquia de Detecção de Intenção

```
Whisper (resultado final)
  └── Contém wake word "carro" (substring ou fuzzy ≥75%)?
      ├── NÃO → ignora completamente
      └── SIM → Dispatcher:
          ├── Modo pareamento ativo? → PairingManager
          ├── Comando de pareamento detectado? → PairingManager
          ├── Comando de música mapeado? → BluetoothMusicController
          └── Nenhum dos anteriores → OllamaClient (LLM)
```

## Validações em Runtime

| Verificação | Localização | Falha → |
|---|---|---|
| Microfone disponível | `speech_to_text.py` | `exit(1)` |
| Stream de áudio abre | `whisper_backend.py` | `exit(1)` |
| Texto reconhecido não-vazio | `whisper_backend.py` | `continue` (ignora frame) |
| Buffer overflow | `whisper_backend.py` | ignorado silenciosamente |

## Regras de Comportamento do LLM (persona.py)

**6. Não inventar especificações técnicas do carro** — `persona.py:43`
- Ano, motor, cor, versão — nunca mencionar se não foram explicitamente informados pelo dono
- Se não souber, não menciona; não tenta inferir ou "adivinhar"

**7. Identidade via brain.md** — `persona.py:44`
- Quando perguntado "quem você é", a resposta deve usar o que está registrado em `data/brain.md`
- Não há identidade hardcoded além do nome "Palio"; detalhes pessoais vêm da memória persistente

## Restrições de Domínio

- **Stateless**: nenhum estado mantido entre comandos; cada frase processada de forma independente
- **PT-BR exclusivo**: modelo STT, wake word, comandos, TTS — tudo em português
- **Sem internet**: toda lógica funciona offline; Ollama offline desativa apenas o LLM
