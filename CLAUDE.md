# Contexto do Projeto — Palio-IA

Antes de qualquer tarefa, leia os arquivos em `ai_docs/` para entender o projeto:

| Arquivo | Quando ler |
|---|---|
| `ai_docs/index.md` | Sempre — visão geral e status dos módulos |
| `ai_docs/business-rules.md` | Sempre — regras críticas de áudio, wake word e validações |
| `ai_docs/gotchas.md` | Antes de implementar qualquer coisa — armadilhas e bugs conhecidos |
| `ai_docs/patterns.md` | Ao criar ou refatorar código — padrões e convenções do projeto |
| `ai_docs/features.md` | Ao trabalhar em novas features — o que já existe e o que está planejado |
| `ai_docs/stack.md` | Ao avaliar dependências ou arquitetura — decisões técnicas já tomadas |
| `ai_docs/integrations.md` | Ao mexer em hardware, Bluetooth, LLM ou APIs externas |

## Resumo rápido

- Assistente de voz embarcado para um Fiat Palio, rodando em **Rock Pi 4B** (ARM64)
- Processamento 100% offline: Vosk (STT), pyttsx3/espeak-ng (TTS), Ollama (LLM)
- Wake word: **"palio"** ou **"carro"**
- Áudio obrigatório: **16kHz mono** (Vosk)
- Idioma: **português brasileiro**
- Entry point principal: `main.py`
