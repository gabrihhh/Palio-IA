# Regras de Negócio

## Regras Críticas

### Regra 1: Vosk exige áudio em 16kHz mono
**Descrição**: O modelo Vosk PT-BR aceita exclusivamente áudio com taxa de amostragem de 16.000 Hz (16kHz) e canal mono (1 canal).

**Justificativa**: O modelo Kaldi subjacente foi treinado com esse formato. Áudio em outra taxa gera reconhecimento completamente errado ou silencioso, sem lançar erro explícito.

**Implementação**: `speech_to_text.py:36,79-84`
```python
TARGET_RATE = 16000
recognizer = vosk.KaldiRecognizer(model, TARGET_RATE)

def resample_audio(audio_data, original_rate, target_rate):
    if original_rate != target_rate:
        num_samples = int(len(audio_data) * target_rate / original_rate)
        return resample(audio_data, num_samples)
    return audio_data
```

**Validações**: `DEVICE_RATE` (taxa do microfone) é detectada em runtime; se diferente de `TARGET_RATE`, o resampling é aplicado automaticamente.

**Consequência se ignorado**: O Vosk vai transcrever lixo ou retornar strings vazias, e os comandos nunca serão detectados.

---

### Regra 2: Wake Word obrigatória antes de qualquer comando
**Descrição**: Nenhuma ação é executada a menos que a wake word (atualmente `"carro"`) seja detectada na frase reconhecida.

**Justificativa**: Evita que conversas normais no carro ou músicas tocando acionem comandos acidentalmente.

**Implementação**: `speech_to_text.py:109`
```python
if "carro" in recognized_text:
    # só aqui processa comandos
```

**Implicações**: Se a wake word não for pronunciada claramente, ou se o Vosk não a reconhecer corretamente, nenhum comando funcionará mesmo que o restante da frase seja perfeito.

**Exceções**: Nenhuma — a wake word é sempre obrigatória.

---

### Regra 3: Comparação de comandos sem acento e case-insensitive
**Descrição**: Ao verificar qual comando foi dito, a comparação ignora acentuação e maiúsculas/minúsculas.

**Justificativa**: O Vosk pode transcrever "próxima" ou "proxima" dependendo da qualidade do áudio. Normalizar antes de comparar torna o sistema mais robusto.

**Implementação**: `speech_to_text.py:9-21`
```python
def remove_acentos(texto):
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

def verificar_palavra(frase, palavra):
    frase_normalizada = remove_acentos(frase).lower()
    palavra_normalizada = remove_acentos(palavra).lower()
    return palavra_normalizada in frase_normalizada
```

**Regra**: `"próxima"` == `"proxima"` == `"PROXIMA"` == `"Próxima"` para fins de detecção de comando.

---

### Regra 4: Modelo deve existir localmente antes da inicialização
**Descrição**: O sistema verifica se a pasta `model-ptbr/` existe antes de tentar carregar o modelo. Se não existir, o programa encerra imediatamente.

**Implementação**: `speech_to_text.py:26-29`
```python
MODEL_PATH = "model-ptbr"
if not os.path.exists(MODEL_PATH):
    print("O caminho do modelo não foi encontrado.")
    exit(1)
```

**Justificativa**: Falhar rápido com mensagem clara é melhor do que um erro críptico do Vosk internamente.

**Consequência**: O modelo nunca está no git (`.gitignore`). Cada nova instalação precisa baixar o modelo manualmente.

---

### Regra 5: Reconhecimento somente em resultados finais (não parciais)
**Descrição**: O sistema processa apenas resultados finais do Vosk (`AcceptWaveform() == True`), ignorando resultados parciais.

**Implementação**: `speech_to_text.py:102-104`
```python
if recognizer.AcceptWaveform(audio_data.tobytes()):
    result = json.loads(recognizer.Result())
    recognized_text = result.get('text', '').strip()
```

**Justificativa**: Resultados parciais mudam constantemente enquanto o usuário fala. Processar apenas resultados finais evita execução de comandos incompletos.

**Trade-off**: Aumenta a latência percebida (o sistema espera a pausa natural na fala para processar).

---

### Regra 6: TTS usa velocidade e volume fixos
**Descrição**: A síntese de voz opera com parâmetros fixos configurados em código.

**Implementação**: `main.py:10-13`
```python
engine.setProperty('rate', 160)   # 160 palavras por minuto
engine.setProperty('volume', 1)   # Volume máximo (1.0)
```

**Justificativa**: No ambiente de carro com ruído de motor e música, volume máximo e velocidade moderada garantem inteligibilidade. Valores configuráveis via interface ainda não estão implementados.

---

## Validações e Restrições

| Validação                          | Localização                      | Consequência de Falha  |
|------------------------------------|----------------------------------|------------------------|
| Pasta `model-ptbr/` deve existir   | `speech_to_text.py:26-29`       | `exit(1)`              |
| Microfone deve estar disponível    | `speech_to_text.py:60-61`       | `exit(1)`              |
| Stream de áudio deve abrir com sucesso | `speech_to_text.py:67-76`   | `exit(1)`              |
| Áudio capturado não pode ser vazio | `speech_to_text.py:93-95`       | `continue` (ignora)    |
| Buffer overflow de áudio           | `speech_to_text.py:92`          | Ignorado silenciosamente |

---

## Políticas de Detecção de Comandos

### Hierarquia de verificação
```
1. Texto reconhecido pelo Vosk (resultado final)
   └── Contém wake word ("carro")?
       ├── NÃO → Ignorar completamente
       └── SIM → Verificar comandos:
           ├── Contém "próxima" (normalizado)?  → Passar música
           ├── Contém "voltar" (normalizado)?   → Voltar música
           └── Nenhum comando reconhecido?       → Log "Comando desconhecido"
```

### Política de comando desconhecido
Quando a wake word é detectada mas nenhum comando mapeado é encontrado, o sistema apenas loga a frase sem executar ação:
```python
print(f"Comando desconhecido na frase: '{recognized_text}'")
```
**Futuro**: Comandos desconhecidos devem ser roteados para o LLM (Ollama).

---

## Cálculos e Algoritmos

### Cálculo de Resampling
Converte o número de amostras proporcionalmente entre duas taxas:
```python
num_samples = int(len(audio_data) * target_rate / original_rate)
```
Exemplo: 4096 amostras @ 48kHz → `int(4096 * 16000 / 48000)` = 1365 amostras @ 16kHz

### Seleção do Melhor Microfone
Minimiza `|taxa_do_dispositivo - TARGET_RATE|` iterando por todos os dispositivos de entrada disponíveis. É um algoritmo de busca linear O(n) onde n = número de dispositivos de áudio.

---

## Regras de Domínio

### O que constitui um "comando válido"
1. O áudio deve resultar em texto não-vazio após reconhecimento pelo Vosk
2. O texto deve conter a wake word exata (busca por substring, sem normalização)
3. Após a wake word, deve haver pelo menos uma palavra de comando reconhecida (com normalização)

### Idioma
Todo o sistema opera exclusivamente em **português brasileiro**:
- Modelo Vosk: `model-ptbr` (treinado em PT-BR)
- Wake word e comandos em PT-BR
- Mensagens de log e TTS em PT-BR

### Persistência
O sistema é **stateless** — não mantém estado entre comandos. Cada frase reconhecida é processada de forma independente. Não há histórico de comandos, contexto de conversa ou memória entre execuções.

**Implicação**: Para integração com LLM com memória de contexto, será necessário implementar gerenciamento de histórico de conversa.
