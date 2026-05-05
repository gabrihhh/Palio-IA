# Guia de Uso — Palio-IA

O que dá pra fazer com o assistente hoje, do ponto de vista de quem está no carro.

---

## Fluxo de uso

```mermaid
flowchart TD
    LIGA([Liga o carro]) --> BOOT["Sistema inicializa\nDois bipes = pronto"]
    BOOT --> AUTOCON["Tenta conectar celular\nautomaticamente"]
    AUTOCON --> ESCUTA(["Escuta contínua\naguardando 'carro'"])

    ESCUTA --> FALA["Fala: 'carro ...'"]
    FALA --> CMD{O que vem\ndepois?}

    CMD --> GRP_MUS["Controle de música"]
    CMD --> GRP_VOL["Controle de volume"]
    CMD --> GRP_BT["Bluetooth"]
    CMD --> GRP_CONV["Conversa livre"]

    subgraph MUSICA["🎵 Música — celular precisa estar conectado via BT"]
        GRP_MUS --> M1["'próxima' / 'passa'"]
        GRP_MUS --> M2["'volta' / 'anterior'"]
        GRP_MUS --> M3["'pausa' / 'para'"]
        GRP_MUS --> M4["'toca' / 'play'"]
        GRP_MUS --> M5["'que música é essa'"]
    end

    subgraph VOLUME["🔊 Volume"]
        GRP_VOL --> V1["'aumenta' / 'sobe'"]
        GRP_VOL --> V2["'diminui' / 'abaixa'"]
        GRP_VOL --> V3["'volume cinco'\n(1 a 10 = 10% a 100%)"]
    end

    subgraph BLUETOOTH["📱 Bluetooth"]
        GRP_BT --> B1["'conectar'\n→ conecta ao celular salvo"]
        GRP_BT --> B2["'modo de pareamento'\n→ Rock Pi fica visível 60s\npara parear novo celular"]
    end

    subgraph CONVERSA["💬 Conversa — LLM offline"]
        GRP_CONV --> C1["Qualquer pergunta\nou assunto"]
        C1 --> MEM["Palio aprende seu nome\ne preferências ao longo do tempo"]
    end

    M1 & M2 & M3 & M4 --> R_ACT["Palio comenta\na ação"]
    M5 --> R_INFO["'Tá tocando X do Y.'"]
    V1 & V2 & V3 --> R_VOL["Volume ajustado\n(sem resposta em voz)"]
    B1 --> R_CON["'Dispositivo conectado.'\nou 'Não achei o dispositivo.'"]
    B2 --> R_PAR["'Pronto pra parear.\nVocê tem 60 segundos.'"]
    C1 --> R_LLM["Palio responde\ncomo o carro"]

    R_ACT & R_INFO & R_VOL & R_CON & R_PAR & R_LLM & MEM --> ESCUTA
```

---

## Referência rápida de comandos

### Música
| Fala | Ação |
|---|---|
| `carro próxima` / `carro passa` | Pula para a próxima faixa |
| `carro volta` / `carro anterior` | Volta para a faixa anterior |
| `carro pausa` / `carro para` | Pausa a música |
| `carro toca` / `carro play` | Retoma a música |
| `carro que música é essa` | Fala o nome da faixa atual |

### Volume
| Fala | Ação |
|---|---|
| `carro aumenta` / `carro sobe` | +10% |
| `carro diminui` / `carro abaixa` | -10% |
| `carro volume cinco` | Define 50% (escala 1–10) |

### Bluetooth
| Fala | Ação |
|---|---|
| `carro conectar` | Conecta ao celular salvo em `data/devices.json` |
| `carro modo de pareamento` | Torna o Rock Pi visível por 60s para parear |

### Conversa
| Situação | Comportamento |
|---|---|
| Qualquer frase não reconhecida | Envia ao LLM local (Ollama `llama3.2:3b`) |
| Palio aprende seu nome | Salva em `data/brain.md` e lembra nas próximas sessões |
| Ollama offline | `"Meu cérebro tá offline agora."` — música e BT continuam |

---

## Notas de uso

- **Wake word**: sempre começa com `"carro"` — sem ela nenhum comando é executado
- **Timeout**: se não falar nada em até 5s após a wake word, volta a escutar normalmente
- **Boot automático**: ao ligar o carro, o sistema tenta conectar o celular salvo sozinho — sem precisar falar `"carro conectar"`
- **100% offline**: sem internet, sem nuvem, tudo roda no Rock Pi
