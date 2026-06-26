## Summary

<!-- 1–3 frases: o que mudou e por quê. Foque no impacto para o usuário ou negócio. -->

-

## Tipo de mudança

<!-- Marque com [x] o que se aplica -->

- [ ] `feat` — nova funcionalidade
- [ ] `fix` — correção de bug
- [ ] `refactor` — refatoração sem mudança de comportamento
- [ ] `test` — testes
- [ ] `docs` — documentação
- [ ] `chore` — manutenção (deps, config, CI)
- [ ] `perf` — melhoria de performance

## Contexto

<!-- Issue, ticket ou link relacionado. Use "N/A" se não houver. -->

-

## Checklist de implementação

<!-- Toda PR deve marcar os itens aplicáveis. Itens não aplicáveis: deixe desmarcado e explique em "Notas" se necessário. -->

- [ ] Código segue as camadas do projeto (`routes → services → data` no backend; `pages → hooks → services` no frontend)
- [ ] Tipos centralizados em `types/` (sem duplicação entre camadas)
- [ ] Nomenclatura em inglês (identificadores, comentários, mensagens de API)
- [ ] Funções com no máximo 30 linhas; no máximo 3 parâmetros (ou objeto tipado)
- [ ] Testes adicionados ou atualizados para o comportamento alterado
- [ ] `cd backend && npm test` passou
- [ ] `cd frontend && npm test` passou (se frontend foi alterado)
- [ ] `cd frontend && npm run lint && npm run typecheck` passou (se frontend foi alterado)
- [ ] Sem secrets, `.env` ou credenciais no diff
- [ ] Screenshots Playwright capturados e commitados em `.github/pr-screenshots/` (se mudança visual)
- [ ] PR aberta/atualizada via `gh pr create` ou `gh pr edit` (não pelo browser)

## Plano de testes

<!-- Passos concretos para o revisor validar a mudança -->

- [ ]
- [ ]

## Screenshots / evidências

<!-- Obrigatório para mudança de UI: colar markdownSection do manifest Playwright.
     Backend-only: descreva request/response ou output de teste. -->

<!-- Exemplo (UI):

Capturas geradas com Playwright (`<slug>`).

### Desktop (1280×720)

![/ — desktop](./.github/pr-screenshots/<slug>/home-desktop.png)

### Mobile (390×844)

![/ — mobile](./.github/pr-screenshots/<slug>/home-mobile.png)
-->

N/A

## Notas para o revisor

<!-- Decisões de design, trade-offs, follow-ups ou itens do checklist não aplicáveis -->

-

## Breaking changes

<!-- [ ] Sim — descreva abaixo  |  [x] Não -->

Não
