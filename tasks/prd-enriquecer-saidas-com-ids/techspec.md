# Especificação técnica

## Resumo executivo

A inspeção estrutural (`inspect_workbook_structure`) hoje produz seu relatório a partir **apenas** do arquivo `.twb`/`.twbx` baixado, que não carrega os LUIDs do servidor. A solução introduz uma etapa de **enriquecimento por nome** na camada de ferramenta (`tools/qa.py`): após o parsing local puro, a ferramenta consulta as views publicadas do workbook via REST (`workbooks.populate_views`) e casa cada worksheet/dashboard local com o `ViewItem` correspondente por nome, anexando o LUID renderizável. O parsing local (`validation/structure.py`) permanece puro e passa a emitir objetos `SheetRef{id, name}` com `id=None`; o LUID é preenchido somente na orquestração, onde já existe a sessão autenticada.

As decisões centrais: (1) fonte do LUID é a REST `populate_views` (sempre disponível, mesmo identificador aceito pelas ferramentas de render); (2) o enriquecimento é **best-effort** — qualquer falha em obtê-lo degrada para `id=null` sem derrubar o diagnóstico estrutural (preserva a semântica de erro do RF10); (3) o contrato muda de forma incompatível: `worksheets`/`dashboards` deixam de ser `list[str]` e passam a `list[SheetRef]`, e `FilterInfo` ganha `worksheet_id`. O `id` de conexão (RF5) fica **fora deste ciclo** por decisão de produto (conexões embutidas não possuem LUID de servidor); `ConnectionInfo` permanece inalterada. Similaridade e linhagem já retornam `id` consistente — apenas verificação, sem redesenho (RF11).

## Arquitetura do sistema

### Visão dos componentes

Fluxo: `inspect_workbook_structure` (tool) → download (REST) → `inspect_structure` (parsing puro, ids nulos) → `list_workbook_view_luids` (REST, mapa nome→LUID) → merge na tool → `StructureReport` enriquecido.

- **`src/mcp_tableau/models.py`** (modificado): novo modelo `SheetRef{id, name}`. `StructureReport.worksheets` e `.dashboards` passam de `list[str]` para `list[SheetRef]`. `FilterInfo` ganha `worksheet_id: str | None`. `ConnectionInfo` inalterada.
- **`src/mcp_tableau/validation/structure.py`** (modificado): `inspect_structure` passa a construir `SheetRef(name=..., id=None)` para worksheets/dashboards e `FilterInfo(worksheet_id=None, ...)`. Permanece **puro** (sem rede); não conhece LUIDs.
- **`src/mcp_tableau/tableau/client.py`** (modificado): novo método `list_workbook_view_luids(workbook_id) -> dict[str, str]` que executa `populate_views` e retorna o mapa `nome_da_view → LUID`. Reutiliza `_with_reauth` e a tradução de erros existente.
- **`src/mcp_tableau/tools/qa.py`** (modificado): após o parsing, invoca o novo método e aplica o merge (preenche `SheetRef.id` e `FilterInfo.worksheet_id` por nome). Encapsula o enriquecimento em bloco best-effort que degrada para `id=null`.
- **`src/mcp_tableau/validation/complexity.py`** (verificado, sem mudança de comportamento): `_measure` usa `len(report.worksheets)`/`len(report.dashboards)` — continua válido sobre `list[SheetRef]`.
- **Consumidores a jusante** (não modificados, beneficiários): `render_view_image`/`render_view_pdf` recebem o `SheetRef.id` diretamente; `get_upstream_lineage`/`get_datasource_dictionary` recebem ids já existentes.

## Design de implementação

### Principais interfaces

```python
# tableau/client.py — nova consulta REST de views (somente LUID + nome)
class TableauClient:
    def list_workbook_view_luids(self, workbook_id: str) -> dict[str, str]:
        """Mapa nome_da_view -> LUID das views publicadas do workbook.
        Views sem LUID (sheets ocultas) são omitidas do mapa."""

# tools/qa.py — merge best-effort aplicado ao relatório já parseado
def _enrich_with_view_luids(
    client: TableauClient, report: StructureReport, workbook_id: str
) -> StructureReport:
    """Preenche SheetRef.id (worksheets/dashboards) e FilterInfo.worksheet_id
    por correspondência de nome. Falha de upstream degrada para id=None."""
```

