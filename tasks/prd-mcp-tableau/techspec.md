# Especificação técnica

## Resumo executivo

O **MCP Tableau** será um servidor [FastMCP](https://github.com/jlowin/fastmcp) (Python ≥ 3.13) que expõe, via Model Context Protocol em transporte **stdio**, um conjunto coeso de ferramentas que cobrem as quatro capacidades do PRD: publicação/deploy, inspeção visual, validação estrutural (QA) e consulta a metadados/linhagem. A integração com o Tableau é centralizada em uma camada de cliente (`tableau/`) construída sobre o `tableauserverclient` (TSC) para a **REST API** (autenticação PAT, publicação com upload em chunks transparente acima de 64 MB, renderização de imagem/PDF) e sobre a **Metadata API (GraphQL)** para linhagem e dicionário. Toda credencial é lida de variáveis de ambiente; nenhum segredo trafega em retornos, logs ou mensagens de erro.

As decisões arquiteturais centrais são: (1) **abordagem híbrida de QA estrutural** — parsing local do XML do artefato com `tableaudocumentapi` para complexidade/contagens combinado com a Metadata API para campos quebrados e referências resolvidas pelo servidor; (2) **inspeção visual em duas camadas** — heurística leve de detecção de tela em branco (Pillow) que produz um veredito estruturado, acompanhada da própria imagem PNG/PDF devolvida ao agente multimodal; (3) **busca de similaridade determinística** por correspondência fuzzy (`rapidfuzz`) sobre nomes/descrições/campos obtidos da REST e Metadata API, sem infraestrutura de embeddings. Todas as ferramentas retornam modelos **Pydantic** com status explícito e um **envelope de erro tipado e acionável**, garantindo saídas previsíveis e auditáveis tanto para o agente autônomo quanto para o engenheiro supervisor.

## Arquitetura do sistema

### Visão dos componentes

O código segue o layout `src/mcp_tableau/` definido no `AGENTS.md`, com separação por responsabilidade. Componentes **novos** marcados com (novo):

- **`server.py`** (novo) — instancia o `FastMCP` e registra todas as ferramentas dos módulos `tools/`. Define o transporte stdio. É o único ponto de bootstrap; `main.py` apenas o invoca.
- **`config.py`** (novo) — carrega e valida configuração/credenciais de variáveis de ambiente (URL do servidor, site, PAT name/secret, limiares de complexidade, timeouts). Expõe um objeto `Settings` (Pydantic `BaseSettings`). Nunca loga segredos.
- **`tableau/client.py`** (novo) — `TableauClient`: wrapper sobre `tableauserverclient`. Centraliza sign-in/sign-out (PAT), **re-autenticação lazy em expiração/401**, publicação (workbook/datasource com `PublishMode`), download de artefato, renderização de imagem/PDF (`populate_image`/`populate_pdf` com `vf_` filters) e paginação. Único componente que fala REST com o Tableau.
- **`tableau/metadata.py`** (novo) — `MetadataClient`: executa queries GraphQL na Metadata API (linhagem ascendente/descendente, dicionário de campos, candidatos de similaridade). Reaproveita a sessão autenticada do `TableauClient`.
- **`tools/deploy.py`** (novo) — ferramentas de publicação/sobrescrita (Capacidade 1). Finas: validam entrada e delegam ao `TableauClient`.
- **`tools/visual.py`** (novo) — ferramentas de renderização PNG/PDF e diagnóstico visual (Capacidade 2). Orquestra `TableauClient` + `validation/visual.py`.
- **`tools/qa.py`** (novo) — ferramentas de inspeção estrutural e auditoria de complexidade (Capacidade 3). Orquestra download + `validation/structure.py` + `validation/complexity.py` + Metadata API.
- **`tools/metadata.py`** (novo) — ferramentas de linhagem, dicionário e similaridade (Capacidade 4). Orquestra `MetadataClient` + `validation/similarity.py`.
- **`validation/structure.py`** (novo) — parsing puro do XML (`.twb`/`.twbx`) via `tableaudocumentapi`: extrai campos, filtros, conexões; detecta campos quebrados/filtros inconsistentes. Sem rede.
- **`validation/complexity.py`** (novo) — regras puras de auditoria de complexidade contra limiares configuráveis. Sem rede.
- **`validation/visual.py`** (novo) — heurística pura de detecção de imagem em branco/uniforme (Pillow). Recebe bytes, retorna veredito estruturado. Sem rede.
- **`validation/similarity.py`** (novo) — correspondência fuzzy pura (`rapidfuzz`) entre o critério informado e os candidatos retornados pela camada de integração. Sem rede.
- **`models.py`** (novo) — todos os modelos Pydantic de entrada/saída e o envelope de erro tipado (`ToolError`).

**Principais relacionamentos:** `server.py` → registra `tools/*` → cada tool orquestra (`tableau/*` para I/O com Tableau) + (`validation/*` para regras puras) → retorna modelos de `models.py`. As camadas `validation/*` não conhecem rede nem o TSC; as camadas `tableau/*` não conhecem regras de negócio.

**Fluxo de dados (jornada do agente):** Descobrir (`tools/metadata.py` → Metadata API) → Construir/Publicar (`tools/deploy.py` → REST publish, chunked) → Validar estrutura (`tools/qa.py` → download + parse XML + Metadata API) → Inspecionar visualmente (`tools/visual.py` → REST render + heurística Pillow + imagem ao agente) → Decidir.

## Design de implementação

### Principais interfaces

Camada de integração — único ponto que fala com o Tableau (REST + GraphQL):

```python
class TableauClient:
    """Sessão TSC gerenciada (PAT). Re-autentica em expiração/401."""
    def publish_workbook(self, file_path: Path, project_id: str, overwrite: bool) -> "PublishedRef": ...
    def publish_datasource(self, file_path: Path, project_id: str, overwrite: bool) -> "PublishedRef": ...
    def download_workbook(self, workbook_id: str, dest_dir: Path) -> Path: ...
    def render_view_image(self, view_id: str, filters: dict[str, str], high_res: bool) -> bytes: ...
    def render_view_pdf(self, view_id: str, page_type: str, filters: dict[str, str]) -> bytes: ...
    def find_project_id(self, project_name: str) -> str | None: ...
    def search_content(self, term: str) -> list["ContentRef"]: ...

class MetadataClient:
    """Executa GraphQL na Metadata API reaproveitando a sessão do TableauClient."""
    def downstream_of_datasource(self, datasource_luid: str) -> dict: ...
    def upstream_of_workbook(self, workbook_luid: str) -> dict: ...
    def datasource_dictionary(self, datasource_luid: str) -> dict: ...
```

Camada de validação — funções puras, testáveis sem rede:

```python
def inspect_structure(workbook_path: Path) -> "StructureReport": ...
def audit_complexity(report: "StructureReport", thresholds: "Thresholds") -> "ComplexityReport": ...
def detect_blank_render(image_bytes: bytes) -> "VisualDiagnostic": ...
def rank_similar(term: str, candidates: list["ContentRef"]) -> list["SimilarityMatch"]: ...
```

### Modelos de dados

Contratos JSON expostos pelas ferramentas MCP. Todas as saídas são modelos Pydantic serializados. Campos ausentes no upstream (Tableau) são normalizados para `null`. Toda ferramenta retorna **ou** seu modelo de sucesso **ou** o envelope `ToolError`.

#### `PublishResult` — resultado de publicação/sobrescrita

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `string` | sim | `"success"` ou `"error"`. |
| `content_id` | `string` | sim | LUID do conteúdo publicado no Tableau. |
| `content_type` | `string` | sim | `"workbook"` ou `"datasource"`. |
| `name` | `string` | sim | Nome do conteúdo publicado. |
| `project_id` | `string` | sim | LUID do projeto de destino. |
| `project_name` | `string` | sim | Nome do projeto de destino. |
| `mode` | `string` | sim | `"create_new"` ou `"overwrite"`. |
| `chunked` | `boolean` | sim | `true` se o upload usou particionamento (>64 MB). |
| `webpage_url` | `string \| null` | não | URL do conteúdo no servidor, quando disponível. |

```json
{
  "status": "success",
  "content_id": "3f9a1c2e-7b4d-4a11-9c0e-1d2f3a4b5c6d",
  "content_type": "workbook",
  "name": "Vendas Regionais 2026",
  "project_id": "a1b2c3d4-0000-1111-2222-333344445555",
  "project_name": "Financeiro/Produção",
  "mode": "overwrite",
  "chunked": true,
  "webpage_url": "https://10ax.online.tableau.com/#/site/acme/workbooks/9981"
}
```

#### `RenderImageResult` — renderização PNG + diagnóstico visual

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `string` | sim | `"success"` ou `"error"`. |
| `view_id` | `string` | sim | LUID da view renderizada. |
| `mime_type` | `string` | sim | `"image/png"`. |
| `applied_filters` | `object` | sim | Filtros `vf_` efetivamente aplicados (mapa chave→valor). |
| `diagnostic` | `VisualDiagnostic` | sim | Veredito heurístico de erro visual. |

> A imagem em si é retornada como bloco de conteúdo de imagem do MCP (`fastmcp.utilities.types.Image`, base64/PNG), ao lado deste JSON estruturado, para consumo pelo agente multimodal (RF12).

```json
{
  "status": "success",
  "view_id": "7c8d9e0f-1111-2222-3333-444455556666",
  "mime_type": "image/png",
  "applied_filters": { "Region": "West", "Year": "2026" },
  "diagnostic": {
    "is_likely_blank": false,
    "blank_ratio": 0.07,
    "severity": "ok",
    "message": "Renderização com conteúdo visual detectado."
  }
}
```

#### `VisualDiagnostic` — veredito heurístico de erro visual (RF11)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `is_likely_blank` | `boolean` | sim | `true` se a heurística indica tela/gráfico em branco. |
| `blank_ratio` | `number` | sim | Fração de pixels uniformes/de fundo (0.0–1.0). |
| `severity` | `string` | sim | `"ok"`, `"warning"` ou `"error"`. |
| `message` | `string` | sim | Explicação legível do veredito. |

> **Tela em branco detectada:** quando `blank_ratio` excede o limiar (`severity` = `"error"`), o agente é instruído a não liberar o painel. A imagem ainda é devolvida para confirmação multimodal.

```json
{
  "is_likely_blank": true,
  "blank_ratio": 0.991,
  "severity": "error",
  "message": "Imagem praticamente uniforme; possível falha de carregamento ou view vazia."
}
```

#### `StructureReport` — estrutura interna do workbook (RF13/RF14)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `string` | sim | `"success"` ou `"error"`. |
| `workbook_id` | `string` | sim | LUID do workbook inspecionado. |
| `worksheets` | `string[]` | sim | Nomes das worksheets encontradas. |
| `dashboards` | `string[]` | sim | Nomes dos dashboards encontrados. |
| `connections` | `ConnectionInfo[]` | sim | Conexões de dados declaradas. |
| `fields` | `FieldInfo[]` | sim | Campos (inclui calculados, com fórmula). |
| `filters` | `FilterInfo[]` | sim | Filtros declarados por worksheet. |
| `issues` | `StructureIssue[]` | sim | Problemas detectados (campos quebrados, filtros sem lógica, conexões inválidas). |

```json
{
  "status": "success",
  "workbook_id": "3f9a1c2e-7b4d-4a11-9c0e-1d2f3a4b5c6d",
  "worksheets": ["Vendas por Região", "Tendência Mensal"],
  "dashboards": ["Visão Executiva"],
  "connections": [
    { "name": "Oracle PROD", "type": "oracle", "server": "db.acme.local", "is_valid": true }
  ],
  "fields": [
    { "name": "Margem", "datatype": "real", "role": "measure", "is_calculated": true,
      "formula": "[Lucro] / [Receita]", "is_broken": false },
    { "name": "Receita", "datatype": "real", "role": "measure", "is_calculated": false,
      "formula": null, "is_broken": false }
  ],
  "filters": [
    { "worksheet": "Vendas por Região", "field": "Region", "kind": "categorical", "has_logic": true }
  ],
  "issues": []
}
```

> **Campo quebrado / filtro sem lógica:** quando detectados, populam `issues` com `severity` e `field`/`worksheet` afetados, sem falhar a ferramenta — o objetivo é diagnóstico, não bloqueio.

```json
{
  "issues": [
    { "code": "broken_field", "severity": "error", "target": "Margem",
      "detail": "Campo calculado referencia coluna inexistente: [Lucro]." },
    { "code": "filter_no_logic", "severity": "warning", "target": "Tendência Mensal/Date",
      "detail": "Filtro sem condição aplicável definida." }
  ]
}
```

#### `ComplexityReport` — auditoria de boas práticas (RF15/RF16)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `string` | sim | `"success"` ou `"error"`. |
| `workbook_id` | `string` | sim | LUID auditado. |
| `metrics` | `object` | sim | Contagens medidas (`worksheets`, `dashboards`, `filters`, `data_sources`, `calculated_fields`). |
| `thresholds` | `object` | sim | Limiares efetivos usados na avaliação. |
| `compliant` | `boolean` | sim | `true` se nenhum limiar foi excedido. |
| `findings` | `ComplexityFinding[]` | sim | Itens que excederam limiares, com risco de performance. |

```json
{
  "status": "success",
  "workbook_id": "3f9a1c2e-7b4d-4a11-9c0e-1d2f3a4b5c6d",
  "metrics": { "worksheets": 14, "dashboards": 2, "filters": 23, "data_sources": 3, "calculated_fields": 41 },
  "thresholds": { "max_filters": 15, "max_worksheets": 20, "max_data_sources": 5 },
  "compliant": false,
  "findings": [
    { "metric": "filters", "value": 23, "threshold": 15, "severity": "warning",
      "recommendation": "Excesso de filtros pode degradar a performance de carregamento." }
  ]
}
```

#### `LineageResult` — linhagem ascendente/descendente (RF17/RF18)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `string` | sim | `"success"` ou `"error"`. |
| `direction` | `string` | sim | `"downstream"` ou `"upstream"`. |
| `root` | `ContentRef` | sim | Conteúdo consultado. |
| `dependencies` | `LineageNode[]` | sim | Nós dependentes/dependências, atribuíveis. |

```json
{
  "status": "success",
  "direction": "downstream",
  "root": { "id": "ds-1234", "name": "Vendas Corporativo", "type": "datasource", "project": "Dados Certificados" },
  "dependencies": [
    { "id": "wb-9981", "name": "Visão Executiva", "type": "workbook", "project": "Financeiro/Produção", "owner": "ana.silva" },
    { "id": "wb-9982", "name": "Painel Diretoria", "type": "workbook", "project": "Diretoria", "owner": "bruno.costa" }
  ]
}
```

#### `DataDictionary` — dicionário de fonte de dados (RF19)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `string` | sim | `"success"` ou `"error"`. |
| `datasource_id` | `string` | sim | LUID da fonte de dados. |
| `datasource_name` | `string` | sim | Nome da fonte de dados. |
| `fields` | `DictionaryField[]` | sim | Campos: nome, tipo, fórmula (se calculado), descrição homologada. |

```json
{
  "status": "success",
  "datasource_id": "ds-1234",
  "datasource_name": "Vendas Corporativo",
  "fields": [
    { "name": "Receita Líquida", "datatype": "real", "is_calculated": true,
      "formula": "SUM([Receita]) - SUM([Impostos])", "description": "Regra homologada Fin-2024-07." },
    { "name": "Cliente", "datatype": "string", "is_calculated": false, "formula": null, "description": null }
  ]
}
```

#### `SimilarityResult` — busca de similaridade (RF20)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `string` | sim | `"success"` ou `"error"`. |
| `query` | `string` | sim | Critério informado pelo agente. |
| `matches` | `SimilarityMatch[]` | sim | Candidatos ordenados por `score` decrescente. |

```json
{
  "status": "success",
  "query": "painel de vendas por região",
  "matches": [
    { "id": "wb-9981", "name": "Vendas Regionais 2026", "type": "workbook",
      "project": "Financeiro/Produção", "score": 0.92 },
    { "id": "ds-1234", "name": "Vendas Corporativo", "type": "datasource",
      "project": "Dados Certificados", "score": 0.71 }
  ]
}
```

> **Nenhuma correspondência:** `matches` retorna `[]` com `status: "success"` — ausência de similar não é erro (sinaliza que criar novo conteúdo é seguro quanto a duplicação).

#### `ToolError` — envelope de erro tipado

| Código | HTTP (origem REST) | Significado |
| --- | --- | --- |
| `AUTH_FAILED` | 401 | PAT inválido/expirado ou sign-in recusado. |
| `PERMISSION_DENIED` | 403 | Identidade do PAT sem permissão para a operação. |
| `NOT_FOUND` | 404 | Conteúdo/projeto/view inexistente. |
| `PROJECT_NOT_FOUND` | 404 | Projeto de destino não encontrado por nome/ID. |
| `OVERWRITE_NOT_ALLOWED` | 409 | Conteúdo já existe e `overwrite` não foi indicado (RF7). |
| `INVALID_FILE` | — | Extensão/arquivo inválido ou inexistente (validado localmente). |
| `PAYLOAD_TOO_LARGE` | 413 | Excede limite do servidor mesmo com chunking (config do servidor). |
| `RENDER_FAILED` | 5xx | Falha na renderização de imagem/PDF. |
| `UPSTREAM_ERROR` | 5xx | Falha genérica da REST/Metadata API do Tableau. |
| `VALIDATION_ERROR` | — | Entrada inválida nos limites da ferramenta. |

```json
{
  "status": "error",
  "error": {
    "code": "OVERWRITE_NOT_ALLOWED",
    "message": "Já existe um workbook 'Vendas Regionais 2026' no projeto 'Financeiro/Produção'. Reenvie com overwrite=true para criar nova versão."
  }
}
```

#### Mapeamento Tableau (TSC / Metadata API) → contrato

| Origem (Tableau) | Destino (contrato) |
| --- | --- |
| `WorkbookItem.id` / `DatasourceItem.id` | `PublishResult.content_id` |
| `ProjectItem.id` / `.name` | `PublishResult.project_id` / `project_name` |
| `PublishMode.Overwrite` / `.CreateNew` | `PublishResult.mode` |
| `view.populate_image()` (bytes PNG) | bloco de imagem MCP + `RenderImageResult` |
| `tableaudocumentapi` `Workbook.worksheets/datasources/fields` | `StructureReport.*` |
| Metadata API `downstreamWorkbooks` / `upstreamDatasources` | `LineageResult.dependencies` |
| Metadata API `fields { name formula description }` | `DataDictionary.fields` |
| REST `Server.workbooks/datasources` + filtro `name` | candidatos de `SimilarityResult` |

#### Parâmetros fixados no upstream (backend)

| API | Parâmetros principais |
| --- | --- |
| **REST — Query View Image** | `resolution=high` (quando `high_res=true`), `vf_<campo>=<valor>` para filtros, `maxAge` curto p/ render fresco |
| **REST — Publish** | `overwrite` ⇒ `PublishMode.Overwrite`; chunking automático do TSC quando arquivo > 64 MB |
| **Metadata API** | GraphQL POST único; sem paginação manual nas queries de linhagem/dicionário do MVP |

### Endpoints da API

> Este produto **não** expõe endpoints HTTP. Sua superfície de API é o conjunto de **ferramentas MCP** registradas no FastMCP e consumidas pelo agente via stdio. A seção abaixo documenta cada ferramenta no formato do template (visão geral, parâmetros, respostas, exemplos), tratando o nome da ferramenta como a "rota" e os parâmetros tipados como o "body".

#### Visão geral

| Ferramenta (MCP tool) | Capacidade | Descrição | RFs |
| --- | --- | --- | --- |
| `publish_workbook` | 1 Deploy | Publica/sobrescreve workbook em um projeto. | RF1, RF3, RF5, RF6, RF7 |
| `publish_datasource` | 1 Deploy | Publica/sobrescreve fonte de dados em um projeto. | RF2, RF4, RF5, RF6, RF7 |
| `render_view_image` | 2 Visual | Renderiza PNG de uma view + diagnóstico de erro visual. | RF8, RF10, RF11, RF12 |
| `render_workbook_pdf` | 2 Visual | Renderiza PDF de uma/mais páginas. | RF9, RF10, RF12 |
| `inspect_workbook_structure` | 3 QA | Lê estrutura interna e lista problemas. | RF13, RF14 |
| `audit_workbook_complexity` | 3 QA | Audita complexidade contra boas práticas. | RF15, RF16 |
| `get_downstream_lineage` | 4 Metadados | Conteúdos que dependem de uma fonte de dados. | RF17 |
| `get_upstream_lineage` | 4 Metadados | Fontes/tabelas das quais um conteúdo depende. | RF18 |
| `get_datasource_dictionary` | 4 Metadados | Dicionário de campos/fórmulas/regras. | RF19 |
| `search_similar_content` | 4 Metadados | Busca fuzzy por conteúdo semelhante. | RF20 |

> Transversais (RF22/RF23/RF24): toda ferramenta retorna estrutura tipada com `status`, usa o envelope `ToolError` em falha e abstrai Cloud vs Server na camada `tableau/`.

---

#### `publish_workbook`

Publica um novo workbook ou sobrescreve um existente (nova versão) em um projeto. Upload em chunks acima de 64 MB é transparente.

**Body (parâmetros da ferramenta)**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `file_path` | `string` | — | Caminho local; extensão deve ser `.twb`/`.twbx`; arquivo deve existir. |
| `project_name` | `string` | — | Projeto de destino; resolvido para LUID antes de publicar. |
| `overwrite` | `boolean` | `false` | `true` cria nova versão de conteúdo existente (RF3). |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `PublishResult` | Publicação concluída (create ou overwrite). |
| erro | `ToolError` (`INVALID_FILE`) | Extensão inválida ou arquivo inexistente. |
| erro | `ToolError` (`PROJECT_NOT_FOUND`) | Projeto de destino não encontrado. |
| erro | `ToolError` (`OVERWRITE_NOT_ALLOWED`) | Conteúdo existe e `overwrite=false` (RF7). |
| erro | `ToolError` (`AUTH_FAILED`/`PERMISSION_DENIED`/`PAYLOAD_TOO_LARGE`/`UPSTREAM_ERROR`) | Falhas de auth, permissão, limite ou upstream. |

**Exemplo — sucesso (overwrite, chunked)**

```http
publish_workbook { "file_path": "/work/vendas.twbx", "project_name": "Financeiro/Produção", "overwrite": true }
```

Ver `PublishResult` na seção Modelos de dados.

**Exemplo — sobrescrita não autorizada**

```json
{ "status": "error", "error": { "code": "OVERWRITE_NOT_ALLOWED",
  "message": "Já existe 'vendas' no projeto. Reenvie com overwrite=true para criar nova versão." } }
```

---

#### `publish_datasource`

Análoga a `publish_workbook` para fontes de dados (`.tds`/`.tdsx`). Mesmas regras de overwrite e chunking.

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `file_path` | `string` | — | Extensão `.tds`/`.tdsx`; arquivo deve existir. |
| `project_name` | `string` | — | Projeto de destino resolvido para LUID. |
| `overwrite` | `boolean` | `false` | `true` cria nova versão (RF4). |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `PublishResult` (`content_type="datasource"`) | Publicação concluída. |
| erro | `ToolError` | Mesmos códigos de `publish_workbook`. |

---

#### `render_view_image`

Renderiza o PNG de uma view de workbook publicado, opcionalmente filtrado, e retorna a imagem + diagnóstico heurístico de erro visual.

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `view_id` | `string` | — | LUID da view. |
| `filters` | `object` | `{}` | Mapa campo→valor convertido em `vf_`; valores múltiplos via lista. |
| `high_res` | `boolean` | `true` | `true` ⇒ `resolution=high`. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `RenderImageResult` + bloco de imagem PNG | Renderização concluída (com ou sem alerta visual). |
| erro | `ToolError` (`NOT_FOUND`) | View inexistente. |
| erro | `ToolError` (`RENDER_FAILED`/`UPSTREAM_ERROR`) | Falha de renderização/upstream. |

**Exemplo — sucesso com filtro**

```http
render_view_image { "view_id": "7c8d9e0f-...", "filters": { "Region": "West", "Year": "2026" } }
```

Ver `RenderImageResult` / `VisualDiagnostic` na seção Modelos de dados.

> A imagem PNG acompanha o JSON como bloco de imagem MCP; o veredito `diagnostic.severity="error"` sinaliza tela em branco sem falhar a ferramenta.

---

#### `render_workbook_pdf`

Renderiza PDF de uma ou mais páginas de um workbook publicado.

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `view_id` | `string` | — | LUID da view a renderizar. |
| `filters` | `object` | `{}` | Filtros `vf_`. |
| `page_type` | `string` | `"A4"` | Tamanho/orientação suportado pela REST API. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `{ "status": "success", "view_id": ... }` + bloco PDF | PDF gerado. |
| erro | `ToolError` (`NOT_FOUND`/`RENDER_FAILED`) | View inexistente ou falha. |

---

#### `inspect_workbook_structure`

Baixa o workbook publicado, parseia o XML e combina com a Metadata API para reportar estrutura e problemas.

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `workbook_id` | `string` | — | LUID do workbook publicado. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `StructureReport` | Estrutura lida; `issues` pode estar vazio ou populado. |
| erro | `ToolError` (`NOT_FOUND`/`UPSTREAM_ERROR`) | Workbook inexistente ou falha de download/metadata. |

> Campos quebrados/filtros sem lógica **não** falham a ferramenta: aparecem em `issues` (RF14).

---

#### `audit_workbook_complexity`

Audita métricas de complexidade contra limiares (config com override por env).

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `workbook_id` | `string` | — | LUID do workbook. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `ComplexityReport` | Auditoria concluída; `compliant` true/false. |
| erro | `ToolError` (`NOT_FOUND`/`UPSTREAM_ERROR`) | Falha ao obter estrutura. |

---

#### `get_downstream_lineage`

Lista conteúdos que dependem de uma fonte de dados (linhagem descendente).

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `datasource_id` | `string` | — | LUID da fonte de dados. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `LineageResult` (`direction="downstream"`) | Dependências encontradas (lista pode ser vazia). |
| erro | `ToolError` (`NOT_FOUND`/`UPSTREAM_ERROR`) | Fonte inexistente ou falha Metadata API. |

> `dependencies: []` com `status: "success"` significa nenhum dependente (sobrescrita segura).

---

#### `get_upstream_lineage`

Lista fontes/tabelas das quais um conteúdo depende (linhagem ascendente).

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `content_id` | `string` | — | LUID de workbook ou datasource. |
| `content_type` | `string` | `"workbook"` | `"workbook"` ou `"datasource"`. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `LineageResult` (`direction="upstream"`) | Dependências de origem. |
| erro | `ToolError` (`NOT_FOUND`/`UPSTREAM_ERROR`) | Conteúdo inexistente ou falha. |

---

#### `get_datasource_dictionary`

Retorna o dicionário de campos (nomes, fórmulas de calculados, descrições homologadas) de uma fonte de dados.

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `datasource_id` | `string` | — | LUID da fonte de dados. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `DataDictionary` | Dicionário retornado; `formula`/`description` podem ser `null`. |
| erro | `ToolError` (`NOT_FOUND`/`UPSTREAM_ERROR`) | Fonte inexistente ou falha. |

---

#### `search_similar_content`

Busca fuzzy por workbooks/datasources semelhantes ao critério, para evitar duplicação.

**Body**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `query` | `string` | — | Critério textual (nome/tema pretendido). |
| `content_type` | `string` | `"all"` | `"workbook"`, `"datasource"` ou `"all"`. |
| `limit` | `integer` | `10` | 1–50; nº máximo de candidatos ordenados. |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| sucesso | `SimilarityResult` | Candidatos ordenados por `score`. |
| sucesso | `SimilarityResult` (`matches: []`) | Nenhum semelhante — não é erro. |
| erro | `ToolError` (`UPSTREAM_ERROR`) | Falha ao listar conteúdo. |

---

## Pontos de integração

- **Tableau REST API (via `tableauserverclient`)** — autenticação **PAT** (`PersonalAccessTokenAuth`), publicação (workbook/datasource) com `PublishMode` e chunking automático >64 MB, download de artefato, `view.populate_image()` / `populate_pdf()` com `ImageRequestOptions`/`PDFRequestOptions` (filtros `vf_`, resolução). Abstrai Cloud vs Server (RF24).
- **Tableau Metadata API (GraphQL)** — linhagem (`downstream*`/`upstream*`), dicionário (`fields { name formula description }`), e listagem para candidatos de similaridade. Mesma sessão/credencial da REST.
- **Autenticação** — PAT (name + secret) + URL do servidor + site lidos de env (`config.py`). Sessão gerenciada no `TableauClient`: sign-in lazy, sign-out garantido (context manager), **re-auth automático** ao detectar token expirado/401. Segredos nunca em logs/retornos (RF23).
- **Tratamento de erros** — exceções específicas do TSC (`NotSignedInError`, `ServerResponseError`, `EndpointUnavailableError`, `Forbidden`/`401`/`404`) são traduzidas em códigos do `ToolError`. Erros locais (extensão/arquivo) viram `INVALID_FILE`/`VALIDATION_ERROR` antes de qualquer chamada de rede.

## Abordagem de testes

Pirâmide conforme `testing-standards`: base ampla de unitários (rede/Tableau **sempre mockados**), camada moderada de integração MCP in-memory, integração real marcada (`@pytest.mark.integration`) fora da suite rápida. Meta **≥ 80%** de cobertura (`--cov=mcp_tableau --cov-fail-under=80`). Estrutura de `tests/` espelha `src/mcp_tableau/`.

### Testes unitários

**`validation/structure.py`** (funções puras sobre XML — fixtures `.twbx`/`.twb` em `tmp_path`):
- `test_inspect_structure_workbook_valido_lista_worksheets_e_dashboards`
- `test_inspect_structure_extrai_campos_calculados_com_formula`
- `test_inspect_structure_campo_calculado_referencia_inexistente_marca_broken_field`
- `test_inspect_structure_filtro_sem_logica_gera_issue_warning`
- `test_inspect_structure_conexao_invalida_gera_issue`
- `test_inspect_structure_workbook_sem_issues_retorna_lista_vazia`
- `test_inspect_structure_twbx_compactado_e_twb_puro_produzem_mesma_estrutura`
- `test_inspect_structure_arquivo_xml_corrompido_levanta_erro_tratavel`

**`validation/complexity.py`** (regras puras + `parametrize` de limiares):
- `test_audit_complexity_dentro_dos_limiares_compliant_true`
- `test_audit_complexity_excesso_de_filtros_gera_finding_warning`
- `test_audit_complexity_excesso_de_worksheets_gera_finding`
- `test_audit_complexity_multiplos_estouros_acumula_findings`
- `test_audit_complexity_thresholds_customizados_alteram_resultado` (parametrize)
- `test_audit_complexity_valores_no_limite_exato_nao_geram_finding`

**`validation/visual.py`** (heurística Pillow — imagens sintéticas em memória):
- `test_detect_blank_render_imagem_uniforme_branca_is_likely_blank_true`
- `test_detect_blank_render_imagem_com_conteudo_is_likely_blank_false`
- `test_detect_blank_render_blank_ratio_entre_zero_e_um`
- `test_detect_blank_render_severity_error_quando_acima_do_limiar` (parametrize limiares)
- `test_detect_blank_render_bytes_invalidos_levanta_erro_tratavel`

**`validation/similarity.py`** (fuzzy puro):
- `test_rank_similar_ordena_por_score_decrescente`
- `test_rank_similar_match_exato_score_maximo`
- `test_rank_similar_sem_candidatos_retorna_lista_vazia`
- `test_rank_similar_respeita_limit`
- `test_rank_similar_case_insensitive_e_acentos`

**`tools/deploy.py`** (cliente Tableau mockado):
- `test_publish_workbook_arquivo_valido_chama_client_e_retorna_publishresult`
- `test_publish_workbook_extensao_invalida_retorna_error_invalid_file_sem_chamar_client`
- `test_publish_workbook_arquivo_inexistente_retorna_error_invalid_file`
- `test_publish_workbook_projeto_inexistente_retorna_error_project_not_found`
- `test_publish_workbook_overwrite_false_em_conteudo_existente_retorna_overwrite_not_allowed`
- `test_publish_workbook_overwrite_true_usa_publishmode_overwrite`
- `test_publish_workbook_arquivo_grande_define_chunked_true`
- `test_publish_workbook_auth_falha_retorna_error_auth_failed_sem_vazar_token`
- `test_publish_datasource_extensao_tdsx_aceita`
- `test_publish_datasource_extensao_invalida_rejeitada`

**`tools/visual.py`** (client mockado, heurística real):
- `test_render_view_image_sucesso_retorna_result_e_bloco_imagem`
- `test_render_view_image_aplica_filtros_vf_no_request_options`
- `test_render_view_image_tela_em_branco_define_severity_error_sem_falhar`
- `test_render_view_image_view_inexistente_retorna_not_found`
- `test_render_view_image_falha_render_retorna_render_failed`
- `test_render_workbook_pdf_sucesso_retorna_bloco_pdf`
- `test_render_workbook_pdf_page_type_default_a4`

**`tools/qa.py`** (client + metadata mockados, validação real):
- `test_inspect_workbook_structure_baixa_e_parseia_retorna_report`
- `test_inspect_workbook_structure_workbook_inexistente_retorna_not_found`
- `test_inspect_workbook_structure_issues_nao_falham_ferramenta`
- `test_audit_workbook_complexity_retorna_compliant_conforme_metricas`
- `test_audit_workbook_complexity_usa_thresholds_de_config`

**`tools/metadata.py`** (metadata client mockado):
- `test_get_downstream_lineage_retorna_dependencias_atribuiveis`
- `test_get_downstream_lineage_sem_dependentes_retorna_lista_vazia_sucesso`
- `test_get_upstream_lineage_workbook_retorna_fontes`
- `test_get_datasource_dictionary_inclui_formula_de_calculados`
- `test_get_datasource_dictionary_campos_sem_descricao_normalizados_null`
- `test_search_similar_content_retorna_matches_ordenados`
- `test_search_similar_content_sem_match_retorna_lista_vazia`
- `test_search_similar_content_limit_invalido_retorna_validation_error`

**`tableau/client.py`** (TSC mockado):
- `test_client_sign_in_usa_pat_da_config`
- `test_client_sign_out_garantido_mesmo_em_erro` (context manager)
- `test_client_token_expirado_dispara_reauth_e_repete_uma_vez`
- `test_client_traduz_serverresponseerror_404_para_not_found`
- `test_client_traduz_403_para_permission_denied`
- `test_client_nunca_inclui_pat_em_mensagem_de_erro`
- `test_client_paginacao_lista_todo_o_conteudo`

**`tableau/metadata.py`**:
- `test_metadata_query_monta_graphql_e_parseia_resposta`
- `test_metadata_erro_graphql_vira_upstream_error`

**`config.py`** (`monkeypatch.setenv`):
- `test_settings_carrega_variaveis_obrigatorias`
- `test_settings_variavel_faltante_levanta_erro_claro`
- `test_settings_thresholds_default_quando_env_ausente`
- `test_settings_thresholds_override_por_env`

**`models.py`**:
- `test_toolerror_serializa_com_code_e_message`
- `test_publishresult_serializa_campos_obrigatorios`
- `test_models_campos_opcionais_aceitam_null`

### Testes de integração

**Integração MCP in-memory (suite rápida):** sobe o `FastMCP` em processo e chama as ferramentas via cliente de teste, com `TableauClient`/`MetadataClient` mockados. Verifica:
- `test_mcp_todas_ferramentas_registradas_e_descobriveis`
- `test_mcp_publish_workbook_contrato_de_entrada_e_saida_serializa`
- `test_mcp_render_view_image_retorna_bloco_imagem_e_json`
- `test_mcp_ferramenta_em_erro_retorna_toolerror_serializado`
- `test_mcp_docstrings_presentes_em_todas_ferramentas`

**Integração com Tableau real (`@pytest.mark.integration`, fora da suite rápida):**
- `test_integration_publish_e_download_roundtrip` (sandbox)
- `test_integration_render_view_image_retorna_png_valido`
- `test_integration_metadata_lineage_responde`

### Testes E2E

Conforme `testing-standards`, E2E extensivo é evitado. Apenas **smoke** opcional em pipeline dedicado: fluxo agente → MCP → Tableau sandbox executando descobrir → publicar → validar → inspecionar. **Playwright não se aplica** (produto sem UI/frontend); a validação visual usa renderização PNG/PDF, não navegação de browser.

## Sequenciamento do desenvolvimento

### Ordem de construção

1. **Fundação** (`config.py`, `models.py`, `server.py`, `main.py`) — config por env e contratos Pydantic primeiro; tudo depende deles.
2. **Camada de integração** (`tableau/client.py`, `tableau/metadata.py`) — auth PAT, sessão/re-auth, publish, download, render, GraphQL. Mockável e base das tools.
3. **Capacidade 1 — Deploy** (`tools/deploy.py`) — caminho mais direto (só REST), valida a fundação ponta a ponta.
4. **Capacidade 4 — Metadados** (`validation/similarity.py`, `tools/metadata.py`) — habilita a etapa "Descobrir" da jornada do agente.
5. **Capacidade 3 — QA** (`validation/structure.py`, `validation/complexity.py`, `tools/qa.py`) — depende de download (passo 2).
6. **Capacidade 2 — Visual** (`validation/visual.py`, `tools/visual.py`) — render + heurística Pillow.
7. **Integração e testes** — suite MCP in-memory, cobertura ≥80%, marcação de integração real.

### Dependências técnicas

- **Novas dependências de runtime:** `tableauserverclient`, `pydantic`, `python-dotenv`, `tableaudocumentapi` (parsing de `.twb/.twbx`), `Pillow` (heurística visual), `rapidfuzz` (similaridade). Adicionar ao `pyproject.toml`.
- **Dev:** `pytest`, `pytest-cov`, `ruff` (já previstos no AGENTS.md).
- **Infra externa:** Tableau Cloud/Server acessível + PAT válido com permissões adequadas (somente para testes de integração marcados; unitários não exigem).
- **`.env.example`** atualizado com `TABLEAU_SERVER_URL`, `TABLEAU_SITE`, `TABLEAU_PAT_NAME`, `TABLEAU_PAT_SECRET` e limiares opcionais (`MAX_FILTERS`, `MAX_WORKSHEETS`, etc.).

## Monitoramento e observabilidade

O produto é um servidor MCP stdio local, sem stack Prometheus/Grafana. A observabilidade se dá por **logging estruturado** (stdlib `logging`) e pelos próprios retornos auditáveis:

- **Logs (nível INFO):** início/fim de cada chamada de ferramenta com nome, duração e `status`; modo de publicação e se houve chunking; re-auth disparado.
- **Logs (nível WARNING/ERROR):** traduções de erro upstream, tela em branco detectada, limiares excedidos.
- **Redação obrigatória:** PAT, secret e tokens de sessão **nunca** são logados (RF23); um filtro de logging redige valores sensíveis por chave conhecida.
- **Evidências auditáveis (RF11/US11):** cada retorno carrega identificadores, `status`, diagnósticos e (no visual) a renderização — suficiente para o engenheiro supervisor rastrear o que o agente fez.
- **Métricas de produto** do PRD (taxa de sucesso de publicação, aprovação visual, erros por publicação, duração do ciclo) são derivadas pelo consumidor a partir dos campos estruturados/logs; não há coletor dedicado no MVP.

## Considerações técnicas

### Principais decisões

- **QA estrutural híbrido** (`tableaudocumentapi` + Metadata API): o parsing de XML cobre contagens e complexidade (RF15) que a Metadata API não expõe; a Metadata API valida referências resolvidas pelo servidor (campos quebrados pós-publicação, RF14). Alternativas descartadas: só Metadata API (não conta gráficos/filtros de layout) e só XML (não vê quebras resolvidas no servidor).
- **Inspeção visual em duas camadas** (heurística Pillow + imagem ao agente): garante o veredito estruturado exigido por RF11 **e** preserva o julgamento multimodal (RF12). Heurística é intencionalmente simples (uniformidade/branco) — o Tableau não oferece API de "falha de carregamento".
- **Similaridade fuzzy determinística** (`rapidfuzz`): atende RF20 sem infra de embeddings, mantendo o MVP leve e reprodutível.
- **Transporte stdio + site único por env**: alinhado ao consumo local por agente; auth simples e segura. Re-auth lazy lida com expiração de sessão do Tableau (~240 min idle).
- **Input por caminho local validado**: combina com chunking do TSC para artefatos grandes e evita inflar payload MCP com base64.
- **Limiares com default + override por env**: política de governança ajustável sem mudança de código e sem poluir a interface da ferramenta.

### Riscos conhecidos

- **Heurística visual com falsos positivos/negativos:** dashboards legitimamente "vazios" ou de fundo claro podem disparar alerta. Mitigação: limiar configurável + sempre devolver a imagem para o agente decidir; severidade `warning` antes de `error`.
- **Diferenças Cloud vs Server (RF24):** disponibilidade de Metadata API e recursos de render variam por versão. Mitigação: degradar campos indisponíveis para `null` e mapear `EndpointUnavailableError` para `UPSTREAM_ERROR` acionável; cobrir em testes de integração marcados.
- **Estabilidade do parsing de XML:** formato interno `.twb` pode variar entre versões do Tableau. Mitigação: isolar o parsing em `validation/structure.py`, testar com fixtures de múltiplas versões, tratar XML inesperado sem quebrar a ferramenta.
- **Expiração de sessão em operações longas (render/metadata):** mitigado pelo re-auth lazy com uma repetição.
- **Limites de tamanho específicos de update (config do servidor):** mesmo com chunking, updates podem ter teto adicional; mapear para `PAYLOAD_TOO_LARGE` com orientação.

### Conformidade com skills

Skills do projeto aplicáveis a esta especificação:

- **`code-standards`** — estilo ruff (linha ≤88, aspas duplas, f-strings), type hints obrigatórios, modelos Pydantic como contrato, ferramentas FastMCP finas com docstring-contrato, acesso ao Tableau só via `tableau/client.py`, credenciais por env, sem segredos em logs, erros acionáveis.
- **`testing-standards`** — pirâmide (unitários mockando rede, integração MCP in-memory, integração real marcada), nomenclatura `test_<unidade>_<cenario>_<resultado>`, fixtures em `conftest.py`, `tmp_path` para artefatos, meta de cobertura ≥80%.
- **`criar-tasks`** — a quebra em tasks de implementação a partir desta techspec seguirá os templates da skill.

### Arquivos relevantes e dependentes

- `pyproject.toml` — adicionar dependências de runtime e dev.
- `.env.example` — novo; variáveis de credencial/limiar.
- `main.py` — passa a iniciar o servidor (`server.run()`).
- `src/mcp_tableau/__init__.py`, `server.py`, `config.py`, `models.py` — novos.
- `src/mcp_tableau/tableau/client.py`, `metadata.py` — novos.
- `src/mcp_tableau/tools/deploy.py`, `visual.py`, `qa.py`, `metadata.py` — novos.
- `src/mcp_tableau/validation/structure.py`, `complexity.py`, `visual.py`, `similarity.py` — novos.
- `tests/` espelhando `src/mcp_tableau/` + `tests/conftest.py` — novos.
- `AGENTS.md` / `README.md` — atualizar dependências e instruções de execução.
