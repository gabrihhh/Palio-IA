# Gotchas e Conhecimento Tácito

Este documento captura o conhecimento que desenvolvedores experientes acumulam ao longo do tempo — as "armadilhas" não documentadas, comportamentos contra-intuitivos e workarounds que são essenciais para trabalhar efetivamente neste repositório.

---

## Bugs Conhecidos

### ~~`await winsound.PlaySound(...)` causa erro de runtime~~ — RESOLVIDO
**Sintoma**: `TypeError: object NoneType can't be used in 'await' expression`.

**Causa**: `winsound.PlaySound()` é síncrona e retorna `None`. Não pode ser `await`ada.

**Resolução (v0.0.8)**: `asyncio` removido do TTS. A função `falar()` agora é síncrona. `winsound` foi substituído por `sounddevice` + `soundfile` (cross-platform).

---

## Armadilhas Comuns

### Modelo Vosk não está no repositório
**Sintoma**: `O caminho do modelo não foi encontrado.` + `exit(1)` ao rodar `speech_to_text.py`.

**Causa**: A pasta `model-ptbr/` está no `.gitignore` e nunca é commitada. Em um clone fresco do repositório, o modelo não existe.

**Solução**:
1. Acessar https://alphacephei.com/vosk/models
2. Baixar um modelo PT-BR (ex: `vosk-model-small-pt-0.3` ~30MB ou `vosk-model-pt-fb-v0.1.1-20220516_2113` ~1.5GB para maior precisão)
3. Extrair na raiz do projeto com o nome `model-ptbr/`

**Estrutura esperada**:
```
Palio-IA/
└── model-ptbr/
    ├── am/
    ├── conf/
    ├── graph/
    └── ...
```

**Por que está no .gitignore**: O modelo é grande demais para versionar (30MB a 1.5GB). Não faz sentido incluir arquivos binários grandes no git.

---

### ~~`winsound` não existe no Linux/Rock Pi 4B~~ — RESOLVIDO
**Resolução (v0.0.8)**: Substituído por `sounddevice` + `soundfile`, que funcionam em Windows e Linux/ARM64.

---

### Taxa de amostragem do microfone causa reconhecimento ruim
**Sintoma**: Vosk retorna texto completamente errado, palavras aleatórias, ou string vazia mesmo com fala clara.

**Causa mais comum**: O resampling está sendo aplicado incorretamente ou o microfone opera em uma taxa muito diferente de 16kHz (ex: 192kHz), causando distorção.

**Diagnóstico**: Verificar o log de inicialização:
```
Dispositivo 0: Microphone (USB Audio), Taxa máxima: 44100 Hz
Microfone selecionado: Microphone (USB Audio) com taxa de 44100 Hz
```
Se a taxa for muito alta (>96kHz), o resampling com `scipy.signal.resample` pode introduzir artefatos.

**Solução**: Para microfones de 44.1kHz ou 48kHz o resampling funciona bem. Para taxas muito altas, considerar especificar o microfone manualmente em vez de usar a auto-seleção.

---

### O arquivo `req.txt` não segue o nome padrão do pip
**Sintoma**: `pip install -r requirements.txt` falha com "Arquivo não encontrado".

**Causa**: O arquivo de dependências se chama `req.txt` e não `requirements.txt` (nome padrão do ecossistema Python).

**Solução**: Sempre usar o nome correto:
```bash
pip install -r req.txt
```

**Por que está assim**: Escolha do desenvolvedor — não há motivo técnico. Candidato a renomear para `requirements.txt` para seguir convenção.

---

### Inicialização do `speech_to_text.py` é bloqueante no nível de módulo
**Sintoma**: Ao importar `speech_to_text.py` em outro arquivo, o código de nível de módulo executa imediatamente — incluindo a carga do modelo Vosk (lenta), abertura do stream de áudio, e o loop `while True`.

**Causa**: O código não está encapsulado em funções ou classes. Tudo roda ao ser importado:
```python
# speech_to_text.py — executa ao ser importado:
model = vosk.Model(MODEL_PATH, ...)  # lento, ~5-30 segundos
p = pyaudio.PyAudio()
DEVICE_INDEX, DEVICE_RATE = get_best_microphone(p, TARGET_RATE)
stream = p.open(...)
while True:  # loop infinito!
    ...
```

