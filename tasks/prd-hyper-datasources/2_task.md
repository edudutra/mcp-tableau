# Tarefa 2.0: Engine Hyper (`hyper/engine.py`)

## Visão geral

Criar o pacote `hyper/` com o wrapper da `tableauhyperapi` (análogo a `tableau/client.py`): context manager `hyper_session()` que inicia/encerra o `HyperProcess` por chamada (telemetria desativada), operações de alto nível (criar tabela de arquivo/inline, append, query, execute, describe) e tradução de `HyperException` para `HyperEngineError(code, message)` sem vazar paths internos do runtime. Inclui a adição da dependência `tableauhyperapi>=0.0.23576` ao `pyproject.toml`.

<skills>
### Conformidade com skills

- `code-standards` — integração externa isolada em módulo próprio (`hyper/` análogo a `tableau/`), context manager para ciclo de vida do processo, tradução de erros com mensagens acionáveis sem dados sensíveis, type hints nativos, `ruff`.
- `testing-standards` — `tableauhyperapi` mockada na suite rápida (módulo inteiro via `monkeypatch`/`sys.modules`), `tmp_path` para paths, nomenclatura padrão.
</skills>

<requirements>
- RF1–RF3 — mecânica de criação de tabela de CSV (COPY FROM com delimitador/encoding/header) e Parquet, inferência via `external()` e schema explícito via `TableDefinition`.
- RF6 — inserção de linhas inline via `Inserter`.
- RF13–RF14 — query de leitura com `max_rows+1` para detecção de truncamento; serialização de tipos (datas ISO-8601, `NUMERIC` como string).
- RF16 — introspecção do catálogo (schemas, tabelas, colunas, contagens; contagem que falha vira `None` sem abortar).
- RF15, RF17–RF20 — execução de comandos com linhas afetadas e tradução de erros do motor (`HYPER_SQL_ERROR`, `HYPER_INVALID_FILE`, `HYPER_SCHEMA_MISMATCH`).
</requirements>

## Subtarefas

- [x] 2.1 Adicionar `tableauhyperapi>=0.0.23576` ao `pyproject.toml` e criar o pacote `src/mcp_tableau/hyper/` (`__init__.py`).
- [x] 2.2 Implementar `hyper_session()` — inicia `HyperProcess` com `Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU`, entrega `HyperEngine`, encerra o processo mesmo com exceção.
- [x] 2.3 Implementar criação de tabela: `create_table_from_file` (CSV com schema → `TableDefinition` + `COPY FROM`; CSV sem schema e Parquet → `CREATE TABLE AS SELECT * FROM external(...)`; path escapado com `escape_string_literal`) e `create_table_from_rows` (via `Inserter`).
- [x] 2.4 Implementar `append_rows` com validação de compatibilidade de schema antes de inserir.
- [x] 2.5 Implementar `query` (lê `max_rows+1`, sinaliza truncamento, serializa tipos para JSON), `execute` (linhas afetadas) e `describe` (catálogo completo, contagem tolerante a falha).
- [x] 2.6 Implementar tradução de `HyperException` → `HyperEngineError` com `ErrorCode` adequado, preservando a `main_message` do motor e removendo paths internos do runtime.
- [x] 2.7 Implementar o mapeamento bidirecional tipos do contrato ↔ `SqlType`/`TypeTag` (tabela da techspec; tipos não mapeados expostos como `text` do nome bruto).
- [x] 2.8 Escrever testes unitários com `tableauhyperapi` mockada (`tests/hyper/test_engine.py`).

## Detalhes de implementação

Ver techspec.md, seções "Principais interfaces" (assinaturas de `HyperEngine`/`hyper_session`/`HyperEngineError`), "Parâmetros fixados no upstream" (`HyperProcess`, `Connection` com `create_mode` por operação, `COPY FROM`, `external()`) e "Mapeamento tipos do contrato → `tableauhyperapi.SqlType`". Decisão 5 ("`HyperProcess` por chamada") e decisão 8 ("inferência via `external()` + carga via `COPY`") em "Principais decisões".

## Critérios de sucesso

- `hyper_session()` nunca deixa processo Hyper residente, inclusive em exceção.
- Todas as operações da interface `HyperEngine` funcionais e testadas com mocks.
- Nenhuma mensagem de `HyperEngineError` contém paths internos do runtime Hyper.
- Serialização de valores: `DATE`/`TIMESTAMP` → ISO-8601; `NUMERIC` → `str` (preservação de precisão).
- Suite rápida verde sem exigir o runtime Hyper instalado no CI; cobertura ≥ 80%; `ruff` limpo.

## Testes da tarefa

### Testes unitários

`tests/hyper/test_engine.py` (casos 18–34 da techspec, `tableauhyperapi` mockada):

- [x] 18. `test_hyper_session_inicia_processo_com_telemetria_desativada`
- [x] 19. `test_hyper_session_encerra_processo_mesmo_com_excecao`
- [x] 20. `test_create_table_from_file_csv_com_schema_usa_copy_com_delimitador_e_encoding`
- [x] 21. `test_create_table_from_file_csv_sem_schema_usa_external_para_inferencia`
- [x] 22. `test_create_table_from_file_parquet_usa_external`
- [x] 23. `test_create_table_from_file_escapa_path_com_escape_string_literal`
- [x] 24. `test_create_table_from_rows_insere_via_inserter_e_retorna_contagem`
- [x] 25. `test_append_rows_valida_compatibilidade_antes_de_inserir`
- [x] 26. `test_append_rows_schema_incompativel_levanta_hyper_schema_mismatch`
- [x] 27. `test_query_le_max_rows_mais_um_e_sinaliza_truncamento`
- [x] 28. `test_query_serializa_date_e_timestamp_como_iso8601`
- [x] 29. `test_query_serializa_numeric_como_string`
- [x] 30. `test_execute_retorna_linhas_afetadas`
- [x] 31. `test_describe_lista_todos_schemas_e_tabelas_com_colunas`
- [x] 32. `test_describe_contagem_de_linhas_falha_vira_none_sem_abortar`
- [x] 33. `test_hyper_exception_traduzida_para_hyper_engine_error_com_mensagem_original`
- [x] 34. `test_arquivo_nao_hyper_traduzido_para_hyper_invalid_file`

### Testes de integração

- Cobertos na tarefa 8.0 (`tests/integration/test_hyper_real.py`, runtime Hyper real via `@pytest.mark.integration`).

### Testes E2E (se aplicável)

- Não aplicável.

## Arquivos relevantes

- `src/mcp_tableau/hyper/__init__.py` — novo
- `src/mcp_tableau/hyper/engine.py` — novo
- `pyproject.toml` — modificado (`tableauhyperapi`)
- `tests/hyper/test_engine.py` — novo
- `src/mcp_tableau/models.py` — dependência (contratos e `ErrorCode` da tarefa 1.0)
