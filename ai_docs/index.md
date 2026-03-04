# Documentação do Palio-IA

## Visão Geral

Palio-IA é um assistente de voz embarcado desenvolvido para operar dentro de um carro (Fiat Palio), rodando em um **Rock Pi 4B**. O objetivo é fornecer controle por voz completamente offline para funções do veículo: controle de música via Bluetooth, navegação GPS, chamadas telefônicas, respostas inteligentes via LLM local (Ollama) e relatórios de hora/clima.

O projeto está em desenvolvimento ativo (v0.0.9) com arquitetura modular. O orquestrador principal integra STT, TTS, controle Bluetooth de música e LLM com persona "Palio".

## Documentação Disponível

### Arquitetura e Stack
- [Stack Tecnológica](stack.md) - Tecnologias, frameworks e ferramentas utilizadas
- [Padrões de Design](patterns.md) - Padrões arquiteturais e de código

### Funcionalidades e Regras
- [Funcionalidades](features.md) - Descrição das funcionalidades implementadas e planejadas
- [Regras de Negócio](business-rules.md) - Regras e lógicas implementadas no sistema
- [Gotchas](gotchas.md) - Armadilhas, bugs conhecidos e conhecimento tácito essencial

### Integrações
- [Integrações](integrations.md) - Comunicação com hardware, Bluetooth, LLM e serviços externos

## Estado Atual do Projeto

| Módulo                  | Arquivo                        | Status           |
|-------------------------|--------------------------------|------------------|
| Speech-to-Text (STT)    | `speech_to_text.py`            | Funcional        |
| Text-to-Speech (TTS)    | `main.py` → `falar()`          | Funcional        |
| Orquestrador            | `main.py`                      | Funcional        |
| Dispatcher de intenção  | `modules/core/dispatcher.py`   | Funcional        |
| Controle Bluetooth      | `modules/bluetooth/music.py`   | Implementado (requer Linux+bluez) |
| Persona Palio           | `modules/llm/persona.py`       | Funcional        |
| Cliente LLM (Ollama)    | `modules/llm/client.py`        | Implementado (requer Ollama rodando) |
| Integração GPS          | A implementar                  | Planejado        |
| Chamadas telefônicas    | A implementar                  | Planejado        |

## Links Rápidos

- **Repositório**: `C:\Users\gabri\Desktop\Palio-IA` (local)
- **Hardware alvo**: Rock Pi 4B
- **Modelo de voz**: Vosk PT-BR (`model-ptbr/`) — deve ser baixado manualmente (nao incluso no git)
- **Ambiente de Desenvolvimento**: Python 3.x + `pip install -r req.txt` + baixar modelo Vosk PT-BR
- **Versao atual**: v0.0.9