**Solução ao integrar**: Antes de criar o arquivo pai, refatorar `speech_to_text.py` para encapsular tudo em uma classe ou função, sem execução de nível de módulo:
```python
def iniciar_stt():
    model = vosk.Model(MODEL_PATH, ...)
    # ...
    return recognizer, stream

def ouvir_comando(recognizer, stream):
    # loop de escuta
    pass
```

---

### Buffer overflow do microfone é ignorado silenciosamente
**Sintoma**: Comandos ocasionalmente não são detectados mesmo com fala clara.

**Causa**: `stream.read(CHUNK, exception_on_overflow=False)` ignora silenciosamente overflows de buffer. Se o sistema estiver processando lentamente (ex: Vosk ocupado), chunks de áudio são descartados.

**Localização**: `speech_to_text.py:92`

**Implicação**: Em hardware lento (Rock Pi 4B com modelo grande), o início de uma frase pode ser perdido se o sistema estiver ocupado. A wake word pode ser descartada.

---

## Comportamentos Contra-Intuitivos

### `engine.runAndWait()` já gera e "salva" o áudio — não apenas aguarda
**O que parece**: `save_to_file()` salva o áudio e `runAndWait()` apenas espera terminar.

**O que realmente acontece**: `save_to_file()` apenas enfileira a operação. `runAndWait()` é quem processa a fila e **realmente** gera e salva o arquivo WAV. O arquivo só existe após `runAndWait()` retornar.

**Implicação**: Não tente ler ou reproduzir `output.wav` antes de `runAndWait()` completar.

**Localização**: `main.py:16-19`

---

### Vosk carrega o modelo com parâmetros custom sem validação
**O que parece**: `{"beam": 15, "max-active": 10000}` é uma configuração óbvia.

**O que realmente acontece**: Vosk aceita esses parâmetros silenciosamente mesmo que sejam inválidos. Aumentar `beam` aumenta precisão mas também latência. Aumentar `max-active` aumenta uso de memória. No Rock Pi 4B com RAM limitada, valores muito altos podem causar OOM (Out of Memory).

**Valores atuais**:
- `beam: 15` — latência moderada
- `max-active: 10000` — uso de memória moderado

---

### `AcceptWaveform()` espera bytes, não numpy array
**O que parece**: Como o áudio já foi convertido para numpy array para resampling, parece natural passar o array diretamente.

**O que realmente acontece**: `AcceptWaveform()` espera `bytes`. Por isso é necessário `.tobytes()` explicitamente:
```python
recognizer.AcceptWaveform(audio_data.tobytes())  # correto
recognizer.AcceptWaveform(audio_data)             # erro silencioso ou crash
```

**Localização**: `speech_to_text.py:102`

---

## Dependências de Ordem e Sequência

### Sequência obrigatória de inicialização do STT
```
1. Verificar MODEL_PATH existe
2. Carregar model = vosk.Model(...)      ← lento (5-30s)
3. Inicializar p = pyaudio.PyAudio()
4. Detectar get_best_microphone()        ← depende de (3)
5. Abrir stream = p.open(...)            ← depende de (4)
6. Criar recognizer = vosk.KaldiRecognizer(model, TARGET_RATE)  ← depende de (2)
7. Iniciar loop while True               ← depende de (5) e (6)
```

Se qualquer etapa falhar, as subsequentes não devem ser executadas. O código atual usa `exit(1)` nas etapas 1, 4 e 5 para garantir isso.

### Sequência obrigatória de inicialização do TTS
```
1. engine = pyttsx3.init()
2. engine.setProperty('rate', 160)
3. engine.setProperty('volume', 1)
4. engine.save_to_file(texto, 'output.wav')
5. engine.runAndWait()                   ← só aqui o arquivo é gerado
6. winsound.PlaySound('output.wav', ...) ← depende de (5)
7. os.remove('output.wav')               ← depende de (6)
```

---

## Configurações Não-Óbvias

### `CHUNK = 4096` — tamanho do buffer de áudio
**Configuração**: `speech_to_text.py:37`

**Por que parece errado**: Chunks maiores aumentam latência. Um valor menor (ex: 1024) pareceria mais responsivo.

