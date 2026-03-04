# Padrões de Design

## Padrões Arquiteturais

### Pipeline de Processamento de Áudio
O sistema segue um pipeline linear de processamento de voz:

```
Microfone → Captura (PyAudio) → Resample (scipy) → STT (Vosk) → 
Detecção de intenção → Execução de comando → TTS (pyttsx3) → Saída de áudio
```

Cada etapa tem responsabilidade única e bem definida.

### Arquitetura de Módulos Independentes (Estado Atual)
Atualmente o projeto tem dois módulos separados que serão integrados:

```
speech_to_text.py   →   Responsabilidade: captura e reconhecimento de voz
main.py             →   Responsabilidade: síntese e reprodução de voz
[futuro main pai]   →   Orquestração dos dois módulos + LLM + comandos
```

### Event Loop Assíncrono (asyncio)
`main.py` usa `asyncio` para permitir I/O não-bloqueante. A intenção é que o sistema final possa:
- Ouvir o microfone enquanto aguarda resposta do LLM
- Reproduzir áudio sem bloquear o reconhecimento de novos comandos
- Gerenciar múltiplas operações de I/O simultaneamente (Bluetooth, GPS, etc.)

## Padrões de Código

### Wake Word + Comando (Trigger Word Pattern)
O reconhecimento de intenção segue o padrão:

```
[wake word] + [comando]
```

Exemplo: `"carro próxima"` → wake word = `"carro"`, comando = `"próxima"`

Implementado em `speech_to_text.py:109-116`:
```python
if "carro" in recognized_text:          # 1. Detecta wake word
    if verificar_palavra(texto, 'próxima'):   # 2. Identifica comando
        # executa ação
    elif verificar_palavra(texto, 'voltar'):
        # executa ação
```

### Normalização de Texto (Utility Function Pattern)
Funções utilitárias puras para normalização antes da comparação de strings:

```python
def remove_acentos(texto):      # Normaliza Unicode NFD, remove Mn
def verificar_palavra(frase, palavra):  # Compara ignorando acentos e case
```

Localização: `speech_to_text.py:9-21`

Essa abordagem é necessária porque o Vosk pode retornar texto com ou sem acentos dependendo do modelo e da pronúncia detectada.

### Auto-seleção de Dispositivo (Strategy Pattern implícito)
A função `get_best_microphone()` em `speech_to_text.py:42-61` itera por todos os dispositivos de entrada disponíveis e seleciona automaticamente o mais próximo de 16kHz. Isso elimina configuração manual de hardware, tornando o código portável entre diferentes microfones.

### Arquivo de Áudio Temporário (Temp File Pattern)
`main.py` usa um arquivo WAV temporário como intermediário:
```python
engine.save_to_file(res, 'output.wav')  # Gera arquivo
engine.runAndWait()
winsound.PlaySound('output.wav', ...)   # Reproduz
os.remove('output.wav')                 # Limpa
```

Esse padrão é necessário porque `pyttsx3` não suporta streaming direto de áudio sem passar por arquivo em algumas engines.

## Organização de Código

### Estrutura Atual de Arquivos

```
Palio-IA/
├── main.py              # Módulo TTS (text-to-speech)
├── speech_to_text.py    # Módulo STT (speech-to-text) + detecção de comandos
├── req.txt              # Dependências pip (nome não padrão — normalmente é requirements.txt)
├── input.txt            # Arquivo de teste/rascunho
├── output.txt           # Arquivo de teste/rascunho
├── model-ptbr/          # Modelo Vosk PT-BR (NÃO incluso no git, baixar manualmente)
├── venv/                # Ambiente virtual Python (NÃO incluso no git)
└── ai_docs/             # Documentação do projeto
```

### Estrutura Planejada (Futuro)

```
Palio-IA/
├── main.py              # Arquivo pai — orquestra todos os módulos
├── modules/
│   ├── stt.py           # Speech-to-text (refatorado de speech_to_text.py)
│   ├── tts.py           # Text-to-speech (refatorado de main.py)
│   ├── llm.py           # Integração com Ollama
│   ├── music.py         # Controle de música via Bluetooth
│   ├── navigation.py    # Integração GPS
│   └── phone.py         # Controle de chamadas
├── config.py            # Configurações centralizadas (taxa de amostragem, wake word, etc.)
├── req.txt
└── model-ptbr/
```

## Convenções de Nomenclatura

| Elemento         | Convenção                    | Exemplo                         |
|------------------|------------------------------|---------------------------------|
| Arquivos         | snake_case                   | `speech_to_text.py`             |
| Funções          | snake_case descritivo        | `get_best_microphone()`, `remove_acentos()` |
| Variáveis        | UPPER_CASE para constantes   | `TARGET_RATE`, `CHUNK`, `MODEL_PATH` |
| Variáveis locais | snake_case                   | `recognized_text`, `audio_data` |
| Idioma           | Português (comentários e prints) | `"Passando a música..."` |

## Padrões de Tratamento de Erros

### Tratamento Atual
- `try/except ImportError` para `winsound` (fallback com mensagem)
- `try/except Exception` genérico para erros de áudio
- `exit(1)` imediato se modelo Vosk não encontrado ou microfone não detectado
- `exception_on_overflow=False` no `stream.read()` para ignorar buffer overflow silenciosamente

### Padrão de Validação de Pré-condições
```python
if not os.path.exists(MODEL_PATH):
    print("O caminho do modelo não foi encontrado.")
    exit(1)
```
O sistema falha rápido (fail-fast) se dependências críticas estão ausentes.

## Padrões de Teste

**Estado atual**: Sem testes automatizados.

`input.txt` e `output.txt` são usados como arquivos de teste manual/rascunho.

**Recomendação para o futuro**:
- Testes unitários para `remove_acentos()` e `verificar_palavra()` (funções puras, fáceis de testar)
- Testes de integração com arquivos WAV pré-gravados como input para o STT
- Mock do microfone para testes offline

## Padrões de Logging

Atualmente usa `print()` direto para todos os logs:
```python
print("Modelo carregado com sucesso!")
print(f"Dispositivo {i}: {device_info['name']}, Taxa máxima: {rate} Hz")
print("DEBUG: Resultados do modelo:", result)
print(f"Comando detectado: '{recognized_text}'")
```

O prefixo `DEBUG:` é usado informalmente para logs de depuração. Quando o projeto crescer, considerar migrar para o módulo `logging` da stdlib com níveis (DEBUG, INFO, WARNING, ERROR).