O parsing puro permanece com a mesma assinatura (`inspect_structure(path, workbook_id) -> StructureReport`), apenas alterando o tipo interno dos campos de sheet.

### Modelos de dados

Contratos JSON de saída da ferramenta `inspect_workbook_structure`. Campos ausentes/indisponíveis no upstream são normalizados para `null` — especificamente, `SheetRef.id` e `FilterInfo.worksheet_id` são `null` quando a view não possui LUID (sheet oculta) ou quando o enriquecimento via REST falha (degradação).

#### `SheetRef` — referência a uma worksheet ou dashboard

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `id` | `string \| null` | sim (pode ser `null`) | LUID da view aceito por `render_view_image`/`render_view_pdf`. `null` quando a sheet não é uma view publicada (ex.: oculta) ou o enriquecimento falhou. |
| `name` | `string` | sim | Nome da worksheet/dashboard extraído do arquivo do workbook. |

```json
{
  "id": "9f2a6c10-4b8e-4d3a-9c21-7e1f5b0a2d44",
  "name": "Vendas por Região"
}
```

> **Degradação (sheet sem LUID ou falha de enriquecimento):** `id` vem `null`, `name` é sempre preservado. O consumidor distingue "não renderizável" (`id: null`) de erro (envelope `error`).

```json
{
  "id": null,
  "name": "Sheet auxiliar (oculta)"
}
```

#### `ConnectionInfo` — conexão de dados (inalterada nesta feature)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `name` | `string` | sim | Nome da fonte de dados/conexão. |
| `type` | `string` | sim | Tipo da conexão (ex.: `postgres`). |
| `server` | `string \| null` | não | Host do servidor; `null` para conexões serverless/arquivo. |
| `is_valid` | `boolean` | sim | Heurística de validade da conexão. |

> **RF5 fora deste ciclo:** conexões embutidas não possuem LUID de servidor; por decisão de produto, `ConnectionInfo` não recebe `id` agora. Mantida sem alteração para não introduzir campo sempre `null`.

#### `FilterInfo` — filtro por worksheet (campo `worksheet_id` adicionado)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `worksheet` | `string` | sim | Nome da worksheet onde o filtro está declarado. |
| `worksheet_id` | `string \| null` | sim (pode ser `null`) | LUID da view da worksheet; `null` se a worksheet não for view publicada ou se o enriquecimento falhar. |
| `field` | `string` | sim | Campo filtrado. |
| `kind` | `string` | sim | Classe do filtro (ex.: `categorical`). |
| `has_logic` | `boolean` | sim | Indica se o filtro carrega alguma condição. |

```json
{
  "worksheet": "Vendas por Região",
  "worksheet_id": "9f2a6c10-4b8e-4d3a-9c21-7e1f5b0a2d44",
  "field": "Região",
  "kind": "categorical",
  "has_logic": true
}
```

#### `StructureReport` — relatório estrutural (payload agregado)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `string` | sim | Sempre `"success"` no caminho feliz. |
| `workbook_id` | `string` | sim | LUID do workbook inspecionado. |
| `worksheets` | `SheetRef[]` | sim | Worksheets do workbook (era `string[]`). |
| `dashboards` | `SheetRef[]` | sim | Dashboards do workbook (era `string[]`). |
| `connections` | `ConnectionInfo[]` | sim | Conexões de dados. |
| `fields` | `FieldInfo[]` | sim | Campos (inclui calculados). |
| `filters` | `FilterInfo[]` | sim | Filtros por worksheet (agora com `worksheet_id`). |
| `issues` | `StructureIssue[]` | sim | Problemas detectados (vazio quando nada de errado). |

```json
{
  "status": "success",
  "workbook_id": "b7c4e2a1-1234-4abc-9def-0123456789ab",
  "worksheets": [
    { "id": "9f2a6c10-4b8e-4d3a-9c21-7e1f5b0a2d44", "name": "Vendas por Região" },
    { "id": null, "name": "Sheet auxiliar (oculta)" }
  ],
  "dashboards": [
    { "id": "1c3d5e70-aa11-42bb-83cc-44dd55ee66ff", "name": "Painel Executivo" }
  ],
  "connections": [
    { "name": "DW Vendas", "type": "postgres", "server": "db.interno", "is_valid": true }
  ],
  "fields": [
    { "name": "Margem", "datatype": "real", "role": "measure", "is_calculated": true, "formula": "[Lucro]/[Receita]", "is_broken": false }
  ],
  "filters": [
    { "worksheet": "Vendas por Região", "worksheet_id": "9f2a6c10-4b8e-4d3a-9c21-7e1f5b0a2d44", "field": "Região", "kind": "categorical", "has_logic": true }
  ],
  "issues": []
}
```

