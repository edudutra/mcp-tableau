# Tarefa 7.0: Tools — Capacidade 3 QA (`tools/qa.py`)

## Visão geral

Implementa as ferramentas MCP de validação estrutural e auditoria de complexidade (Capacidade 3),
que orquestram download via `TableauClient` (Tarefa 2.0), as funções puras
`validation/structure.py` e `validation/complexity.py` (Tarefa 4.0) e a Metadata API
(Tarefa 3.0): `inspect_workbook_structure` baixa o workbook publicado, parseia o XML e combina
com a Metadata API para reportar estrutura e problemas; `audit_workbook_complexity` audita
métricas contra limiares de config. Campos quebrados/filtros sem lógica aparecem em `issues` sem
falhar a ferramenta (objetivo é diagnóstico, não bloqueio).

<skills>
### Conformidade com skills

- **`code-standards`** — ferramentas finas que orquestram download + validação + metadata;
  acesso ao Tableau só via camada `tableau/`; erros acionáveis.
- **`testing-standards`** — client e metadata mockados, validação real; nomenclatura padrão.
</skills>

<requirements>
- **RF13**: Ler estrutura interna do workbook (campos, filtros, conexões).
- **RF14**: Identificar campos quebrados, filtros sem lógica e conexões inválidas (em `issues`,
  sem falhar).
- **RF15**: Auditar indicadores de complexidade contra parâmetros de boas práticas.
- **RF16**: Retornar avaliação de conformidade, sinalizando riscos de performance.
- **RF22/RF23**: Status explícito e erro acionável tipado.
</requirements>

## Subtarefas

- [ ] 7.1 `inspect_workbook_structure(workbook_id)`: baixar workbook (`TableauClient`), chamar
  `inspect_structure` e combinar com a Metadata API para campos quebrados resolvidos pelo
  servidor; retornar `StructureReport`. `NOT_FOUND`/`UPSTREAM_ERROR` em falha.
- [ ] 7.2 Garantir que `issues` (campos quebrados/filtros sem lógica) **não** falham a
  ferramenta — populam o relatório com `severity`/`target`.
- [ ] 7.3 `audit_workbook_complexity(workbook_id)`: obter estrutura, chamar `audit_complexity`
  com os limiares da `Settings` (Tarefa 1.0) e retornar `ComplexityReport`
  (`compliant` true/false + `findings`).
- [ ] 7.4 Registrar as tools no `server.py`.

## Detalhes de implementação

Ver techspec.md § "Endpoints da API" → `inspect_workbook_structure`, `audit_workbook_complexity`;
§ "Modelos de dados" → `StructureReport`, `StructureIssue`, `ComplexityReport`; e
§ "Principais decisões" (QA estrutural híbrido: XML local + Metadata API).

## Critérios de sucesso

- `inspect_workbook_structure` baixa, parseia e retorna `StructureReport`.
- Workbook inexistente retorna `NOT_FOUND`.
- Presença de `issues` não falha a ferramenta.
- `audit_workbook_complexity` retorna `compliant` conforme métricas e usa thresholds de config.

## Testes da tarefa

### Testes unitários

- [ ] `test_inspect_workbook_structure_baixa_e_parseia_retorna_report`
- [ ] `test_inspect_workbook_structure_workbook_inexistente_retorna_not_found`
- [ ] `test_inspect_workbook_structure_issues_nao_falham_ferramenta`
- [ ] `test_audit_workbook_complexity_retorna_compliant_conforme_metricas`
- [ ] `test_audit_workbook_complexity_usa_thresholds_de_config`

### Testes de integração

- [ ] (Tarefa 9.0) Cobertura via suite MCP in-memory (contrato/serialização das tools de QA,
  client/metadata mockados).

## Arquivos relevantes

- `src/mcp_tableau/tools/qa.py`
- `src/mcp_tableau/server.py` (registro das tools)
- `tests/tools/test_qa.py`
