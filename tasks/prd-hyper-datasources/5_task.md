# Tarefa 5.0: Tools de mutação — `append_to_hyper` e `execute_hyper_sql`

## Visão geral

Implementar as duas tools de modificação de `.hyper` existentes em `tools/hyper.py`: `append_to_hyper` (acrescenta dados de arquivo CSV/Parquet **ou** inline a uma tabela existente, com validação de compatibilidade de schema) e `execute_hyper_sql` (INSERT/UPDATE/DELETE/CREATE TABLE AS com linhas afetadas). Reutilizam integralmente o engine (tarefa 2.0) e as validações/salvaguardas já prontas (tarefas 1.0 e 4.0).

<skills>
### Conformidade com skills

- `code-standards` — tools finas reutilizando engine e validações existentes, parâmetros mutuamente exclusivos validados com `VALIDATION_ERROR` claro, docstring-contrato orientando a separação `query_hyper` × `execute_hyper_sql`.
- `testing-standards` — engine mockado, casos de fronteira das origens mutuamente exclusivas, nomenclatura padrão.
</skills>

<requirements>
- RF18 — append de dados a tabela existente, de arquivo local ou inline, validando compatibilidade de schema.
- RF19 — comandos SQL de modificação (INSERT, UPDATE, DELETE) com número de linhas afetadas.
- RF20 — criação de tabelas derivadas (`CREATE TABLE ... AS`) a partir de consultas sobre tabelas existentes.
- RF23–RF24 — salvaguardas de volume nas origens do append (mesmos limiares de arquivo/inline).
</requirements>

## Subtarefas

- [ ] 5.1 Implementar `append_to_hyper(hyper_path, table_name, source_path=None, columns=None, rows=None, confirm_large_operation=False)` → `HyperMutationResult | VolumeAlert | ToolError`: exatamente uma origem (arquivo XOR inline); nenhuma ou ambas → `VALIDATION_ERROR`.
- [ ] 5.2 Validar compatibilidade de schema origem × tabela alvo antes de gravar (`HYPER_SCHEMA_MISMATCH` com colunas divergentes); tabela inexistente → `NOT_FOUND`; suportar `table_name` qualificado (`schema.tabela`).
- [ ] 5.3 Integrar salvaguardas de volume da origem correspondente (`check_source_file` ou `check_inline_rows`) com fluxo `VolumeAlert`/confirmação.
- [ ] 5.4 Implementar `execute_hyper_sql(hyper_path, command)` → `HyperMutationResult | ToolError`: primeira palavra-chave em {INSERT, UPDATE, DELETE, CREATE}; `SELECT` rejeitado orientando `query_hyper`; demais palavras-chave (ex.: DROP) → `VALIDATION_ERROR`; `operation` derivada da palavra-chave; um único comando por chamada.
- [ ] 5.5 Escrever testes unitários (casos 69–77) em `tests/tools/test_hyper.py`.

## Detalhes de implementação

Ver techspec.md, seções "`append_to_hyper`" e "`execute_hyper_sql`" em "Endpoints da API" (parâmetros, regras, tabelas de respostas e exemplo de tabela derivada) e "`HyperMutationResult`" em "Modelos de dados" (`affected_rows` nulo para DDL; `CREATE TABLE AS` reporta linhas materializadas quando disponível).

## Critérios de sucesso

- Append valida schema antes de gravar; nenhum dado parcial em caso de incompatibilidade.
- `execute_hyper_sql` cobre as quatro operações com `operation` correta e `affected_rows` preenchido quando disponível.
- Guardas de palavra-chave nas duas direções (`SELECT` → `query_hyper`; escrita → `execute_hyper_sql`) com mensagens que orientam o agente.
- Suite rápida verde; cobertura ≥ 80%; `ruff` limpo.

## Testes da tarefa

### Testes unitários

`tests/tools/test_hyper.py` (casos 69–77 da techspec, engine mockado):

- [ ] 69. `test_append_to_hyper_inline_sucesso_retorna_affected_rows`
- [ ] 70. `test_append_to_hyper_de_arquivo_sucesso`
- [ ] 71. `test_append_to_hyper_sem_origem_retorna_validation_error`
- [ ] 72. `test_append_to_hyper_com_duas_origens_retorna_validation_error`
- [ ] 73. `test_append_to_hyper_tabela_inexistente_retorna_not_found`
- [ ] 74. `test_execute_hyper_sql_update_retorna_linhas_afetadas`
- [ ] 75. `test_execute_hyper_sql_create_table_as_retorna_operation_create_table_as`
- [ ] 76. `test_execute_hyper_sql_select_retorna_validation_error_orientando_query_hyper`
- [ ] 77. `test_execute_hyper_sql_palavra_chave_drop_retorna_validation_error`

### Testes de integração

- Runtime real coberto na tarefa 8.0 (casos 88 — append/derivação — e 90 — UPDATE/DELETE refletidos no `row_count`).

### Testes E2E (se aplicável)

- Não aplicável.

## Arquivos relevantes

- `src/mcp_tableau/tools/hyper.py` — modificado (novas tools)
- `tests/tools/test_hyper.py` — modificado
- `src/mcp_tableau/hyper/engine.py` — dependência (tarefa 2.0)
- `src/mcp_tableau/validation/volume.py` / `models.py` — dependências (tarefa 1.0)
