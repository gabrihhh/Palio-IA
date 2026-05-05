# Regras de Negócio

> Estas regras quebram o sistema silenciosamente se violadas. Verificar antes de implementar qualquer coisa.

## Regras Críticas

**1. Vosk exige 16kHz mono** — `speech_to_text.py:36,79-84`
- Qualquer outra taxa gera transcrição errada ou silêncio, sem lançar erro explícito
- O microfone é detectado na taxa nativa e resampleado automaticamente com `resample_poly`
- `TARGET_RATE = 16000` é a única taxa aceita

**2. Wake word obrigatória** — `speech_to_text.py:238` (Vosk) / `whisper_backend.py:158` (Whisper)
- Nenhuma ação executa sem `"carro"` na frase reconhecida — sem exceções
- Verificada por substring exata (remove acentos + lowercase) + fuzzy match 75% como fallback
- A wake word é detectada no **estágio 1** (utterance separado); o comando é capturado no **estágio 2** (utterance seguinte)
- Se o STT não reconhecer "carro" corretamente, zero comandos funcionam

**3. Comparação sempre normalizada** — `speech_to_text.py:9-21`
- Acentos e maiúsculas sempre ignorados em comparações de comando
- `"próxima"` == `"proxima"` == `"PROXIMA"` para fins de detecção
- `verificar_palavra()` centraliza essa lógica — sempre usar ela, nunca comparar string direto

**4. Modelo deve existir antes de inicializar** — `speech_to_text.py:26-29`
- Sem `model-ptbr/` → `exit(1)` imediato com mensagem clara
- O modelo nunca está no git (`.gitignore`) — cada instalação precisa baixar manualmente

**5. Processamento apenas de utterances completos** — Vosk: `speech_to_text.py:225` | Whisper: `whisper_backend.py:142-149`
- **Vosk**: `AcceptWaveform() == True` = resultado final → processa; resultados parciais ignorados
- **Whisper**: VAD por energia detecta início/fim de fala por silêncio (`WHISPER_SILENCE_DURATION=0.8s`); transcreve o utterance completo de uma vez
- Ambos evitam processar fala incompleta; trade-off: latência aumenta (aguarda pausa natural)

**6. TTS síncrono com parâmetros fixos** — `main.py:10-19`
- Taxa 160 wpm, volume 1.0 — fixos por design (ruído de carro exige inteligibilidade máxima)
- `save_to_file()` apenas enfileira; `runAndWait()` é quem realmente gera o arquivo WAV
- Não ler nem reproduzir `output.wav` antes de `runAndWait()` completar

## Hierarquia de Detecção de Intenção

```
Vosk/Whisper (resultado final)
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
| `model-ptbr/` existe | `speech_to_text.py:26-29` | `exit(1)` |
| Microfone disponível | `speech_to_text.py:60-61` | `exit(1)` |
| Stream de áudio abre | `speech_to_text.py:67-76` | `exit(1)` |
| Texto reconhecido não-vazio | `speech_to_text.py:93-95` | `continue` (ignora frame) |
| Buffer overflow | `speech_to_text.py:92` | ignorado silenciosamente |

## Restrições de Domínio

- **Stateless**: nenhum estado mantido entre comandos; cada frase processada de forma independente
- **PT-BR exclusivo**: modelo STT, wake word, comandos, TTS — tudo em português
- **Sem internet**: toda lógica funciona offline; Ollama offline desativa apenas o LLM
