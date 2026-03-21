# Documentação do Palio-IA

## Visão Geral

Palio-IA é um assistente de voz embarcado desenvolvido para operar dentro de um carro (Fiat Palio), rodando em **Radxa ROCK 4B com Debian 12 Bookworm ARM64** (referência: Rock Pi 4B). O objetivo é fornecer controle por voz **completamente offline** para funções do veículo: controle de música via Bluetooth, respostas inteligentes via LLM local (Ollama) e expansão futura de controles por voz.

> **Princípio fundamental: o projeto é 100% offline. Toda feature deve funcionar sem internet.**

O projeto está em desenvolvimento ativo (v0.0.9) com arquitetura modular.

## Documentação Disponível

### Arquitetura e Stack
- [Stack Tecnológica](stack.md) — Tecnologias, frameworks e ferramentas utilizadas
- [Padrões de Design](patterns.md) — Padrões arquiteturais e de código

### Funcionalidades e Regras
- [Funcionalidades](features.md) — Funcionalidades implementadas, planejadas e fora do escopo
- [Regras de Negócio](business-rules.md) — Regras e restrições críticas do sistema
- [Gotchas](gotchas.md) — Armadilhas, bugs conhecidos e conhecimento tácito essencial

### Integrações
- [Integrações](integrations.md) — Hardware, Bluetooth, LLM e dependências do sistema

## Estado Atual do Projeto

| Módulo | Arquivo | Status |
|---|---|---|
| Speech-to-Text (STT) | `speech_to_text.py` | Funcional |
| Text-to-Speech (TTS) | `main.py` → `falar()` | Funcional |
| Orquestrador | `main.py` | Funcional |
| Dispatcher de intenção | `modules/core/dispatcher.py` | Funcional |
| Controle Bluetooth AVRCP | `modules/bluetooth/music.py` | Funcional (requer Linux + bluez) |
| Pareamento Bluetooth por voz | `modules/bluetooth/pairing.py` | Funcional (requer Linux + bluez) |
| Audio Duck | `modules/bluetooth/audio_duck.py` | Funcional (requer Linux + PipeWire) |
| Persona Palio | `modules/llm/persona.py` | Funcional |
| Cliente LLM (Ollama) | `modules/llm/client.py` | Funcional (requer Ollama rodando) |
| Controle de Volume por Voz | `modules/bluetooth/audio.py` | Implementado, aguardando integração |

## Links Rápidos

- **Hardware alvo**: Radxa ROCK 4B — Debian 12 Bookworm ARM64 (CLI, sem desktop)
- **Modelo de voz**: Vosk PT-BR (`model-ptbr/`) — deve ser baixado manualmente (não incluso no git)
- **Setup**: `python3 -m venv --system-site-packages venv && pip install -r req.txt`
- **Versão atual**: v0.0.9