#### `ToolError` — envelope de erro tipado (inalterado)

| Código | HTTP (origem) | Significado |
| --- | --- | --- |
| `NOT_FOUND` | 404 | Workbook não encontrado no Tableau. |
| `AUTH_FAILED` | 401 | Sessão/PAT inválido. |
| `PERMISSION_DENIED` | 403 | Sem permissão para o workbook. |
| `UPSTREAM_ERROR` | 5xx / artefato inválido | Falha de comunicação ou workbook corrompido. |

```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "Recurso não encontrado no Tableau."
  }
}
```

> **Nota (RF10):** o enriquecimento de LUID **não** introduz novos códigos de erro nem falha a ferramenta. Falha ao obter views ⇒ `id`/`worksheet_id` ficam `null`, e o `StructureReport` retorna com `status="success"`.

#### Mapeamento REST (populate_views) → contrato

| Origem (`ViewItem` da REST) | Destino (contrato) |
| --- | --- |
| `ViewItem.id` (LUID) | `SheetRef.id` (quando `ViewItem.name` == nome da worksheet/dashboard local) |
| `ViewItem.id` (LUID) | `FilterInfo.worksheet_id` (quando `ViewItem.name` == `FilterInfo.worksheet`) |
| `ViewItem.name` | chave de correspondência (não exposta diretamente) |
| (worksheet local sem `ViewItem` correspondente) | `SheetRef.id = null` / `worksheet_id = null` |

#### Parâmetros fixados no upstream (backend)

| API | Parâmetros principais |
| --- | --- |
| **REST Query Views for Workbook** (`workbooks.populate_views`) | `usage=False` (sem estatísticas de uso); reutiliza a sessão PAT autenticada e `_with_reauth` (retry único em 401). |

### Endpoints da API

Este projeto é um servidor **MCP** (FastMCP); a interface pública são **ferramentas MCP**, não rotas HTTP. A ferramenta afetada é `inspect_workbook_structure`. As ferramentas de render são consumidoras do novo `id`.

#### Visão geral

| Ferramenta MCP | Entrada | Descrição |
| --- | --- | --- |
| `inspect_workbook_structure` | `workbook_id: str` | Inspeciona estrutura e agora retorna worksheets/dashboards com `id` e filtros com `worksheet_id`. |
| `render_view_image` / `render_view_pdf` | `view_id: str` | Consumidoras: aceitam o `SheetRef.id` sem transformação (RF3). |

---

#### `inspect_workbook_structure(workbook_id)`

Baixa o workbook publicado, parseia o XML local e enriquece worksheets/dashboards/filtros com os LUIDs das views publicadas.

**Body (parâmetros da tool)**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `workbook_id` | `string` | — | LUID do workbook publicado. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `StructureReport` | Workbook baixado e parseado; ids preenchidos quando há view publicada correspondente. |
| sucesso (degradado) | `StructureReport` (ids `null`) | Parsing OK, mas `populate_views` indisponível/falhou; estrutura retornada sem LUIDs. |
| erro | `ToolError(NOT_FOUND)` | Workbook não existe. |
| erro | `ToolError(UPSTREAM_ERROR)` | Artefato inválido/corrompido ou falha de download. |
| erro | `ToolError(AUTH_FAILED/PERMISSION_DENIED)` | Sessão inválida / sem permissão. |

**Exemplo — sucesso (enriquecido)**

```http
TOOL inspect_workbook_structure { "workbook_id": "b7c4e2a1-..." }
```

Ver `StructureReport` completo na seção Modelos de dados.

**Exemplo — sucesso degradado (Metadata/views indisponível)**

```json
{
  "status": "success",
  "workbook_id": "b7c4e2a1-1234-4abc-9def-0123456789ab",
  "worksheets": [ { "id": null, "name": "Vendas por Região" } ],
  "dashboards": [ { "id": null, "name": "Painel Executivo" } ],
  "filters": [ { "worksheet": "Vendas por Região", "worksheet_id": null, "field": "Região", "kind": "categorical", "has_logic": true } ],
  "connections": [],
  "fields": [],
  "issues": []
}
```

