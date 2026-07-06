# Tarefa 1.0: Fundações — contratos, config e salvaguardas de volume

## Visão geral

Criar a base que destrava todas as demais tarefas: novos membros de `ErrorCode`, contratos Pydantic dos retornos das tools Hyper em `models.py`, limiares `HYPER_*` em `Settings` (`config.py`) e o módulo puro de salvaguardas de volume `validation/volume.py`. Nenhuma dependência de biblioteca nova.

<skills>
### Conformidade com skills

- `code-standards` — contratos Pydantic com `status` discriminado (`Literal`), type hints nativos, campos não determináveis normalizados para `null`, mensagens sem dados sensíveis, `ruff` (88 colunas).
- `testing-standards` — testes unitários puros (sem mocks para `validation/volume.py`), nomenclatura `test_<unidade>_<cenario>_<resultado>`, cobertura ≥ 80%.
</skills>

<requirements>
- RF23 — alerta estruturado (não bloqueante) quando operação exceder limiares configuráveis de volume.
- RF24 — alerta indica dimensão excedida e risco associado; prosseguimento só com confirmação explícita (`confirm_large_operation`).
- RF25 — limiares configuráveis por variáveis de ambiente, com defaults conservadores documentados.
- Suporte estrutural aos RF4, RF13–RF14, RF16, RF18–RF20 (contratos de retorno) e aos RF5, RF7, RF12, RF15, RF17 (novos códigos de erro).
</requirements>

## Subtarefas

- [x] 1.1 Adicionar novos membros a `ErrorCode` em `models.py`: `HYPER_INVALID_FILE`, `HYPER_SCHEMA_MISMATCH`, `HYPER_SQL_ERROR`, `DB_CONNECTION_NOT_CONFIGURED`, `DB_CONNECTION_FAILED`, `DB_AUTH_FAILED`, `DB_QUERY_ERROR`.
- [x] 1.2 Criar contratos Pydantic em `models.py`: `HyperColumn`, `InlineColumn`, `HyperCreateResult`, `HyperQueryResult`, `HyperTableInfo`, `HyperSchemaReport`, `HyperMutationResult`, `ExceededDimension`, `VolumeAlert` (campos e exemplos na seção "Modelos de dados" da techspec.md).
- [x] 1.3 Adicionar limiares a `Settings` em `config.py`: `HYPER_MAX_SOURCE_FILE_MB` (500), `HYPER_MAX_INLINE_ROWS` (1.000), `HYPER_MAX_RESULT_ROWS` (200), `HYPER_MAX_EXTRACT_ROWS` (5.000.000), no padrão dos existentes `MAX_FILTERS`/`MAX_WORKSHEETS`.
- [x] 1.4 Criar `src/mcp_tableau/validation/volume.py` com as funções puras `check_source_file`, `check_inline_rows`, `check_extracted_rows` (sem rede/IO além de `stat`), retornando `list[ExceededDimension]`.
- [x] 1.5 Escrever testes unitários de `validation/volume.py` (`tests/validation/test_volume.py`).
- [x] 1.6 Estender `tests/test_config.py` e `tests/test_models.py` com os casos dos novos limiares e contratos.

## Detalhes de implementação

Ver techspec.md, seções "Modelos de dados" (tabelas de campos e exemplos JSON de cada contrato), "Principais interfaces" (assinaturas de `validation/volume.py`) e "ToolError — envelope de erro tipado" (semântica de cada novo `ErrorCode`). O envelope `ToolError` existente é reutilizado sem mudança estrutural.

## Critérios de sucesso

- Todos os contratos serializam com discriminador correto (`status="success"` / `status="volume_alert"`).
- `InlineColumn` rejeita tipos fora do contrato (`text`, `big_int`, `double`, `bool`, `date`, `timestamp`, `timestamp_tz`, `numeric(p,s)`).
- Limiares lidos do ambiente com defaults conservadores; valor inválido gera erro de configuração sem vazar segredos.
- Funções de volume são puras e retornam dimensões excedidas com `limit`, `actual` e `risk` preenchidos.
- Suite rápida verde com cobertura ≥ 80%; `ruff` sem apontamentos.

## Testes da tarefa

### Testes unitários

`tests/validation/test_volume.py` (casos 1–8 da techspec):

- [x] 1. `test_check_source_file_abaixo_do_limiar_retorna_lista_vazia`
- [x] 2. `test_check_source_file_acima_do_limiar_retorna_dimensao_source_file_mb`
- [x] 3. `test_check_source_file_exatamente_no_limiar_nao_excede`
- [x] 4. `test_check_inline_rows_abaixo_do_limiar_retorna_lista_vazia`
- [x] 5. `test_check_inline_rows_acima_do_limiar_retorna_dimensao_inline_rows`
- [x] 6. `test_check_extracted_rows_acima_do_limiar_retorna_dimensao_extracted_rows`
- [x] 7. `test_dimensao_excedida_inclui_limit_actual_e_risk_preenchidos`
- [x] 8. `test_limiares_customizados_via_settings_sao_respeitados`

`tests/test_config.py` (casos 9–11):

- [x] 9. `test_settings_hyper_defaults_conservadores`
- [x] 10. `test_settings_hyper_limiares_lidos_do_ambiente`
- [x] 11. `test_settings_hyper_limiar_invalido_gera_config_error_sem_segredos`

`tests/test_models.py` (casos 12–17):

- [x] 12. `test_hyper_create_result_serializa_status_success`
- [x] 13. `test_volume_alert_serializa_status_volume_alert_e_dimensoes`
- [x] 14. `test_hyper_query_result_row_count_e_truncated_consistentes`
- [x] 15. `test_inline_column_tipo_desconhecido_rejeitado_na_validacao`
- [x] 16. `test_error_code_contem_novos_codigos_hyper_e_db`
- [x] 17. `test_hyper_table_info_row_count_nulo_permitido`

### Testes de integração

- Não aplicável nesta tarefa (módulos puros; integração coberta nas tarefas 3.0–7.0).

### Testes E2E (se aplicável)

- Não aplicável.

## Arquivos relevantes

- `src/mcp_tableau/models.py` — modificado (contratos + `ErrorCode`)
- `src/mcp_tableau/config.py` — modificado (limiares `HYPER_*`)
- `src/mcp_tableau/validation/volume.py` — novo
- `tests/validation/test_volume.py` — novo
- `tests/test_config.py` — modificado
- `tests/test_models.py` — modificado