**Por que está certo**: Para o Vosk funcionar bem, ele precisa de chunks suficientemente grandes para processar fonemas completos. 4096 amostras @ 16kHz = ~256ms de áudio por chunk — um bom balanço entre latência e precisão. Valores menores podem fragmentar fonemas e reduzir a qualidade do reconhecimento.

### `beam: 15` — feixe de busca do Vosk
**Configuração**: `speech_to_text.py:32`

**Por que parece errado**: O valor padrão do Vosk é menor. 15 parece arbitrário.

**Por que está assim**: Aumenta a precisão do reconhecimento às custas de maior CPU. No contexto de carro com ruído, precisão é mais importante que latência mínima.

---

## Débitos Técnicos Conhecidos

### ~~Código de nível de módulo em `speech_to_text.py`~~ — RESOLVIDO
**Resolução (v0.0.8)**: Todo o código de inicialização foi encapsulado em funções (`carregar_modelo`, `get_best_microphone`, `iniciar_loop_stt`). O arquivo pode ser importado sem disparar o loop STT. Guard `if __name__ == '__main__':` adicionado.

### ~~`winsound` não é multiplataforma~~ — RESOLVIDO
**Resolução (v0.0.8)**: Substituído por `sounddevice` + `soundfile`.

### Sem arquivo `requirements.txt` padrão
**Descrição**: O arquivo se chama `req.txt` em vez do padrão `requirements.txt`.

**Impacto**: Ferramentas que detectam automaticamente dependências Python (GitHub Dependabot, Poetry, etc.) não funcionam.

**Plano**: Renomear para `requirements.txt`.

### ~~Sem `if __name__ == "__main__"` guard~~ — RESOLVIDO
**Resolução (v0.0.8)**: Guards adicionados em `main.py` e `speech_to_text.py`.

---

## Dicas de Desenvolvimento

### Ambiente Local (Windows)

```bash
# 1. Criar e ativar venv
python -m venv venv
.\venv\Scripts\activate

# 2. Instalar dependências (atenção ao nome do arquivo)
pip install -r req.txt

# 3. Baixar modelo Vosk PT-BR
# Acessar: https://alphacephei.com/vosk/models
# Baixar e extrair como ./model-ptbr/

# 4. Testar TTS
python main.py

# 5. Testar STT (requer microfone)
python speech_to_text.py
```

### Debugging de Problemas de Reconhecimento

Se o Vosk não reconhece corretamente:
1. Verificar no log qual microfone foi selecionado e sua taxa de amostragem
2. Verificar se o resampling está sendo aplicado (log implícito nas variáveis)
3. Adicionar `print(result)` após `recognizer.Result()` para ver o JSON completo (já existe como `"DEBUG: Resultados do modelo:"`)
4. Testar com fala mais devagar e articulada — o modelo small PT-BR tem limitações
5. Considerar usar o modelo maior para melhor precisão

### Performance no Rock Pi 4B

- O modelo Vosk `small` (~30MB) roda bem em ARM com baixa latência
- O modelo `large` (~1.5GB) tem muito mais precisão mas pode ser lento no Rock Pi 4B
- Para Ollama no Rock Pi 4B, usar modelos quantizados 4-bit (`llama3.2:3b` ou `mistral:7b-instruct-q4_K_M`)
- Evitar `max-active` muito alto no Vosk para não estourar RAM

---

## O Que Eu Gostaria de Ter Sabido

- **O modelo Vosk nunca estará no clone** — sempre precisará ser baixado separadamente. Documente isso em um README.
- **`winsound` não existe no Linux** — o código não vai rodar no alvo final sem modificação.
- **`speech_to_text.py` agora pode ser importado** — refatorado em v0.0.8, loop encapsulado em `iniciar_loop_stt()`.
- **O `await winsound.PlaySound(...)` foi corrigido** — removido em v0.0.8, TTS agora usa `sounddevice`.
- **`winsound` foi removido** — substituído por `sounddevice` + `soundfile`, funciona no Linux/Rock Pi 4B.
- **O resampling é obrigatório** — praticamente nenhum microfone de consumo opera a 16kHz nativamente.
- **Vosk é lento para carregar** (5-30s) — planeje uma tela/indicador de "inicializando" no produto final.
- **Ruído de carro é o maior inimigo** — considerar implementar VAD (Voice Activity Detection) para só processar quando há fala real, reduzindo falsos positivos e carga de CPU.
