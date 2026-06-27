# Relatório de QA — Enriquecer Saídas com IDs

## Resumo

- Data: 2026-06-27
- Status: **APROVADO** (0 bugs encontrados)
- Total de Requisitos (RF): 11
- Requisitos Atendidos: 10 (RF5 adiado por decisão de produto — ver nota)
- Bugs Encontrados: 0
- Cobertura de testes: **93,46%** (meta ≥ 80%)
- Testes rápidos (unit + MCP in-memory): **165 passou / 0 falhou** (suite verde)
- Testes de integração real (Tableau Cloud `dimensa-homologacao`): **4/4 passaram**

> **Natureza do produto:** servidor MCP headless (stdio), sem UI/frontend. Playwright/E2E de
> browser não se aplica; validação de encadeamento feita por testes de integração MCP
> in-memory e por teste real contra Tableau Cloud.

> **RF5 (id de conexão):** por decisão explícita de produto registrada na TechSpec,
> `ConnectionInfo` permanece inalterada. Conexões embutidas no arquivo de workbook não
> possuem LUID de servidor; adicionar um campo sempre `null` introduziria ruído sem valor.
> Isso está documentado na TechSpec (§ Principais decisões) e no contrato da ferramenta.

## Ambiente de teste

- Tableau Cloud: `https://us-east-1.online.tableau.com`, site `dimensa-homologacao`
- Autenticação: PAT `tableau-mcp-homologacao` (válido)
- Projeto sandbox: `MCP-TestSample`
- Workbook de sandbox: `MCP-Superstore` (`b32e69bf-4517-4d49-ab3b-c43d16f42908`)
- Variável `TABLEAU_IT_WORKBOOK_ID` adicionada ao `.env.integration` nesta QA

## Requisitos Verificados

| ID | Requisito | Status | Evidência |
|----|-----------|--------|-----------|
| RF1 | `inspect_workbook_structure` retorna cada worksheet como `{id, name}` | PASSOU | `test_inspect_structure_worksheets_viram_sheetref_id_none` + `test_inspect_structure_enriquece_ids_por_nome` + `test_real_inspect_structure_retorna_luids_validos` (integração real) |
| RF2 | `inspect_workbook_structure` retorna cada dashboard como `{id, name}` | PASSOU | `test_inspect_structure_dashboards_viram_sheetref_id_none` + `test_inspect_structure_enriquece_ids_por_nome` |
| RF3 | `SheetRef.id` retornado é o LUID aceito por `render_view_image`/`render_view_pdf` sem transformação | PASSOU | `test_inspect_structure_id_aceito_por_render` + `test_render_aceita_id_do_structure_report` (MCP in-memory) + `test_real_inspect_structure_retorna_luids_validos` (render real via LUID da inspeção) |
| RF4 | Worksheet/dashboard sem LUID retorna `id: null` (não omitido), com `name` preservado | PASSOU | `test_inspect_structure_worksheets_viram_sheetref_id_none` + `test_inspect_structure_sheet_sem_correspondencia_id_none` + `test_inspect_workbook_structure_degradado_serializa_id_null` (in-memory) |
| RF5 | Conexão retorna identificador quando disponível | **ADIADO** | Decisão de produto: `ConnectionInfo` inalterada (conexões embutidas não possuem LUID). Coberto por `test_connection_info_inalterada` — não-regressão confirmada. |
| RF6 | Cada filtro retorna `worksheet_id` (LUID da worksheet) quando disponível | PASSOU | `test_inspect_structure_filtro_worksheet_id_preenchido` + `test_inspect_workbook_structure_contrato_serializa_sheetref` (in-memory) |
| RF7 | `worksheet_id` nulo quando identificador não disponível (não omitido) | PASSOU | `test_inspect_structure_filtros_worksheet_id_none` + `test_inspect_workbook_structure_degradado_serializa_id_null` |
| RF8 | Objetos identificáveis representados como `{id, name, ...}` em vez de string | PASSOU | `test_structure_report_rejeita_list_str_em_worksheets` (breaking change confirmado — `list[str]` levanta `ValidationError`) + serialização MCP in-memory |
| RF9 | Mudança de contrato refletida na docstring/esquema da ferramenta | PASSOU | Docstring de `inspect_workbook_structure` (qa.py:40–76) documenta `{id, name}`, degradação best-effort e semântica de `null`; `SheetRef` documentado em models.py:143–154 |
| RF10 | Ausência de identificador = `null` (nunca envelope de erro); ferramenta só falha nas mesmas condições atuais | PASSOU | `test_inspect_structure_degrada_quando_populate_views_falha` + `test_inspect_structure_degrada_quando_metadata_indisponivel` → `status="success"` com ids `null`; `test_inspect_structure_not_found_antes_do_enriquecimento` → `ToolError(NOT_FOUND)` sem enriquecimento |
| RF11 | `SimilarityMatch`, `ContentRef` e `LineageNode` verificados — formato `{id, name}` consistente | PASSOU | Inspeção direta em models.py: todos os três modelos existentes usam `id: str` + `name: str`; nenhuma divergência encontrada |

## Testes Executados

### Suite rápida (unit + integração MCP in-memory)

```
165 passou, 0 falhou, 4 deselecionados — cobertura 93,46% (meta ≥80%)
```

#### Novos testes adicionados para a feature (28 testes)

