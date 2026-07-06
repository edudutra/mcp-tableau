# Tarefa 6.0: Extração de banco externo — `hyper/db.py` e `extract_database_to_hyper`

## Visão geral

Implementar a extração de bancos de dados externos para `.hyper`: novo módulo `hyper/db.py` (SQLAlchemy Core com `stream_results`, leitura em lotes de 10.000 linhas via `Inserter`, resolução de conexões nomeadas `HYPER_DB_CONN_<NOME>`, sanitização obrigatória de credenciais e classificação de erros conexão × autenticação × SQL) e a tool `extract_database_to_hyper` em `tools/hyper.py`. É a tarefa com maior superfície de erro externa — fica por último entre as tools. Inclui a adição de `sqlalchemy>=2.0` ao `pyproject.toml` (drivers de banco NÃO entram como dependência do projeto).

<skills>
### Conformidade com skills

- `code-standards` — segredos exclusivamente via ambiente (mesmo padrão do PAT), mensagens de erro acionáveis sem dados sensíveis, integração externa isolada em módulo próprio.
- `testing-standards` — SQLAlchemy mockada na suite rápida, asserções sobre `caplog` para garantir não vazamento, teste real com SQLite na tarefa 8.0.
</skills>

<requirements>
- RF9 — materializar em `.hyper` o resultado de query SQL de banco externo configurado via connection string em variável de ambiente.
- RF10 — agnóstico de banco: qualquer fonte com driver compatível via connection string, sem lógica por fornecedor.
- RF11 — credenciais e connection strings nunca aceitas como parâmetro, nem em logs, mensagens de erro ou retornos.
- RF12 — erro estruturado distinguindo falha de conexão (`DB_CONNECTION_FAILED`), autenticação (`DB_AUTH_FAILED`) e SQL (`DB_QUERY_ERROR`).
- RF23/RF25 — alerta pós-execução em `warnings` quando as linhas extraídas excederem `HYPER_MAX_EXTRACT_ROWS` (volume não estimável pré-extração).
</requirements>

## Subtarefas

- [x] 6.1 Adicionar `sqlalchemy>=2.0` ao `pyproject.toml` (core apenas; drivers instalados pelo administrador).
- [x] 6.2 Implementar `resolve_connection(name)` em `hyper/db.py`: lê `HYPER_DB_CONN_<NAME>` (uppercase) de `os.environ` (desvio documentado do padrão `Settings` — decisão 2 da techspec); ausente → `DbConfigError`/`DB_CONNECTION_NOT_CONFIGURED` citando o nome da variável; a URL resolvida nunca é logada nem incluída em exceções.
- [x] 6.3 Implementar `extract_to_hyper(connection_name, query, hyper_path, table_name, batch_size=10_000)`: `create_engine` com `pool_pre_ping=True` e `execution_options(stream_results=True)`, iteração do cursor em lotes gravando via `Inserter` do engine (tarefa 2.0); mapeamento tipos do cursor → `SqlType` com fallback para `text` (com warning); transação somente leitura quando o dialeto suportar.
- [x] 6.4 Implementar classificação de erros: `OperationalError` de rede → `DB_CONNECTION_FAILED`; códigos de autenticação do dialeto → `DB_AUTH_FAILED`; `ProgrammingError`/`DatabaseError` → `DB_QUERY_ERROR`; fallback `DB_CONNECTION_FAILED`. Sanitização obrigatória de toda mensagem (remoção de URL, usuário, senha, host) antes de sair do módulo.
- [x] 6.5 Implementar a tool `extract_database_to_hyper(connection_name, query, hyper_path, table_name="Extract")` → `HyperCreateResult | ToolError` (`source="database"`): rejeitar `connection_name` contendo `://` com `VALIDATION_ERROR`; alerta pós-execução em `warnings` via `check_extracted_rows`.
- [x] 6.6 Escrever testes unitários de `hyper/db.py` (casos 35–45) e da tool (casos 57–60 e 78), incluindo asserção sobre `caplog` + payloads de que nenhum retorno/log contém connection string.