> A degradação **não** é erro HTTP/tool: o consumidor recebe `status="success"` e decide se renderiza (precisa de `id != null`).

**Exemplo — erro (workbook inexistente)**

```json
{
  "status": "error",
  "error": { "code": "NOT_FOUND", "message": "Recurso não encontrado no Tableau." }
}
```

---

## Pontos de integração

- **Tableau REST API** via `tableauserverclient` (`workbooks.populate_views`): única integração nova. Autenticação reutiliza a sessão PAT já aberta por `tableau_session`; nenhum novo segredo ou variável de ambiente.
- **Tratamento de erro**: o novo método do cliente reusa `_with_reauth` + `_translate` (mesmos `ErrorCode`). No nível da tool, o enriquecimento é envolvido em captura de `TableauClientError` para garantir degradação para `id=null` (a falha não é propagada como `ToolError`).
- **Segurança**: o método retorna apenas nomes e LUIDs (não sensíveis); mensagens de erro continuam sem credenciais.

## Abordagem de testes

Meta de cobertura: **≥80%** no pacote `mcp_tableau`, com foco em `models.py`, `validation/structure.py`, `validation/complexity.py`, `tableau/client.py` e `tools/qa.py`. Cliente Tableau sempre mockado nos unitários (sem rede).

### Testes unitários

**`models.py` (`tests/test_models.py`)**
- `test_sheetref_aceita_id_none_preserva_name` — `SheetRef(id=None, name="X")` válido e serializa `id: null`.
- `test_sheetref_serializa_id_luid` — `SheetRef(id="luid", name="X")` serializa ambos.
- `test_structure_report_worksheets_aceita_list_sheetref` — atribuir `list[SheetRef]` a `worksheets`/`dashboards`.
- `test_structure_report_rejeita_list_str_em_worksheets` — passar `["A"]` (string) agora levanta `ValidationError` (contrato incompatível confirmado).
- `test_filter_info_worksheet_id_default_none` — `FilterInfo` sem `worksheet_id` assume `None`.
- `test_filter_info_aceita_worksheet_id` — `worksheet_id="luid"` preservado.
- `test_connection_info_inalterada` — `ConnectionInfo` continua sem `id` (garante não-regressão de contrato).

**`validation/structure.py` (`tests/validation/test_structure.py`)** — atualizar fixtures de `list[str]` para `list[SheetRef]`.
- `test_inspect_structure_worksheets_viram_sheetref_id_none` — worksheets parseadas têm `id is None` e `name` correto.
- `test_inspect_structure_dashboards_viram_sheetref_id_none` — idem para dashboards.
- `test_inspect_structure_filtros_worksheet_id_none` — `FilterInfo.worksheet_id is None` no parsing puro.
- `test_inspect_structure_permanece_puro_sem_rede` — nenhuma chamada de cliente/rede ocorre (parsing apenas do arquivo).
- Regressão dos casos existentes (filtro sem lógica, conexão inválida, campo quebrado) sob o novo tipo.

**`validation/complexity.py` (`tests/validation/test_complexity.py`)** — atualizar helper `_report` para gerar `SheetRef`.
- `test_measure_conta_worksheets_sobre_sheetref` — `metrics.worksheets == len(list[SheetRef])`.
- `test_measure_conta_dashboards_sobre_sheetref` — idem dashboards.
- `test_complexity_excede_worksheets_com_sheetref` — limiar excedido conta corretamente objetos.
- Parametrizações existentes mantidas, agora com `SheetRef`.

**`tableau/client.py` (`tests/tableau/test_client.py`)** — TSC mockado.
- `test_list_workbook_view_luids_retorna_mapa_nome_luid` — `populate_views` mockado retorna views; método devolve `{name: id}`.
- `test_list_workbook_view_luids_omite_view_sem_luid` — `ViewItem` com `id` vazio/`None` é omitido do mapa.
- `test_list_workbook_view_luids_nomes_duplicados_ultima_vence` — comportamento determinístico definido para nomes repetidos.
- `test_list_workbook_view_luids_reautentica_em_401` — 401 dispara re-auth e repete uma vez (via `_with_reauth`).
- `test_list_workbook_view_luids_traduz_404_not_found` — erro REST 404 → `TableauClientError(NOT_FOUND)`.
- `test_list_workbook_view_luids_nao_vaza_credenciais` — mensagem de erro sem PAT/token.

