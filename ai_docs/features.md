# Funcionalidades

## Funcionalidades Implementadas

### Reconhecimento de Voz Offline (STT)
**Descrição**: Captura áudio contínuo do microfone e converte fala em texto usando o modelo Vosk PT-BR localmente, sem depender de internet.

**Casos de Uso**: Base de todo o sistema de comandos por voz. Sem STT, nenhum outro módulo funciona.

**Componentes Envolvidos**:
- `speech_to_text.py` (arquivo principal do módulo)
- Modelo `model-ptbr/` (Vosk, deve ser baixado manualmente)
- `PyAudio` para captura do microfone
- `scipy.signal.resample` para ajuste de taxa de amostragem

**Fluxo de execução**:
1. Detecta o melhor microfone disponível (mais próximo de 16kHz)
2. Abre stream de áudio com a taxa nativa do microfone
3. Lê chunks de 4096 amostras em loop contínuo
4. Se taxa do microfone != 16kHz, reamostra para 16kHz (Vosk exige)
5. Alimenta o recognizer Vosk com os bytes de áudio
6. Quando `AcceptWaveform()` retorna `True`, processa o resultado completo
7. Extrai texto reconhecido do JSON de resultado

**Dependências**: Modelo Vosk PT-BR em `./model-ptbr/`

---

### Auto-seleção de Microfone
**Descrição**: Itera por todos os dispositivos de áudio disponíveis e seleciona automaticamente o microfone cuja taxa de amostragem nativa é mais próxima de 16kHz.

**Casos de Uso**: Portabilidade entre diferentes ambientes de hardware sem configuração manual.

**Componentes Envolvidos**: `speech_to_text.py:42-61` — função `get_best_microphone()`

**Comportamento**: Se nenhum microfone for encontrado, o programa exibe mensagem e encerra com `exit(1)`.

---

### Resampling de Áudio
**Descrição**: Converte áudio capturado na taxa nativa do microfone para 16kHz (taxa exigida pelo Vosk).

**Casos de Uso**: Necessário quando o microfone opera em 44.1kHz ou 48kHz (padrão de hardware de consumo).

**Componentes Envolvidos**: `speech_to_text.py:79-84` — função `resample_audio()`

**Implementação**:
```python
def resample_audio(audio_data, original_rate, target_rate):
    if original_rate != target_rate:
        num_samples = int(len(audio_data) * target_rate / original_rate)
        return resample(audio_data, num_samples)
    return audio_data
```

---

### Detecção de Wake Word + Comando
**Descrição**: Após o STT converter fala em texto, verifica se a wake word está presente e identifica qual comando foi solicitado.

**Casos de Uso**: Ativar o assistente apenas quando a palavra-chave for detectada, evitando execuções indesejadas.

**Componentes Envolvidos**: `speech_to_text.py:109-117`

**Wake word atual**: `"carro"` (planejado mudar para `"Palio"`)

**Comandos implementados**:
| Comando falado          | Ação executada           |
|-------------------------|--------------------------|
| "carro próxima"         | Passar a música          |
| "carro voltar"          | Voltar a música          |

**Normalização**: Usa `verificar_palavra()` que remove acentos e ignora maiúsculas antes de comparar, tornando a detecção robusta a variações de pronúncia.

---

### Síntese de Voz Offline (TTS)
**Descrição**: Converte texto em fala usando `pyttsx3` offline, salva em arquivo WAV temporário e reproduz o áudio.

**Casos de Uso**: Feedback de voz para o motorista — confirmar comandos, responder perguntas, anunciar informações.

**Componentes Envolvidos**: `main.py` — função `falar(res)`

**Fluxo de execução**:
1. Inicializa engine pyttsx3
2. Configura taxa de fala: 160 palavras/minuto
3. Configura volume: 1.0 (máximo)
4. Salva texto como `output.wav`
5. Executa `runAndWait()` (processa a fila de comandos da engine)
6. Reproduz `output.wav` com `winsound` (somente Windows)
7. Remove `output.wav` após reprodução

