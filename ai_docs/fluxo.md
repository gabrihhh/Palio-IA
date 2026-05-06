# Fluxo do Sistema — Palio-IA

Diagrama completo do fluxo de execução do assistente de voz, do boot à resposta.

```mermaid
flowchart TD
    BOOT([Inicialização\nmain.py]) --> AUTOCON["autoconnect_boot()\ntenta conectar dispositivo salvo\nsilenciosamente"]
    AUTOCON --> BIPES["Dois bipes de boot\ntocar_boot()"]
    BIPES --> S1_CAP

    subgraph S1["Estágio 1 — Escuta contínua"]
        S1_CAP["Captura áudio\nPyAudio · CHUNK 1024"] --> S1_DSP["Resample → 16kHz\nresample_poly · 48kHz→16kHz"]
        S1_DSP --> S1_BP["Bandpass 300–3400Hz\nbandpass_filter()"]
        S1_BP --> S1_VAD{Energia\nacima do threshold?}
        S1_VAD -- Não --> S1_CAP
        S1_VAD -- Sim --> S1_STT["Acumula buffer de fala\npre-buffer 0.3s"]
        S1_STT --> S1_SIL{Silêncio\n≥ 0.8s?}
        S1_SIL -- Não --> S1_STT
        S1_SIL -- Sim --> S1_TRANS["Pré-ênfase + Transcreve utterance\nfaster-whisper small · initial_prompt"]
        S1_TRANS --> S1_WW{Contém wake word\n'carro'?\nsubstring + fuzzy ≥75%}
        S1_WW -- Não --> S1_CAP
    end

    S1_WW -- Sim --> DUCK["AudioDuck → 20%\non_wake_word() · pactl"]
    DUCK --> WAIT["Aguarda 0.4s\nDUCK_WAIT"]
    WAIT --> S2_CAP

    subgraph S2["Estágio 2 — Captura de comando (timeout 5s)"]
        S2_CAP["Captura próximo utterance\nfaster-whisper small"] --> S2_OK{Fala\ndetectada?}
        S2_OK -- Timeout 5s --> S2_TO["Restaura volume\non_timeout()"]
    end

    S2_TO --> S1_CAP
    S2_OK -- Sim --> DISP

    subgraph DISPATCH["Dispatcher — Roteamento de intenção\nmodules/core/dispatcher.py"]
        DISP{Tipo de\nintenção?}
        DISP -- "modo pareamento /\nconectar" --> PAIR["PairingManager\nbluetooth pairing · bluetoothctl\nmodules/bluetooth/pairing.py"]
        DISP -- "aumenta / diminui /\nvolume N" --> VOL["VolumeController\npactl · steps 10%\nmodules/bluetooth/audio.py"]
        DISP -- "próxima / pausa /\ntoca / volta..." --> MUSIC["BluetoothMusicController\nAVRCP · dbus · bluez\nmodules/bluetooth/music.py"]
        DISP -- tudo o mais --> LLM["OllamaClient\nllama3.2:3b · histórico multi-turno\nmodules/llm/client.py"]
    end

    PAIR --> TTS
    VOL --> VPEND(["Volume pendente\naplicado após TTS"])
    MUSIC --> TTS
    LLM --> CLEAN["_limpar_markdown()\nremove ** # ` bullets\nmain.py"]
    CLEAN --> TTS

    TTS["TTS\npiper-tts ONNX (pt_BR-faber-medium)\nsounddevice · tempfile WAV\nmain.py · falar()"] --> RESTORE["Restaura volume\non_done() · pactl"]
    RESTORE --> VPEND_CHECK{Volume\npendente?}
    VPEND_CHECK -- Não --> S1_CAP
    VPEND --> VPEND_CHECK
    VPEND_CHECK -- Sim --> APPLY["Aplica volume\nVolumeController.aumentar()\n.diminuir() · .set_step()"]
    APPLY --> S1_CAP
```

## Módulos envolvidos

| Módulo | Papel no fluxo |
|---|---|
| `main.py` | Orquestrador: inicializa tudo, cria handlers, roda loop |
| `modules/stt/whisper_backend.py` | Estágios 1 e 2: captura, VAD, transcrição, detecção de wake word |
| `modules/core/dispatcher.py` | Classifica a intenção e roteia para o módulo correto |
| `modules/bluetooth/music.py` | Executa comandos AVRCP via dbus (próxima, pausa, play...) |
| `modules/bluetooth/pairing.py` | Gerencia pareamento e conexão BT por voz |
| `modules/bluetooth/audio.py` | Controla volume do sink padrão via pactl |
| `modules/bluetooth/audio_duck.py` | Duck 20% na wake word, restaura após TTS |
| `modules/llm/client.py` | Chat multi-turno com Ollama local |
| `speech_to_text.py` | Funções compartilhadas: resample, bandpass, pré-ênfase, fuzzy match, seleção de mic |