**`tools/qa.py` (`tests/tools/test_qa.py`)** — `tableau_session`, `load_settings`, `inspect_structure` e o novo método mockados.
- `test_inspect_structure_enriquece_ids_por_nome` — sheets cujo nome casa com o mapa recebem o LUID; filtros recebem `worksheet_id`.
- `test_inspect_structure_sheet_sem_correspondencia_id_none` — worksheet sem view publicada mantém `id=None`.
- `test_inspect_structure_filtro_worksheet_id_preenchido` — `FilterInfo.worksheet_id` casado por nome.
- `test_inspect_structure_degrada_quando_populate_views_falha` — `list_workbook_view_luids` lança `TableauClientError(UPSTREAM_ERROR)` ⇒ resultado é `StructureReport` com ids `null` e `status="success"` (não `ToolError`).
- `test_inspect_structure_degrada_quando_metadata_indisponivel` — `EndpointUnavailable`/erro equivalente ⇒ degrada, não falha.
- `test_inspect_structure_not_found_antes_do_enriquecimento` — download falha com `NOT_FOUND` ⇒ `ToolError` e enriquecimento nunca chamado.
- `test_inspect_structure_id_aceito_por_render` — o `SheetRef.id` retornado é exatamente o formato passado a `render_view_image` (teste de contrato de encadeamento).
- `test_audit_complexity_inalterado_com_sheetref` — auditoria continua correta com o novo tipo (não-regressão).

### Testes de integração

**Protocolo MCP in-memory (`tests/test_mcp_integration.py`)**
- `test_inspect_workbook_structure_contrato_serializa_sheetref` — sobe FastMCP em processo, chama a tool com cliente mockado e valida o JSON: `worksheets[].id`, `worksheets[].name`, `filters[].worksheet_id` presentes e tipados.
- `test_inspect_workbook_structure_degradado_serializa_id_null` — caminho degradado serializa `id: null` corretamente (sem omitir o campo).
- `test_render_aceita_id_do_structure_report` — encadeamento: id obtido da inspeção é aceito pela tool de render (ambas mockadas no limite do cliente).

**Integração com Tableau real (`tests/integration/`, `@pytest.mark.integration`, fora da suite rápida)**
- `test_real_inspect_structure_retorna_luids_validos` — contra sandbox: worksheets visíveis têm `id` não nulo e renderizável; sheets ocultas vêm `null`.

### Testes E2E

Não se aplica interface gráfica (servidor MCP headless). E2E fica restrito ao smoke de integração real acima (sob demanda), conforme `testing-standards`. Sem Playwright neste projeto.

## Sequenciamento do desenvolvimento

### Ordem de construção

1. **`models.py`** — criar `SheetRef`, alterar `StructureReport` e `FilterInfo`. Base de tipos para todo o resto; quebra de contrato fica isolada e testável primeiro.
2. **`validation/structure.py`** — emitir `SheetRef(id=None)` e `FilterInfo(worksheet_id=None)`; manter pureza. Depende de (1).
3. **`validation/complexity.py`** — ajustar/confirmar `_measure` sobre `list[SheetRef]`. Depende de (1).
4. **`tableau/client.py`** — `list_workbook_view_luids`. Independente de (2)/(3); pode ser paralelo a (2).
5. **`tools/qa.py`** — orquestrar download → parse → enriquecimento best-effort → merge. Depende de (1), (2), (4).
6. **Atualização de testes** existentes + novos casos (seção Abordagem de testes) e documentação das docstrings (RF9).
7. **Integração MCP in-memory** e verificação de cobertura (`--cov-fail-under=80`).

### Dependências técnicas

- Nenhuma infra nova; nenhuma variável de ambiente nova (`.env.example` inalterado).
- `tableauserverclient` já provê `workbooks.populate_views` (sem upgrade de dependência).
- Integração real exige sandbox Tableau com workbook publicado (apenas para os testes `@pytest.mark.integration`).

## Monitoramento e observabilidade

O projeto não possui stack Prometheus/Grafana (servidor MCP local); observabilidade é via logging estruturado, sem segredos.

