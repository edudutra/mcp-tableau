# Tarefa 3.0: Tools de leitura — `inspect_hyper_schema` e `query_hyper`

## Visão geral

Criar `tools/hyper.py` com a função `register(mcp)` e as duas primeiras tools (somente leitura): `inspect_hyper_schema` (relatório estrutural completo, análogo local do `inspect_workbook_structure`) e `query_hyper` (consulta SQL de leitura com truncamento informado). É o caminho de menor risco para validar a integração com o engine e estabelece o padrão de tools finas, docstring-contrato e tradução de erros que as tarefas 4.0–6.0 seguirão.

<skills>
### Conformidade com skills

- `code-standards` — tools finas com docstring-contrato (orienta o agente a escolher a tool correta), validação de entrada antes de abrir sessão, envelope `ToolError` para erros, registro via `register(mcp)` sem acoplar ao singleton.
- `testing-standards` — engine mockado (padrão fixture `client`/`session` de `test_deploy.py`), resultado vazio como sucesso, cobertura ≥ 80%.
</skills>

<requirements>
- RF13 — consultas SQL de leitura sobre `.hyper` com resultados estruturados (colunas, tipos e linhas).
- RF14 — limite de linhas retornadas por padrão (`HYPER_MAX_RESULT_ROWS`, parâmetro `max_rows` 1–10.000), com truncamento informado (`truncated=true`).
- RF15 — erro estruturado com a mensagem original do motor SQL quando a consulta for inválida.
- RF16 — listagem de todos os schemas e tabelas com colunas, tipos, nulabilidade e contagem de linhas por tabela.
- RF17 — erro estruturado (`HYPER_INVALID_FILE`) quando o arquivo não for um `.hyper` válido.
</requirements>

## Subtarefas

- [ ] 3.1 Criar `src/mcp_tableau/tools/hyper.py` com `register(mcp: FastMCP)` no padrão dos módulos existentes de `tools/`.
- [ ] 3.2 Implementar `inspect_hyper_schema(hyper_path)` → `HyperSchemaReport | ToolError` (contagem de linhas `null` por tabela quando falhar, sem abortar o relatório).
- [ ] 3.3 Implementar `query_hyper(hyper_path, query, max_rows=None)` → `HyperQueryResult | ToolError`, com guarda de leitura por palavra-chave inicial (`SELECT`/`WITH`; caso contrário `VALIDATION_ERROR` orientando `execute_hyper_sql`) e default de `max_rows` vindo de `Settings`.
- [ ] 3.4 Documentar nas docstrings: truncamento (orientar `LIMIT`/agregações), resultado vazio como sucesso, guarda de leitura.
- [ ] 3.5 Escrever testes unitários das duas tools com engine mockado (`tests/tools/test_hyper.py`, casos 61–68).

## Detalhes de implementação

Ver techspec.md, seções "`query_hyper`" e "`inspect_hyper_schema`" em "Endpoints da API" (parâmetros, regras e tabelas de respostas), decisão 7 ("guarda de leitura por palavra-chave — ergonomia, não segurança") e o padrão de degradação de `HyperTableInfo.row_count` em "Modelos de dados".

## Critérios de sucesso

- As duas tools registradas e funcionais via `register(mcp)`.
- Consulta com mais linhas que `max_rows` retorna `truncated=true` e nunca estoura o contexto do agente.
- Resultado vazio é sucesso com `rows=[]` (espelha `search_similar_content`).
- Comando de escrita em `query_hyper` retorna `VALIDATION_ERROR` com orientação para `execute_hyper_sql`.
- Arquivo inválido retorna `HYPER_INVALID_FILE` com mensagem acionável.
- Suite rápida verde; cobertura ≥ 80%; `ruff` limpo.

## Testes da tarefa

### Testes unitários

`tests/tools/test_hyper.py` (casos 61–68 da techspec, engine mockado):

- [ ] 61. `test_query_hyper_sucesso_retorna_colunas_e_linhas`
- [ ] 62. `test_query_hyper_resultado_vazio_e_sucesso`
- [ ] 63. `test_query_hyper_comando_de_escrita_retorna_validation_error_orientando_execute_hyper_sql`
- [ ] 64. `test_query_hyper_max_rows_default_vem_de_settings`
- [ ] 65. `test_query_hyper_max_rows_fora_do_intervalo_retorna_validation_error`
- [ ] 66. `test_query_hyper_sql_invalido_retorna_hyper_sql_error_com_mensagem_do_motor`
- [ ] 67. `test_inspect_hyper_schema_sucesso_retorna_relatorio_completo`
- [ ] 68. `test_inspect_hyper_schema_arquivo_invalido_retorna_hyper_invalid_file`

### Testes de integração

- Serialização via transporte MCP coberta na tarefa 7.0 (`tests/test_mcp_integration.py`, caso 85 usa `query_hyper`).
- Runtime real coberto na tarefa 8.0 (caso 87 inclui inspeção e consulta).

### Testes E2E (se aplicável)

- Não aplicável.

## Arquivos relevantes

- `src/mcp_tableau/tools/hyper.py` — novo (criado nesta tarefa; estendido em 4.0–6.0)
- `tests/tools/test_hyper.py` — novo (criado nesta tarefa; estendido em 4.0–6.0)
- `src/mcp_tableau/hyper/engine.py` — dependência (tarefa 2.0)
- `src/mcp_tableau/models.py` / `src/mcp_tableau/config.py` — dependências (tarefa 1.0)