**Bug conhecido**: `await winsound.PlaySound(...)` está errado — `winsound` não é async. Ver [Gotchas](gotchas.md).

---

### Normalização de Texto (Utilitário)
**Descrição**: Funções auxiliares para comparação de strings sem sensibilidade a acentos ou capitalização.

**Componentes Envolvidos**: `speech_to_text.py:9-21`

```python
remove_acentos(texto)           # Normaliza NFD e remove caracteres Mn
verificar_palavra(frase, palavra)  # Busca substring ignorando acentos e case
```

---

## Funcionalidades Planejadas

### Arquivo Pai / Orquestrador
**Descrição**: Um `main.py` central que integre os módulos STT e TTS em um único loop de execução.

**Fluxo esperado**:
```
Loop contínuo:
  1. STT ouve microfone
  2. Detecta wake word "Palio"
  3. Identifica comando ou encaminha para LLM
  4. Executa ação
  5. TTS confirma ação em voz
  6. Volta ao passo 1
```

---

### Wake Word Personalizada: "Palio"
**Descrição**: Substituir "carro" por "Palio" como wake word. Avaliar uso do Vosk atual vs. engine dedicada (Porcupine/Picovoice) para melhor precisão e menor consumo de CPU.

**Decisão pendente**: Vosk (simples, já integrado) vs. Porcupine (mais preciso, menor CPU, mas requer chave de API para uso comercial).

---

### Integração com LLM Local (Ollama)
**Descrição**: Enviar comandos/perguntas não mapeadas para um LLM local rodando no Rock Pi 4B via Ollama (LLaMA/Mistral quantizado).

**Fluxo esperado**:
```
Fala → STT → "Palio, qual é a capital da França?" 
→ Não é comando mapeado 
→ Envia para Ollama API local 
→ Recebe resposta 
→ TTS fala a resposta
```

**Interface**: Ollama expõe API REST em `http://localhost:11434`

---

### Controle de Música via Bluetooth
**Descrição**: Controlar música tocando no celular conectado ao carro via Bluetooth. Comandos: próxima, anterior, pausar, tocar, aumentar/diminuir volume.

**Tecnologia prevista**: MPRIS (Linux) ou controle Bluetooth AVRCP

---

### Controle de Volume
**Descrição**: Aumentar ou diminuir volume do sistema por voz.

**Tecnologia prevista**: `subprocess` com `amixer` (Linux/Rock Pi) ou `pulsectl`

---

### Navegação GPS
**Descrição**: Abrir app de navegação e definir destino por voz.

**A SER COMPLETADO**: Tecnologia e integração a definir. Possível uso de `subprocess` para abrir Google Maps / OsmAnd no celular via ADB ou API.

---

### Fazer/Atender Ligações
**Descrição**: Controle de chamadas telefônicas por voz.

**A SER COMPLETADO**: Requer integração com Bluetooth HFP (Hands-Free Profile). Tecnologia a definir.

---

### Relatório de Hora, Data e Clima
**Descrição**: Responder perguntas como "que horas são?" ou "como está o tempo?" por voz.

- **Hora/Data**: `datetime` da stdlib Python (offline)
- **Clima**: Requer API externa (OpenWeatherMap ou similar) — depende de conectividade

---

## Funcionalidades Deprecated / Removidas

Nenhuma funcionalidade foi explicitamente deprecada até o momento.

---

## Evolução do Projeto por Versão

| Versão | Descrição                                    |
|--------|----------------------------------------------|
| v0.0.1 | Criação dos módulos TTS e STT iniciais        |
| v0.0.2 | TTS offline com pyttsx3                       |
| v0.0.3 | Melhorias gerais                              |
| v0.0.4 | Comandos de voz básicos                       |
| v0.0.5 | Speech (melhorias STT)                        |
| v0.0.6 | STT offline com Vosk                          |
| v0.0.7 | Voz e reconhecimento configurados (atual)     |
| Futuro | Integração dos módulos + LLM + Bluetooth      |
