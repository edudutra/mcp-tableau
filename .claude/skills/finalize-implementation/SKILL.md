---
name: finalize-implementation
description: Finaliza implementações com commit conventional, screenshots Playwright, checklist de qualidade e abertura de pull request via gh CLI usando o template da empresa. Use quando o usuário pedir para finalizar, commitar, abrir PR, capturar screenshots, encerrar implementação, ou mencionar "finalize", "commit final", "pull request", "gh" ou "conventional commits".
---

# Finalize Implementation

Encerra uma implementação com validação, **screenshots Playwright**, commit Conventional Commits e PR via **`gh` CLI** + [TEMPLATE.md](TEMPLATE.md).

**Só commitar ou abrir PR quando o usuário pedir explicitamente.**

## Ferramentas obrigatórias

| Ferramenta | Uso |
| ---------- | --- |
| **`gh`** | **Todas** as operações GitHub: auth, repo, PR create/view/checks, labels, reviewers |
| `git` | Apenas working tree local: status, diff, add, commit |
| **Playwright** | Screenshots da UI implementada (script em `scripts/`) |

**Regra:** nunca abrir PR pelo browser manualmente se `gh` estiver disponível. Nunca usar API REST/curl para GitHub quando existir comando `gh` equivalente.

Verificar antes de abrir PR:

```bash
gh auth status
gh repo view --json nameWithOwner,defaultBranchRef
```

---

## Restrições do repositório

- **Nunca** executar: `git restore`, `git rm`, `git stash`, `git checkout`
- **Nunca** alterar `git config`
- **Nunca** `--no-verify`, force-push em `main`/`master`, ou comandos destrutivos sem pedido explícito
- **Nunca** commitar `.env`, credenciais ou secrets
- **Nunca** commitar `scripts/node_modules/` da skill

---

## Fluxo

```
1. Pré-validação
2. Screenshots (Playwright) — se houver mudança visual/frontend
3. Commit final
4. Push (git) + PR (gh)
```

---

## 1. Pré-validação

| Alteração | Comandos |
| --------- | -------- |
| Backend | `cd backend && npm test` |
| Frontend | `cd frontend && npm test && npm run lint && npm run typecheck` |

Revisar contra `code-standards`, `react` e `tests` quando relevante.

Se algo falhar, corrigir antes de continuar.

---

## 2. Screenshots com Playwright

**Obrigatório** quando a implementação altera UI (`frontend/src/pages`, `components`, estilos). Para backend-only, pular e documentar evidência textual no template.

### 2.1 Preparar ambiente

1. Backend rodando em `http://localhost:3000` (se a UI depende da API)
2. Frontend acessível — preferir build estável:

```bash
cd frontend && npm run build && npm run preview -- --port 5173
```

Alternativa rápida: `npm run dev` na porta 5173.

3. Instalar Playwright (primeira vez ou após limpar `node_modules`):

```bash
cd .claude/skills/finalize-implementation/scripts
npm install
npm run install-browser
```

### 2.2 Capturar

Escolher `--slug` descritivo (kebab-case, ex.: `weather-panel`, `api-status-indicator`).

```bash
cd .claude/skills/finalize-implementation/scripts
node capture-screenshots.mjs \
  --slug <feature-slug> \
  --routes / \
  --url http://localhost:5173 \
  --mobile
```

| Flag | Descrição |
| ---- | --------- |
| `--slug` | Pasta em `.github/pr-screenshots/<slug>/` |
| `--routes` | Rotas separadas por vírgula (`/`, `/settings`) |
| `--url` | Base URL do app |
| `--mobile` | Captura adicional 390×844 |

Saída: PNGs em `.github/pr-screenshots/<slug>/` + `manifest.json` com `markdownSection` pronto para colar na PR.

### 2.3 Incluir na PR

1. **Commitar** os PNGs na branch da feature (links relativos na description dependem disso)
2. Copiar `markdownSection` do manifest para a seção **Screenshots / evidências** do [TEMPLATE.md](TEMPLATE.md)
3. Marcar checklist: "Screenshots Playwright capturados"

Paths na description usam formato:

