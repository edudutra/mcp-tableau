# Tarefa 8.0: Tools — Capacidade 2 Visual (`tools/visual.py`)

## Visão geral

Implementa as ferramentas MCP de inspeção visual (Capacidade 2), que orquestram a renderização
via `TableauClient` (Tarefa 2.0) e a heurística pura `validation/visual.py` (Tarefa 4.0):
`render_view_image` renderiza o PNG de uma view (com filtros `vf_` opcionais), aplica a
heurística de tela em branco e devolve `RenderImageResult` **acompanhado do bloco de imagem MCP**
para consumo multimodal; `render_workbook_pdf` renderiza o PDF de uma ou mais páginas. O veredito
`diagnostic.severity="error"` sinaliza tela em branco **sem falhar** a ferramenta.

<skills>
### Conformidade com skills

- **`code-standards`** — ferramentas finas com docstring-contrato, render só via `TableauClient`,
  heurística via `validation/visual.py`, erros acionáveis.
- **`testing-standards`** — client mockado, heurística real; nomenclatura padrão.
</skills>

<requirements>
- **RF8**: Extrair imagem (PNG) de uma página/view de workbook publicado.
- **RF9**: Extrair PDF de uma ou mais páginas.
- **RF10**: Aplicar filtros/parâmetros (`vf_`) na renderização.
- **RF11**: Sinalizar indícios de erro visual de forma estruturada (`VisualDiagnostic`).
- **RF12**: Retornar a renderização em formato adequado a agente multimodal (bloco de imagem MCP).
- **RF22/RF23**: Status explícito e erro acionável tipado.
</requirements>

## Subtarefas

- [x] 8.1 `render_view_image(view_id, filters={}, high_res=true)`: converter `filters` em `vf_`,
  chamar `render_view_image` do client, aplicar `detect_blank_render` e retornar
  `RenderImageResult` + bloco de imagem PNG (`fastmcp.utilities.types.Image`).
- [x] 8.2 Garantir que `severity="error"` (tela em branco) **não** falha a ferramenta; a imagem é
  sempre devolvida para confirmação multimodal.
- [x] 8.3 `render_workbook_pdf(view_id, filters={}, page_type="A4")`: renderizar PDF e retornar
  status + bloco PDF.
- [x] 8.4 Mapear view inexistente → `NOT_FOUND` e falha de render → `RENDER_FAILED`/
  `UPSTREAM_ERROR`; registrar as tools no `server.py`.

## Detalhes de implementação

Ver techspec.md § "Endpoints da API" → `render_view_image`, `render_workbook_pdf`;
§ "Modelos de dados" → `RenderImageResult`, `VisualDiagnostic`; § "Principais decisões"
(inspeção visual em duas camadas) e o mapeamento Tableau→contrato (bloco de imagem MCP).

## Critérios de sucesso

- `render_view_image` retorna `RenderImageResult` + bloco de imagem PNG.
- Filtros são aplicados como `vf_` no request options.
- Tela em branco define `severity="error"` sem falhar a ferramenta.
- View inexistente retorna `NOT_FOUND`; falha de render retorna `RENDER_FAILED`.
- `render_workbook_pdf` retorna bloco PDF; `page_type` default `A4`.

## Testes da tarefa

### Testes unitários

- [x] `test_render_view_image_sucesso_retorna_result_e_bloco_imagem`
- [x] `test_render_view_image_aplica_filtros_vf_no_request_options`
- [x] `test_render_view_image_tela_em_branco_define_severity_error_sem_falhar`
- [x] `test_render_view_image_view_inexistente_retorna_not_found`
- [x] `test_render_view_image_falha_render_retorna_render_failed`
- [x] `test_render_workbook_pdf_sucesso_retorna_bloco_pdf`
- [x] `test_render_workbook_pdf_page_type_default_a4`

### Testes de integração

- [ ] (Tarefa 9.0) `test_mcp_render_view_image_retorna_bloco_imagem_e_json`
  (MCP in-memory, client mockado).

## Arquivos relevantes

- `src/mcp_tableau/tools/visual.py`
- `src/mcp_tableau/server.py` (registro das tools)
- `tests/tools/test_visual.py`
