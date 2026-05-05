Você vai atualizar a documentação do projeto Palio-IA com base nas mudanças de código desde a última atualização registrada.

## Passo 1 — Ler estado atual

Execute em paralelo:

```bash
cat ai_docs/.docs_hash 2>/dev/null || echo "NENHUM"
```
```bash
git rev-parse HEAD
```
```bash
git log --oneline "$(cat ai_docs/.docs_hash 2>/dev/null)"..HEAD 2>/dev/null | head -20
```

Se `ai_docs/.docs_hash` não existir ou o hash for inválido (git log retornar erro), use o commit mais antigo como base:
```bash
git rev-list --max-parents=0 HEAD
```

**Se HEAD == hash salvo**: informe "documentação já está sincronizada" e encerre aqui.

## Passo 2 — Obter as mudanças

```bash
git diff "$(cat ai_docs/.docs_hash 2>/dev/null)"..HEAD -- '*.py' 'req.txt'
```

Leia o diff completo. Para cada arquivo `.py` que aparece no diff, leia também o arquivo atual (estado final), não apenas o que mudou — você precisa entender o estado atual, não só o delta.

## Passo 3 — Analisar e atualizar os docs

Para cada mudança encontrada, atualize cirurgicamente os arquivos correspondentes:

| Tipo de mudança | Arquivo(s) a atualizar |
|---|---|
| Novo módulo / arquivo `.py` adicionado | `CLAUDE.md` (mapa de módulos) + `ai_docs/features.md` |
| Módulo removido ou renomeado | `CLAUDE.md` + `ai_docs/features.md` |
| Nova feature ou comando de voz | `ai_docs/features.md` |
| Feature planejada que foi implementada | `ai_docs/features.md` (mover Planejadas → Implementadas) + `CLAUDE.md` status |
| Regra de negócio alterada (threshold, formato, validação) | `ai_docs/rules.md` |
| Bug corrigido que era gotcha ativo | `ai_docs/gotchas.md` (remover o item) |
| Novo comportamento não-óbvio ou armadilha | `ai_docs/gotchas.md` (adicionar) |
| Mudança de dependência / biblioteca / versão | `ai_docs/context.md` |
| Decisão arquitetural relevante | `CLAUDE.md` (seção **Decisões Importantes**) |
| Mudança no setup, hardware ou integração | `ai_docs/context.md` |
| Variável de ambiente nova ou modificada | `CLAUDE.md` (tabela de variáveis) |

### Regras obrigatórias para edição

- **Não copiar snippets de código** — referenciar `arquivo:linha` no lugar
- **Não registrar histórico de versões** — isso é o `git log`
- **Editar cirurgicamente** — apenas o que mudou, não reescrever seções inteiras
- **Remover do `gotchas.md`** itens resolvidos quando o bug foi corrigido no código
- **Não adicionar comentários, docstrings ou type hints** nos arquivos `.py`

## Passo 4 — Salvar o novo hash

```bash
git rev-parse HEAD > ai_docs/.docs_hash
```

## Passo 5 — Commitar as mudanças de documentação

Verifique se há arquivos de doc modificados:

```bash
git status --short CLAUDE.md ai_docs/
```

**Se houver mudanças**: faça stage e commit:

```bash
git add CLAUDE.md ai_docs/
git commit -m "[QA] docs: sincroniza documentação com código"
```

**Se não houver mudanças** (docs já estavam corretas): apenas informe que não havia nada a atualizar.

## Passo 6 — Relatório final

Informe ao usuário:
- Intervalo de commits analisados (ex: `a0a19d4..f3b82c1`, N commits)
- Arquivos de doc atualizados e por quê (uma linha cada)
- Se alguma mudança requer decisão humana (decisão arquitetural a registrar, gotcha que precisa de mais contexto)
- Hash salvo: novo valor de `ai_docs/.docs_hash`
