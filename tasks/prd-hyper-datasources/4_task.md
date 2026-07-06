# Tarefa 4.0: Tools de criação local — `create_hyper_from_file` e `create_hyper_from_inline`

## Visão geral

Implementar as duas tools de criação local de `.hyper` em `tools/hyper.py`: a partir de CSV/Parquet (`create_hyper_from_file`, com inferência de schema via `external()` ou schema explícito via `COPY FROM`) e a partir de dados inline (`create_hyper_from_inline`, com validação tudo-ou-nada). Ambas integradas às salvaguardas de volume: `VolumeAlert` pré-execução quando o limiar é excedido sem `confirm_large_operation=true`, e `warnings` no resultado quando executado com confirmação.

<skills>
### Conformidade com skills

- `code-standards` — validação de entrada completa antes de abrir `hyper_session()` (nenhum engine chamado em erro local), docstrings-contrato com defaults sensatos, erros acionáveis citando linha/coluna ofensora.
- `testing-standards` — engine/`validation` mockados na suite rápida, fixture `hyper_env` com limiares baixos para exercitar alertas sem arquivos grandes.
</skills>

<requirements>
- RF1 — criar `.hyper` de CSV local com opções de delimitador, encoding e cabeçalho.
- RF2 — criar `.hyper` de Parquet local.
- RF3 — inferir schema quando não informado; aceitar schema explícito.
- RF4 — relatório estruturado da criação (caminho, tabela, colunas com tipos, total de linhas).
- RF5 — erro estruturado para origem inexistente/corrompida ou schema incompatível.
- RF6 — criar `.hyper` de colunas e linhas inline.
- RF7 — validar dados inline contra o schema declarado, reportando linhas/colunas inconsistentes em erro estruturado.
- RF8 — limite recomendado de volume inline documentado e aplicado (`HYPER_MAX_INLINE_ROWS`, orientação na docstring para usar arquivo acima disso).
- RF23–RF24 — `VolumeAlert` não bloqueante com confirmação explícita.
</requirements>

## Subtarefas

- [ ] 4.1 Implementar `create_hyper_from_file(source_path, hyper_path, table_name="Extract", source_format="auto", delimiter=",", encoding="utf-8", header=True, schema=None, confirm_large_operation=False)` → `HyperCreateResult | VolumeAlert | ToolError`.
- [ ] 4.2 Integrar checagem de `validation/volume.py::check_source_file` antes da execução: acima do limiar sem confirmação → `VolumeAlert`; com confirmação → executa e replica o alerta em `warnings`.
- [ ] 4.3 Implementar `create_hyper_from_inline(hyper_path, table_name, columns, rows, confirm_large_operation=False)` → `HyperCreateResult | VolumeAlert | ToolError`, com validação tudo-ou-nada (qualquer linha inválida aborta antes de tocar o arquivo; mensagem cita índice da linha e coluna).
- [ ] 4.4 Integrar `check_inline_rows` com o mesmo fluxo de alerta/confirmação.
- [ ] 4.5 Validações de entrada: origem existente e com extensão/`source_format` válidos, destino `.hyper` com diretório-pai existente, `columns` não vazio com nomes únicos e tipos do contrato.
- [ ] 4.6 Escrever testes unitários (casos 46–56) em `tests/tools/test_hyper.py`, incluindo a fixture `hyper_env` (limiares baixos) em `tests/conftest.py`.

## Detalhes de implementação

Ver techspec.md, seções "`create_hyper_from_file`" e "`create_hyper_from_inline`" em "Endpoints da API" (parâmetros, regras, tabelas de respostas e exemplos), "`VolumeAlert`" em "Modelos de dados" (contrato do alerta) e decisão 8 (inferência via `external()` × carga via `COPY`).

## Critérios de sucesso

- Fluxo completo de volume: alerta sem confirmação (operação NÃO executada), execução com confirmação e rastro em `warnings`.
- Nenhuma chamada ao engine quando a validação local falha.
- Criação inline é atômica: linha inválida ⇒ nenhum dado gravado.
- Mensagens de `HYPER_SCHEMA_MISMATCH` citam índice da linha e coluna ofensora.
- Suite rápida verde; cobertura ≥ 80%; `ruff` limpo.

## Testes da tarefa

### Testes unitários

`tests/tools/test_hyper.py` (casos 46–56 da techspec, engine mockado):

- [ ] 46. `test_create_hyper_from_file_sucesso_retorna_hyper_create_result`
- [ ] 47. `test_create_hyper_from_file_origem_inexistente_retorna_invalid_file`
- [ ] 48. `test_create_hyper_from_file_extensao_desconhecida_sem_format_retorna_invalid_file`
- [ ] 49. `test_create_hyper_from_file_acima_do_limiar_sem_confirmacao_retorna_volume_alert`
- [ ] 50. `test_create_hyper_from_file_acima_do_limiar_com_confirmacao_executa_e_adiciona_warning`
- [ ] 51. `test_create_hyper_from_file_valida_antes_de_abrir_hyper_session`
- [ ] 52. `test_create_hyper_from_inline_sucesso_retorna_source_inline`
- [ ] 53. `test_create_hyper_from_inline_linha_com_aridade_errada_retorna_schema_mismatch_com_indice`
- [ ] 54. `test_create_hyper_from_inline_valor_nao_coercivel_retorna_schema_mismatch`
- [ ] 55. `test_create_hyper_from_inline_colunas_duplicadas_retorna_validation_error`
- [ ] 56. `test_create_hyper_from_inline_acima_do_limiar_sem_confirmacao_retorna_volume_alert`

### Testes de integração

- Serialização MCP dos novos contratos coberta na tarefa 7.0 (casos 84 e 86 usam `create_hyper_from_inline` e `VolumeAlert`).
- Runtime real coberto na tarefa 8.0 (casos 87–89).

### Testes E2E (se aplicável)

- Não aplicável.

## Arquivos relevantes

- `src/mcp_tableau/tools/hyper.py` — modificado (novas tools; arquivo criado na tarefa 3.0)
- `tests/tools/test_hyper.py` — modificado
- `tests/conftest.py` — modificado (fixture `hyper_env`)
- `src/mcp_tableau/validation/volume.py` / `models.py` / `config.py` — dependências (tarefa 1.0)
- `src/mcp_tableau/hyper/engine.py` — dependência (tarefa 2.0)