```markdown
![Home — desktop](./.github/pr-screenshots/<slug>/home-desktop.png)
```

GitHub renderiza imagens commitadas na mesma branch.

---

## 3. Commit final (Conventional Commits)

### Formato

```
<type>(<scope>): <subject>

[body opcional — 1–3 frases explicando o porquê]
```

| Campo | Regra |
| ----- | ----- |
| `type` | `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `ci`, `build` |
| `scope` | `backend`, `frontend`, `auth`, `health`, `api`, etc. |
| `subject` | Imperativo, minúsculas, sem ponto final, máx. ~72 chars |

Incluir screenshots no **mesmo commit** da feature ou em commit `chore` imediatamente anterior ao PR — nunca deixar PNGs só locais.

### Procedimento

1. Em paralelo: `git status`, `git diff`, `git log -5 --oneline`
2. Staging dos arquivos relevantes + `.github/pr-screenshots/<slug>/`
3. Commit via HEREDOC:

```bash
git commit -m "$(cat <<'EOF'
feat(scope): subject here

Optional body explaining why.
EOF
)"
```

4. Hook falhou → corrigir e **novo** commit (não `--amend` salvo regras do usuário)

---

## 4. Push e Pull Request via `gh`

### 4.1 Coletar contexto com `gh` + `git`

Em paralelo:

```bash
git status
git diff
git log "$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)...HEAD" --oneline
git diff "$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)...HEAD"
gh pr list --head "$(git branch --show-current)" --json number,url
```

Entender **todos** os commits da branch. Se PR já existe, usar `gh pr edit` em vez de `gh pr create`.

### 4.2 Push

```bash
git push -u origin HEAD
```

`gh pr create` pode oferecer push interativo, mas em automação fazer push explícito antes.

### 4.3 Montar description

1. Ler [TEMPLATE.md](TEMPLATE.md)
2. Preencher todas as seções (sem placeholders)
3. Colar `markdownSection` do Playwright em **Screenshots / evidências**
4. Marcar checklist verificado

Salvar body preenchido em arquivo temporário (ex.: `/tmp/pr-body.md`) — **não** alterar o TEMPLATE.md no repo.

### 4.4 Criar ou atualizar PR

Base branch via `gh`:

```bash
BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
```

**Nova PR:**

```bash
gh pr create \
  --base "$BASE" \
  --title "feat(scope): short description" \
  --body-file /tmp/pr-body.md
```

**PR já aberta:**

```bash
gh pr edit <number> --body-file /tmp/pr-body.md
```

Comandos úteis pós-criação:

```bash
gh pr view --web
gh pr checks
gh pr status
```

Flags opcionais: `--draft`, `--reviewer`, `--label`, `--assignee "@me"`.

### 4.5 Resposta ao usuário

Retornar URL da PR (`gh pr view --json url -q .url`). Resumir: validações, screenshots capturados, checklist pendente.

---

## Checklist rápido do agente

- [ ] `gh auth status` OK
- [ ] Testes/lint/typecheck conforme escopo
- [ ] Playwright: screenshots commitados + markdown na description (se UI)
- [ ] Commit Conventional Commits
- [ ] Nenhum secret no diff
- [ ] PR via `gh pr create` ou `gh pr edit` com TEMPLATE.md preenchido
- [ ] URL da PR retornada

---

## Referência — `gh` vs `git`

| Ação | Comando |
| ---- | ------- |
| Branch default | `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` |
| Criar PR | `gh pr create --base ... --title ... --body-file ...` |
| Editar PR | `gh pr edit <n> --body-file ...` |
| Ver PR atual | `gh pr view` |
| Listar PRs da branch | `gh pr list --head "$(git branch --show-current)"` |
| Status CI | `gh pr checks` |
| Auth | `gh auth status` |
| Status/diff/commit | `git status`, `git diff`, `git commit` |
| Push | `git push -u origin HEAD` |

---

## Scopes comuns neste projeto

| Scope | Uso |
| ----- | --- |
| `backend` | Express, routes, services, data |
| `frontend` | React, pages, components, hooks |
| `health` | Endpoint /health e indicadores |
| `deps` | Dependências npm |
| `ci` | Pipelines e automação |
