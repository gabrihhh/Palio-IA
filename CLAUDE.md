# Palio-IA — Quick Reference

## O que é
Assistente de voz embarcado num Fiat Palio. Roda no **Radxa ROCK 4B** (ARM64, Debian 12 Bookworm, CLI sem desktop). **100% offline.**

## Restrições Absolutas
> Violar qualquer uma dessas quebra o sistema silenciosamente.

- **100% offline** — zero dependência de internet; qualquer feature que exija rede está fora do escopo
- **Áudio: 16kHz mono** — Whisper exige esse formato; microfone é resampleado automaticamente via `resample_poly`
- **Wake word: `"carro"`** — sem ela, zero comandos executam; verificada por substring + fuzzy match (75%)
- **Idioma: PT-BR** — STT, wake word, comandos, logs e TTS tudo em português
- **Comparação normalizada** — acentos e case sempre ignorados em comparações de comandos (`verificar_palavra()`)

## Mapa de Módulos

| Arquivo | Responsabilidade | Status |
|---|---|---|
| `main.py` | Orquestrador + TTS (piper-tts+sounddevice) + loop principal | Funcional |
| `speech_to_text.py` | Utilitários de áudio: resample, bandpass, pré-ênfase, seleção de mic, fuzzy match | Funcional |
| `modules/stt/whisper_backend.py` | STT backend Whisper com VAD por energia (bandpass só para VAD; pré-ênfase + initial_prompt para o modelo) | Funcional |
| `modules/core/dispatcher.py` | Roteador: texto → [música \| pareamento \| LLM] | Funcional |
| `modules/bluetooth/music.py` | AVRCP: próxima, anterior, pausa, play, info da faixa | Funcional |
| `modules/bluetooth/pairing.py` | Pareamento BT por voz + `autoconnect_boot()` no boot, 1 device em `data/devices.json` | Funcional |
| `modules/bluetooth/audio_duck.py` | Duck volume → 20% na wake word, restaura após TTS | Funcional |
| `modules/bluetooth/audio.py` | Controle de volume por voz (1-10 = 10%-100%, +10%/-10%) | Funcional |
| `modules/llm/client.py` | Cliente Ollama — histórico multi-turno + memória persistente via `data/brain.md` | Funcional |
| `modules/llm/persona.py` | System prompt + `MEMORY_INSTRUCTIONS` (regras do brain.md para o LLM) | Funcional |

**Variáveis de ambiente:**

| Variável | Padrão | Descrição |
|---|---|---|
| `AUDIO_DEVICE` | auto | índice do microfone (listar com PyAudio) |
| `WHISPER_MODEL` | `small` | `small`, `medium`, `large-v3` |
| `WHISPER_SILENCE_THRESHOLD` | `400` | amplitude mínima para considerar fala |
| `WHISPER_SILENCE_DURATION` | `0.8` | segundos de silêncio para encerrar utterance |

## Fluxo Principal

```
Boot → dois bipes →
loop (2 estágios):
  Estágio 1 — sempre ouvindo:
    STT + bandpass + VAD → detecta wake word "carro" (fuzzy 75%) →
    chama on_wake_word_cb() → duck 20% → aguarda 0.4s (DUCK_WAIT) → vai para estágio 2

  Estágio 2 — ouvindo comando (timeout 5s):
    STT captura próximo utterance → dispatcher:
      [música AVRCP | pareamento BT | volume | Ollama LLM]
    → TTS fala → restaura volume → volta ao estágio 1
    timeout sem fala → restaura volume → volta ao estágio 1
```

## Convenções de Código
- Arquivos/funções: `snake_case` | Constantes: `UPPER_CASE` (`TARGET_RATE`, `CHUNK`)
- Comentários e prints em PT-BR
- Sem testes automatizados atualmente; dependências em `req.txt` (não `requirements.txt`)
- `venv` criado com `--system-site-packages` (necessário para `python3-dbus`)

## Git Workflow

### Branches
```
[feature|fix]/[main|qa]/[nome-breve-com-hifens]

Exemplos:
  feature/main/bluetooth-reconnect
  fix/qa/audio-duck-volume
  feature/qa/whisper-vad-tuning
```

### Commits
```
[QA|MAIN] descrição breve em PT-BR

Exemplos:
  [QA] adiciona fuzzy matching para wake word
  [MAIN] fix: audio duck não restaura volume ao falhar TTS
  [QA] refatora dispatcher para suportar novos módulos
```

### Hooks (`.githooks/`)
Ativar uma vez no clone: `git config core.hooksPath .githooks`
- `commit-msg` — bloqueia commits fora do formato `[QA|MAIN] descrição`
- `pre-push` — valida nome de branch; avisa se `.py` mudou sem atualizar docs

### Worktrees
Usar skill `using-git-worktrees` antes de qualquer trabalho de feature isolado.

## Regra de Atualização de Docs
**Antes de qualquer push**, atualizar `ai_docs/` ou `CLAUDE.md` quando:
- Nova feature, comando de voz, módulo ou dependência adicionada/removida
- Gotcha ou restrição descoberta
- Decisão arquitetural tomada
- Mudança no setup ou hardware

E atualizar `README.md` para qualquer mudança visível ao usuário final (features, stack, setup).

## Quando Ler Cada Doc

| Tarefa | Leia |
|---|---|
| Qualquer implementação | `ai_docs/rules.md` — regras que não podem quebrar |
| Debugar / algo não funciona | `ai_docs/gotchas.md` |
| Trabalhar em features | `ai_docs/features.md` |
| Stack, hardware, integrações, setup | `ai_docs/context.md` |

## Decisões Importantes

> Registre aqui decisões arquiteturais com data e motivo. Quando passar de ~8 entradas, mover para `ai_docs/decisions.md`.

| Data | Decisão | Motivo |
|---|---|---|
| 2026-05-05 | Whisper é o único backend STT; Vosk removido | Vosk confundia "carro" com "carla"; Whisper tem precisão muito superior em PT-BR |
| 2026-05-05 | Saída de áudio via cabo P2 3.5mm, não Bluetooth | O rádio do Palio não é BT-capable; celular conecta por A2DP no Rock Pi que repassa pelo cabo |
| 2026-05-05 | GPS e chamadas telefônicas removidos do roadmap | GPS: complexidade alta sem definição de integração; HFP: requer hardware extra |
| 2026-05-05 | PipeWire ao invés de PulseAudio | Suporte nativo a múltiplos perfis BT simultâneos (A2DP sink + source) |
| 2026-05-05 | Ollama em vez de rodar modelo diretamente | Gerencia ciclo de vida do modelo, mantém em memória entre calls, troca de modelo sem alterar código |
| 2026-05-05 | piper-tts (OHF-Voice) substituiu pyttsx3+espeak-ng | espeak-ng é formântico (robótico); piper usa ONNX neural PT-BR com qualidade muito superior. Instalação offline via wheel ARM64 + modelo .onnx |
| 2026-05-05 | `falar()` como closure em `inicializar()` | Carrega modelo uma vez no boot; mantém assinatura `Callable[[str], None]` sem quebrar PairingManager/Dispatcher |