| Arquivo | Testes novos |
|---------|-------------|
| `tests/test_models.py` | `test_sheetref_aceita_id_none_preserva_name`, `test_sheetref_serializa_id_luid`, `test_structure_report_worksheets_aceita_list_sheetref`, `test_structure_report_rejeita_list_str_em_worksheets`, `test_filter_info_worksheet_id_default_none`, `test_filter_info_aceita_worksheet_id`, `test_connection_info_inalterada` |
| `tests/validation/test_structure.py` | `test_inspect_structure_worksheets_viram_sheetref_id_none`, `test_inspect_structure_dashboards_viram_sheetref_id_none`, `test_inspect_structure_filtros_worksheet_id_none`, `test_inspect_structure_permanece_puro_sem_rede` |
| `tests/validation/test_complexity.py` | `test_measure_conta_worksheets_sobre_sheetref`, `test_measure_conta_dashboards_sobre_sheetref`, `test_complexity_excede_worksheets_com_sheetref` |
| `tests/tableau/test_client.py` | `test_list_workbook_view_luids_retorna_mapa_nome_luid`, `test_list_workbook_view_luids_omite_view_sem_luid`, `test_list_workbook_view_luids_nomes_duplicados_ultima_vence`, `test_list_workbook_view_luids_reautentica_em_401`, `test_list_workbook_view_luids_traduz_404_not_found`, `test_list_workbook_view_luids_nao_vaza_credenciais` |
| `tests/tools/test_qa.py` | `test_inspect_structure_enriquece_ids_por_nome`, `test_inspect_structure_sheet_sem_correspondencia_id_none`, `test_inspect_structure_filtro_worksheet_id_preenchido`, `test_inspect_structure_degrada_quando_populate_views_falha`, `test_inspect_structure_degrada_quando_metadata_indisponivel`, `test_inspect_structure_not_found_antes_do_enriquecimento`, `test_inspect_structure_id_aceito_por_render`, `test_audit_complexity_inalterado_com_sheetref` |
| `tests/test_mcp_integration.py` | `test_inspect_workbook_structure_contrato_serializa_sheetref`, `test_inspect_workbook_structure_degradado_serializa_id_null`, `test_render_aceita_id_do_structure_report` |

### Integração real com Tableau Cloud (`pytest -m integration`)

| Fluxo | Resultado | Observações |
|-------|-----------|-------------|
| `test_integration_publish_e_download_roundtrip` | PASSOU | Não-regressão: publicação + download roundtrip |
| `test_integration_render_view_image_retorna_png_valido` | PASSOU | Não-regressão: PNG com assinatura válida |
| `test_integration_metadata_lineage_responde` | PASSOU | Não-regressão: linhagem Metadata API |
| `test_real_inspect_structure_retorna_luids_validos` | PASSOU | **Novo:** inspeciona `MCP-Superstore`, verifica worksheets com `id` não nulo, encadeia `render_view_image` com o LUID retornado e confirma PNG válido |

### Verificação de não-regressão

- `audit_workbook_complexity` continua funcional sobre `list[SheetRef]`: `test_audit_complexity_inalterado_com_sheetref` PASSOU.
- Todos os 137 testes pré-existentes passaram sem modificação de comportamento.

## Acessibilidade / Responsividade

Não aplicável — produto sem UI (servidor MCP headless). A "interface" é o contrato de ferramentas MCP. A "usabilidade" foi verificada por:

- Nomes de campos autoexplicativos (`id`, `name`, `worksheet_id`) e docstrings atualizadas (RF9).
- Campo `id` **sempre presente** na serialização, mesmo como `null` (RF4, RF7) — distinguível de campo omitido.
- Contrato breaking change documentado na TechSpec e na docstring da ferramenta.

## Bugs Encontrados

Nenhum.

**Ajuste de ambiente:** a variável `TABLEAU_IT_WORKBOOK_ID=b32e69bf-4517-4d49-ab3b-c43d16f42908` estava ausente do `.env.integration`, causando skip do teste `test_real_inspect_structure_retorna_luids_validos`. O valor estava comentado no arquivo mas não declarado como variável. Corrigido nesta QA (adicionada ao `.env.integration`).

## Conclusão

A implementação **atende a 10 dos 11 requisitos funcionais do PRD**. O RF5 (id de conexão) foi postergado por decisão explícita de produto: conexões embutidas no arquivo de workbook não possuem LUID de servidor, e a adição de um campo sempre `null` foi considerada mais ruidosa do que útil. Essa decisão está documentada na TechSpec (§ Principais decisões) e no contrato da ferramenta.

Os 10 RFs implementados foram verificados por:

- **28 novos testes unitários/MCP in-memory** passando, incluindo casos de encadeamento (`SheetRef.id` → `render_view_image`), degradação best-effort, breaking change de contrato e não-regressão da auditoria de complexidade.
- **1 novo teste de integração real** contra `MCP-Superstore` no Tableau Cloud: worksheets publicadas retornam `id` não nulo, e o LUID é aceito diretamente por `render_view_image` sem transformação (RF3 verificado end-to-end).
- **3 testes de não-regressão** de integração (deploy, render, linhagem) — todos passando.

Status final: **APROVADO** — todos os RFs no escopo atendidos, suite 100% verde (165 testes), cobertura 93,46%, integração real 4/4. Sem ressalvas pendentes.