- **Log WARNING** quando `list_workbook_view_luids` falha e o resultado degrada para ids nulos — incluir `workbook_id` e o `ErrorCode`, **nunca** credenciais.
- **Log DEBUG** com a contagem de sheets sem correspondência de LUID (quantas vieram `null`), útil para diagnosticar workbooks com muitas sheets ocultas.
- Sem novas métricas; reutiliza o padrão de mensagens acionáveis já existente no `_translate`.

## Considerações técnicas

### Principais decisões

- **REST `populate_views` como fonte do LUID** (vs Metadata API GraphQL): sempre disponível (Metadata API pode estar desabilitada), e devolve exatamente o LUID que as ferramentas de render consomem (RF3). Trade-off: não distingue worksheet de dashboard — resolvido casando por nome contra os conjuntos locais de worksheets e dashboards (nomes de sheet são únicos no workbook).
- **Enriquecimento na camada de ferramenta, parsing puro intocado**: preserva a testabilidade sem rede de `validation/structure.py` e concentra o efeito colateral onde já há sessão autenticada — alinhado ao `code-standards` (validação pura, ferramenta fina que orquestra).
- **Degradação best-effort para `id=null`**: cumpre RF10 (sem novos erros, sem falhar a inspeção) e a meta de não regressão de latência/robustez. Distingue "não renderizável" de "erro".
- **Quebra de contrato assumida** (`list[str]` → `list[SheetRef]`): sem camada de compatibilidade, conforme PRD (Fora do escopo). Custo: atualização de testes existentes.
- **RF5 (id de conexão) adiado**: conexões embutidas não têm LUID de servidor; adicionar um campo sempre `null` agregaria ruído. `ConnectionInfo` permanece inalterada — desvio consciente do PRD, validado com o usuário.

### Riscos conhecidos

- **Colisão de nomes de view**: teoricamente nomes de sheet são únicos por workbook; ainda assim o mapa nome→LUID adota regra determinística (última ocorrência vence) e há teste dedicado.
- **Sheets ocultas/não publicadas**: vêm sem LUID (`id=null`) por design do Tableau (confirmado na pesquisa). Mitigação: documentado no contrato e coberto por teste; é comportamento esperado, não bug.
- **Latência adicional** de uma chamada REST extra (`populate_views`) por inspeção. Mitigação: chamada única, na mesma sessão; sem laços por sheet.
- **Atualização ampla de testes** por mudança de tipo. Mitigação: sequenciamento começa por `models.py`, expondo todos os pontos a ajustar de uma vez.

### Conformidade com skills

- **`code-standards`**: type hints completos; modelos Pydantic (novo `SheetRef`); ferramenta fina orquestrando, validação pura; acesso ao Tableau só via `tableau/client.py`; sem credenciais em logs.
- **`testing-standards`**: pirâmide respeitada (unitários mockando rede + integração MCP in-memory; integração real marcada); nomes `test_<unidade>_<cenario>_<resultado>`; meta de cobertura ≥80%.
- Skills de fluxo aplicáveis adiante: `criar-tasks` (derivar tasks desta techspec), `executar-task`, `executar-qa`, `executar-review`.

### Arquivos relevantes e dependentes

- `src/mcp_tableau/models.py` — **modificado** (novo `SheetRef`; `StructureReport`, `FilterInfo`).
- `src/mcp_tableau/validation/structure.py` — **modificado** (emite `SheetRef`/`worksheet_id` nulos).
- `src/mcp_tableau/validation/complexity.py` — **verificado/ajustado** (`_measure`).
- `src/mcp_tableau/tableau/client.py` — **modificado** (`list_workbook_view_luids`).
- `src/mcp_tableau/tools/qa.py` — **modificado** (enriquecimento/merge best-effort).
- `tests/test_models.py`, `tests/validation/test_structure.py`, `tests/validation/test_complexity.py`, `tests/tableau/test_client.py`, `tests/tools/test_qa.py`, `tests/test_mcp_integration.py` — **modificados/ampliados**.
- Consumidores (não modificados): `src/mcp_tableau/tools/visual.py`, `src/mcp_tableau/tools/metadata.py`.
- `src/mcp_tableau/tableau/metadata.py` — referência (similaridade/linhagem já com `id`, verificação RF11).