## Detalhes de implementação

Ver techspec.md, seções "Principais interfaces" (`hyper/db.py`), "`extract_database_to_hyper`" em "Endpoints da API", "Pontos de integração" (classificação de exceções SQLAlchemy e sanitização), decisões 1–2 em "Principais decisões" e o risco "Vazamento de credencial em mensagens de driver" em "Riscos conhecidos". Degradação de volume pós-extração documentada em "`HyperCreateResult`" (Modelos de dados).

## Critérios de sucesso

- Zero exposição de credenciais: nenhuma connection string (nem partes: usuário, senha, host) em logs, exceções ou retornos — verificado por teste dedicado (métrica de sucesso do PRD).
- Erros distinguem corretamente as três categorias (RF12), citando apenas o nome lógico da conexão.
- Extração em streaming (lotes de 10.000) sem carregar o resultado inteiro em memória.
- Resultado vazio cria `.hyper` com zero linhas sem erro; extração acima do limiar conclui com warning.
- Suite rápida verde sem SQLAlchemy real conectando a nada; cobertura ≥ 80%; `ruff` limpo.

## Testes da tarefa

### Testes unitários

`tests/hyper/test_db.py` (casos 35–45 da techspec, SQLAlchemy mockada):

- [x] 35. `test_resolve_connection_le_variavel_com_nome_uppercase`
- [x] 36. `test_resolve_connection_ausente_levanta_db_connection_not_configured`
- [x] 37. `test_resolve_connection_nao_loga_nem_inclui_url_na_excecao`
- [x] 38. `test_extract_to_hyper_usa_stream_results_e_lotes`
- [x] 39. `test_extract_to_hyper_mapeia_tipos_do_cursor_para_sqltype`
- [x] 40. `test_extract_to_hyper_tipo_exotico_faz_fallback_para_text`
- [x] 41. `test_operational_error_de_rede_vira_db_connection_failed`
- [x] 42. `test_erro_de_autenticacao_vira_db_auth_failed`
- [x] 43. `test_programming_error_vira_db_query_error_com_mensagem_sanitizada`
- [x] 44. `test_sanitizacao_remove_url_usuario_senha_e_host_da_mensagem`
- [x] 45. `test_resultado_vazio_cria_hyper_com_zero_linhas_sem_erro`

`tests/tools/test_hyper.py` (casos 57–60 e 78, db mockado):

- [x] 57. `test_extract_database_to_hyper_sucesso_retorna_source_database`
- [x] 58. `test_extract_database_to_hyper_connection_name_com_url_retorna_validation_error`
- [x] 59. `test_extract_database_to_hyper_conexao_nao_configurada_retorna_erro_com_nome_da_variavel`
- [x] 60. `test_extract_database_to_hyper_linhas_acima_do_limiar_conclui_com_warning`
- [x] 78. `test_nenhum_retorno_ou_log_contem_connection_string` (asserção sobre caplog + payloads)

### Testes de integração

- Runtime real com SQLite coberto na tarefa 8.0 (caso 91 — SQLAlchemy + SQLite em `tmp_path` como banco externo real).

### Testes E2E (se aplicável)

- Não aplicável.

## Arquivos relevantes

- `src/mcp_tableau/hyper/db.py` — novo
- `src/mcp_tableau/tools/hyper.py` — modificado (nova tool)
- `pyproject.toml` — modificado (`sqlalchemy`)
- `tests/hyper/test_db.py` — novo
- `tests/tools/test_hyper.py` — modificado
- `src/mcp_tableau/hyper/engine.py` — dependência (Inserter em lotes, tarefa 2.0)
- `src/mcp_tableau/validation/volume.py` / `models.py` — dependências (tarefa 1.0)
