# Especificação técnica

## Resumo executivo

Esta feature adiciona ao servidor MCP Tableau a **Capacidade 5 — Hyper Datasources**: um conjunto de sete novas tools MCP (mais uma extensão da `publish_datasource` existente) que cobrem o ciclo de vida local de extratos `.hyper` — criação a partir de CSV/Parquet, de dados inline e de bancos externos; consulta SQL; inspeção de schema; append e transformação — fechando o fluxo autônomo *descobrir → construir → validar → publicar*. O motor é a biblioteca oficial `tableauhyperapi` (runtime Hyper embarcado, compatível com Python ≥ 3.13); a extração de bancos externos usa **SQLAlchemy Core** com connection strings resolvidas exclusivamente de variáveis de ambiente no padrão `HYPER_DB_CONN_<NOME>` (múltiplas conexões nomeadas, credenciais nunca trafegam nas tools).

A arquitetura replica os padrões já consagrados no repositório: tools finas em `tools/hyper.py` registradas via `register(mcp)`, engine de integração em novo pacote `hyper/` (análogo a `tableau/client.py`), regras puras de salvaguarda de volume em `validation/volume.py`, contratos Pydantic em `models.py` com envelope `ToolError`/`ErrorCode` estendido, e limiares configuráveis em `Settings` (padrão `MAX_FILTERS`/`MAX_WORKSHEETS`). Operações acima dos limiares retornam um **`VolumeAlert` estruturado e não bloqueante**: o agente repete a chamada com `confirm_large_operation=true` para prosseguir. A publicação reutiliza integralmente o fluxo `_publish()` de `deploy.py`, apenas aceitando a extensão `.hyper` (suportada nativamente pelo `tableauserverclient` em Tableau Server ≥ 2021.4).

## Arquitetura do sistema

### Visão dos componentes

Componentes **novos**:

- **`src/mcp_tableau/tools/hyper.py`** — camada MCP fina com as sete tools (`create_hyper_from_file`, `create_hyper_from_inline`, `extract_database_to_hyper`, `query_hyper`, `inspect_hyper_schema`, `append_to_hyper`, `execute_hyper_sql`) e a função `register(mcp: FastMCP)`. Responsável por: validação de entrada, checagem de limiares (delegada a `validation/volume.py`), orquestração do engine e montagem dos contratos de retorno.
- **`src/mcp_tableau/hyper/engine.py`** — encapsula `tableauhyperapi` (`HyperProcess`, `Connection`, `Inserter`, catálogo). Expõe o context manager `hyper_session()` (análogo a `tableau_session`) e operações de alto nível: criar tabela de arquivo/inline, consultar, introspectar catálogo, append e comandos SQL. Traduz `HyperException` para `HyperEngineError(code, message)` sem vazar paths internos do runtime.
- **`src/mcp_tableau/hyper/db.py`** — extração de bancos externos via SQLAlchemy Core. Resolve `HYPER_DB_CONN_<NOME>` do ambiente (`resolve_connection(name)`), abre engine com `stream_results`, itera o cursor em lotes e grava no `.hyper` via `Inserter`. Traduz erros de driver distinguindo conexão × autenticação × SQL (RF12) **sem incluir a connection string em nenhuma mensagem** (RF11).
- **`src/mcp_tableau/validation/volume.py`** — regras puras (sem rede/IO além de `stat`): avalia dimensões (tamanho de arquivo de origem, linhas inline, linhas extraídas) contra os limiares de `Settings` e produz a lista de dimensões excedidas usada por `VolumeAlert` e por `warnings` (RF23–RF25).

Componentes **modificados**:

- **`src/mcp_tableau/models.py`** — novos contratos (`HyperColumn`, `HyperCreateResult`, `HyperQueryResult`, `HyperSchemaReport`, `HyperMutationResult`, `VolumeAlert`, `InlineColumn`) e novos membros em `ErrorCode`.
- **`src/mcp_tableau/config.py`** — novos limiares em `Settings` (`HYPER_MAX_SOURCE_FILE_MB`, `HYPER_MAX_INLINE_ROWS`, `HYPER_MAX_RESULT_ROWS`, `HYPER_MAX_EXTRACT_ROWS`).
- **`src/mcp_tableau/tools/deploy.py`** — `publish_datasource` passa a aceitar `.hyper` no conjunto de extensões válidas (RF21); nenhum outro comportamento muda.
- **`src/mcp_tableau/server.py`** — inclui `hyper.register(mcp)` em `register_tools()`.
- **`pyproject.toml`** — adiciona `tableauhyperapi>=0.0.23576` e `sqlalchemy>=2.0` (drivers de banco instalados à parte pelo administrador).
- **`.env.example`** — nova seção `# Hyper` com limiares e exemplo comentado de `HYPER_DB_CONN_<NOME>`.

Fluxo de dados (visão geral):

```
agente MCP
   │  (stdio / FastMCP)
   ▼
tools/hyper.py ──── validation/volume.py (limiares puros)
   │
   ├─► hyper/engine.py ──► tableauhyperapi (HyperProcess local) ──► arquivo .hyper
   │
   └─► hyper/db.py ──► SQLAlchemy Core ──► banco externo (somente leitura)
                             │
                             └─► hyper/engine.py (Inserter em lotes) ──► arquivo .hyper

tools/deploy.py (publish_datasource) ──► tableau/client.py ──► Tableau Server/Cloud
```

O `HyperProcess` é iniciado **por chamada** dentro de `hyper_session()` (processo local, telemetria desativada) e encerrado ao final — sem estado residente entre chamadas, coerente com o modelo sob demanda do servidor MCP (restrição "sem serviços adicionais" do PRD).

## Design de implementação

### Principais interfaces

```python
# src/mcp_tableau/hyper/engine.py
@contextmanager
def hyper_session() -> Iterator[HyperEngine]:
    """Inicia HyperProcess (telemetria off) e entrega o engine; encerra ao sair."""

class HyperEngine:
    def create_table_from_file(self, req: FileIngestRequest) -> TableReport: ...
    def create_table_from_rows(self, req: InlineIngestRequest) -> TableReport: ...
    def append_rows(self, req: AppendRequest) -> int: ...
    def query(self, hyper_path: Path, sql: str, max_rows: int) -> QueryRows: ...
    def execute(self, hyper_path: Path, sql: str) -> int:  # linhas afetadas
    def describe(self, hyper_path: Path) -> list[TableReport]: ...

class HyperEngineError(Exception):
    code: ErrorCode
    message: str  # sem paths internos do runtime, sem dados sensíveis
```

```python
# src/mcp_tableau/hyper/db.py
def resolve_connection(name: str) -> str:
    """Lê HYPER_DB_CONN_<NAME> do ambiente; levanta DbConfigError se ausente.
    A URL resolvida NUNCA é logada nem incluída em mensagens de erro."""

def extract_to_hyper(
    connection_name: str, query: str, hyper_path: Path, table_name: str,
    batch_size: int = 10_000,
) -> ExtractReport:
    """Executa a query com stream_results e grava em lotes via Inserter."""

class DbError(Exception):
    code: ErrorCode  # DB_CONNECTION_FAILED | DB_AUTH_FAILED | DB_QUERY_ERROR
    message: str     # mensagem original do driver SANITIZADA (sem URL/credencial)
```

```python
# src/mcp_tableau/validation/volume.py
def check_source_file(path: Path, settings: Settings) -> list[ExceededDimension]: ...
def check_inline_rows(row_count: int, settings: Settings) -> list[ExceededDimension]: ...
def check_extracted_rows(row_count: int, settings: Settings) -> list[ExceededDimension]: ...
```

```python
# src/mcp_tableau/tools/hyper.py — assinaturas das tools (contrato MCP)
def create_hyper_from_file(source_path, hyper_path, table_name="Extract",
    source_format="auto", delimiter=",", encoding="utf-8", header=True,
    schema=None, confirm_large_operation=False) -> HyperCreateResult | VolumeAlert | ToolError
def create_hyper_from_inline(hyper_path, table_name, columns, rows,
    confirm_large_operation=False) -> HyperCreateResult | VolumeAlert | ToolError
def extract_database_to_hyper(connection_name, query, hyper_path,
    table_name="Extract") -> HyperCreateResult | ToolError
def query_hyper(hyper_path, query, max_rows=None) -> HyperQueryResult | ToolError
def inspect_hyper_schema(hyper_path) -> HyperSchemaReport | ToolError
def append_to_hyper(hyper_path, table_name, source_path=None, columns=None,
    rows=None, confirm_large_operation=False) -> HyperMutationResult | VolumeAlert | ToolError
def execute_hyper_sql(hyper_path, command) -> HyperMutationResult | ToolError
```

### Modelos de dados

Contratos Pydantic adicionados a `src/mcp_tableau/models.py`, seguindo o padrão existente: sucesso com `status="success"` (`Literal`), erro via envelope `ToolError`. Campos ausentes ou não determináveis (ex.: contagem de linhas de tabela corrompida) são normalizados para `null`.

#### `HyperColumn` — coluna de uma tabela Hyper

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `name` | `str` | sim | Nome da coluna. |
| `type` | `str` | sim | Tipo lógico do contrato (ver tabela de mapeamento abaixo). |
| `nullable` | `bool` | sim | Se a coluna aceita `NULL`. |

```json
{
  "name": "valor_venda",
  "type": "double",
  "nullable": true
}
```

#### `InlineColumn` — definição de coluna para dados inline (entrada)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `name` | `str` | sim | Nome da coluna. |
| `type` | `str` | sim | Um dos tipos do contrato: `text`, `big_int`, `double`, `bool`, `date`, `timestamp`, `numeric(p,s)`. |
| `nullable` | `bool` | não (default `true`) | Se aceita `NULL`. |

```json
{
  "name": "codigo_filial",
  "type": "big_int",
  "nullable": false
}
```

#### `HyperCreateResult` — relatório de criação/extração (RF4)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `"success"` | sim | Discriminador de sucesso. |
| `hyper_path` | `str` | sim | Caminho absoluto do `.hyper` gerado. |
| `table_name` | `str` | sim | Tabela criada (schema `Extract` por padrão). |
| `columns` | `list[HyperColumn]` | sim | Colunas com tipos efetivos (inferidos ou declarados). |
| `row_count` | `int` | sim | Total de linhas carregadas. |
| `source` | `str` | sim | Origem: `"csv"`, `"parquet"`, `"inline"` ou `"database"`. |
| `warnings` | `list[str]` | sim (default `[]`) | Alertas não bloqueantes (ex.: volume excedido com confirmação, linhas extraídas acima do limiar). |

```json
{
  "status": "success",
  "hyper_path": "/data/extratos/vendas_2026.hyper",
  "table_name": "Extract",
  "columns": [
    { "name": "data_venda", "type": "date", "nullable": true },
    { "name": "filial", "type": "text", "nullable": true },
    { "name": "valor_venda", "type": "double", "nullable": true }
  ],
  "row_count": 184230,
  "source": "csv",
  "warnings": []
}
```

> **Degradação — extração de banco acima do limiar (RF23):** `extract_database_to_hyper` não conhece o volume antes de executar; quando as linhas extraídas ultrapassam `HYPER_MAX_EXTRACT_ROWS`, a extração **conclui normalmente** e o alerta vem em `warnings`.

```json
{
  "status": "success",
  "row_count": 7412903,
  "warnings": [
    "Volume extraído (7412903 linhas) excede o limiar HYPER_MAX_EXTRACT_ROWS (5000000). Valide espaço em disco antes de repetir operações desse porte."
  ]
}
```

#### `HyperQueryResult` — resultado de consulta SQL de leitura (RF13–RF14)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `"success"` | sim | Discriminador de sucesso. |
| `columns` | `list[HyperColumn]` | sim | Colunas do resultado com tipos. |
| `rows` | `list[list[str \| int \| float \| bool \| None]]` | sim | Linhas serializadas em tipos JSON; datas/timestamps como ISO-8601. |
| `row_count` | `int` | sim | Linhas **retornadas** (pós-truncamento). |
| `truncated` | `bool` | sim | `true` quando o resultado foi cortado em `max_rows`. |
| `max_rows` | `int` | sim | Limite aplicado (parâmetro ou `HYPER_MAX_RESULT_ROWS`). |

```json
{
  "status": "success",
  "columns": [
    { "name": "filial", "type": "text", "nullable": true },
    { "name": "total", "type": "double", "nullable": true }
  ],
  "rows": [
    ["Campinas", 1250341.55],
    ["Santos", 987222.10]
  ],
  "row_count": 2,
  "truncated": false,
  "max_rows": 200
}
```

> **Truncamento (RF14):** quando a consulta produz mais linhas que `max_rows`, `truncated=true` e o agente é orientado (na docstring da tool) a refinar com `LIMIT`/agregações — o resultado nunca estoura o contexto do agente.

#### `HyperTableInfo` / `HyperSchemaReport` — inspeção estrutural (RF16)

`HyperTableInfo`:

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `schema_name` | `str` | sim | Schema no arquivo (ex.: `Extract`, `public`). |
| `table_name` | `str` | sim | Nome da tabela. |
| `columns` | `list[HyperColumn]` | sim | Colunas com tipo e nulabilidade. |
| `row_count` | `int \| None` | sim | Contagem de linhas; `null` se não determinável. |

`HyperSchemaReport`:

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `"success"` | sim | Discriminador de sucesso. |
| `hyper_path` | `str` | sim | Caminho do arquivo inspecionado. |
| `file_size_bytes` | `int` | sim | Tamanho do arquivo em bytes. |
| `tables` | `list[HyperTableInfo]` | sim | Todas as tabelas de todos os schemas. |

```json
{
  "status": "success",
  "hyper_path": "/data/extratos/vendas_2026.hyper",
  "file_size_bytes": 52428800,
  "tables": [
    {
      "schema_name": "Extract",
      "table_name": "Extract",
      "columns": [
        { "name": "data_venda", "type": "date", "nullable": true },
        { "name": "valor_venda", "type": "double", "nullable": true }
      ],
      "row_count": 184230
    }
  ]
}
```

#### `HyperMutationResult` — resultado de append/modificação (RF18–RF20)

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `"success"` | sim | Discriminador de sucesso. |
| `hyper_path` | `str` | sim | Arquivo alvo. |
| `operation` | `str` | sim | `"append"`, `"insert"`, `"update"`, `"delete"` ou `"create_table_as"`. |
| `affected_rows` | `int \| None` | sim | Linhas afetadas; `null` para DDL (`CREATE TABLE AS` reporta linhas materializadas quando disponível). |
| `table_name` | `str \| None` | sim | Tabela alvo/criada, quando identificável; senão `null`. |
| `warnings` | `list[str]` | sim (default `[]`) | Alertas não bloqueantes. |

```json
{
  "status": "success",
  "hyper_path": "/data/extratos/vendas_2026.hyper",
  "operation": "append",
  "affected_rows": 5120,
  "table_name": "Extract",
  "warnings": []
}
```

#### `VolumeAlert` — alerta estruturado não bloqueante (RF23–RF24)

Retornado **no lugar do resultado** quando uma dimensão pré-execução excede o limiar e `confirm_large_operation=false`. Não é erro: instrui o agente a decidir (com o usuário) e repetir a chamada com confirmação.

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `status` | `"volume_alert"` | sim | Discriminador do alerta. |
| `exceeded` | `list[ExceededDimension]` | sim | Dimensões excedidas. |
| `message` | `str` | sim | Texto em linguagem natural, repassável ao usuário final. |
| `how_to_proceed` | `str` | sim | Instrução: repetir a chamada com `confirm_large_operation=true`. |

`ExceededDimension`:

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `dimension` | `str` | sim | `"source_file_mb"`, `"inline_rows"` ou `"extracted_rows"`. |
| `limit` | `float` | sim | Limiar configurado. |
| `actual` | `float` | sim | Valor observado. |
| `risk` | `str` | sim | Risco associado (disco, memória, tempo). |

```json
{
  "status": "volume_alert",
  "exceeded": [
    {
      "dimension": "source_file_mb",
      "limit": 500,
      "actual": 2048.7,
      "risk": "Arquivo de origem grande pode esgotar disco local e alongar o processamento."
    }
  ],
  "message": "O arquivo de origem tem 2048.7 MB, acima do limiar de 500 MB. A operação NÃO foi executada.",
  "how_to_proceed": "Confirme com o usuário e repita a chamada com confirm_large_operation=true para prosseguir."
}
```

#### `ToolError` — envelope de erro tipado (existente, com novos códigos)

O envelope `ToolError` de `models.py` é reutilizado sem mudanças estruturais. Novos membros de `ErrorCode`:

| Código | Quando ocorre | Significado / ação para o agente |
| --- | --- | --- |
| `INVALID_FILE` *(existente)* | Arquivo de origem (CSV/Parquet) inexistente, extensão inválida ou ilegível (RF5). | Corrigir o caminho/formato e repetir. |
| `HYPER_INVALID_FILE` | O caminho não aponta para um `.hyper` válido/abrível (RF17). | Verificar o arquivo; usar `inspect_hyper_schema` em um `.hyper` legítimo. |
| `HYPER_SCHEMA_MISMATCH` | Schema declarado incompatível com dados (RF5) ou append com colunas divergentes (RF18); dados inline inconsistentes com as colunas declaradas (RF7). | Ajustar schema/dados; a mensagem lista colunas/linhas ofensoras. |
| `HYPER_SQL_ERROR` | SQL inválido no motor Hyper (RF15, RF19–RF20). | Mensagem original do Hyper incluída; corrigir a consulta. |
| `DB_CONNECTION_NOT_CONFIGURED` | `HYPER_DB_CONN_<NOME>` ausente no ambiente. | Pedir ao administrador para configurar a variável. |
| `DB_CONNECTION_FAILED` | Falha de rede/host/porta ao conectar na origem (RF12). | Verificar disponibilidade do banco com o administrador. |
| `DB_AUTH_FAILED` | Credencial recusada pela origem (RF12). | Acionar o administrador; credencial não é parametrizável via tool. |
| `DB_QUERY_ERROR` | SQL rejeitado pelo banco de origem (RF12). | Mensagem do driver sanitizada incluída; corrigir a query. |
| `VALIDATION_ERROR` *(existente)* | Parâmetros inválidos (ex.: `query_hyper` com comando de escrita; `rows` sem `columns`). | Corrigir os parâmetros da chamada. |

```json
{
  "status": "error",
  "error": {
    "code": "DB_AUTH_FAILED",
    "message": "Autenticação recusada pelo banco de dados da conexão 'VENDAS'. Solicite ao administrador a revisão da credencial configurada no ambiente."
  }
}
```

> **RF11 — sanitização obrigatória:** mensagens de `DB_*` citam apenas o **nome lógico** da conexão (`VENDAS`), nunca a URL. `hyper/db.py` remove qualquer ocorrência da connection string (e de suas partes: usuário, senha, host) da mensagem original do driver antes de montar o `ToolError`.

#### Mapeamento tipos do contrato → `tableauhyperapi.SqlType`

| Origem (contrato / inferência) | Destino (`SqlType`) |
| --- | --- |
| `text` | `SqlType.text()` |
| `big_int` | `SqlType.big_int()` |
| `double` | `SqlType.double()` |
| `bool` | `SqlType.bool()` |
| `date` | `SqlType.date()` |
| `timestamp` | `SqlType.timestamp()` |
| `timestamp_tz` | `SqlType.timestamp_tz()` |
| `numeric(p,s)` | `SqlType.numeric(p, s)` |
| tipos Hyper não mapeados (ex.: `geography`) | expostos na inspeção como `text` do nome bruto do tipo, somente leitura |

Na direção inversa (inspeção/consulta), o `TypeTag` do Hyper é convertido para o tipo lógico do contrato; valores `DATE`/`TIMESTAMP` são serializados como ISO-8601 e `NUMERIC` como `str` (preservação de precisão).

#### Parâmetros fixados no upstream

| API | Parâmetros principais |
| --- | --- |
| **`HyperProcess`** | `telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU` (privacidade), processo iniciado por chamada dentro de `hyper_session()` |
| **`Connection`** | `create_mode=CREATE_AND_REPLACE` (criação), `CREATE_IF_NOT_EXISTS` (inline com arquivo novo), `NONE` (consulta/inspeção/mutação) |
| **`COPY FROM` (CSV)** | `format => 'csv'`, `delimiter`, `encoding`, `header` vindos dos parâmetros da tool; caminho escapado com `escape_string_literal` |
| **`external()` (inferência)** | `CREATE TABLE ... AS SELECT * FROM external(<path>)` para CSV sem schema explícito e para Parquet (schema embutido) |
| **SQLAlchemy `create_engine`** | `pool_pre_ping=True`, `execution_options(stream_results=True)`, `connect_args` com timeout padrão; leitura em lotes de 10.000 linhas |

### Endpoints da API

Não há endpoints HTTP: a superfície pública são **tools MCP** (transporte stdio via FastMCP). Cada tool é documentada no padrão abaixo; a "requisição" é o objeto de argumentos da chamada MCP.

#### Visão geral

| Tool | Tipo | Descrição |
| --- | --- | --- |
| `create_hyper_from_file` | escrita local | Cria `.hyper` de CSV/Parquet (RF1–RF5). |
| `create_hyper_from_inline` | escrita local | Cria `.hyper` de colunas+linhas inline (RF6–RF8). |
| `extract_database_to_hyper` | leitura externa + escrita local | Materializa query de banco externo em `.hyper` (RF9–RF12). |
| `query_hyper` | leitura local | Consulta SQL de leitura sobre `.hyper` (RF13–RF15). |
| `inspect_hyper_schema` | leitura local | Lista schemas/tabelas/colunas/contagens (RF16–RF17). |
| `append_to_hyper` | escrita local | Append de arquivo ou inline em tabela existente (RF18). |
| `execute_hyper_sql` | escrita local | INSERT/UPDATE/DELETE/CREATE TABLE AS (RF19–RF20). |
| `publish_datasource` *(modificada)* | rede Tableau | Passa a aceitar `.hyper` além de `.tds`/`.tdsx` (RF21–RF22). |

---

#### `create_hyper_from_file`

Cria um `.hyper` a partir de CSV ou Parquet local. Sem `schema`, a inferência usa `external()`; com `schema`, cria `TableDefinition` explícita e carrega via `COPY FROM`.

**Parâmetros**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `source_path` | `str` | — | Deve existir e ter extensão `.csv`/`.parquet` (ou `source_format` explícito). |
| `hyper_path` | `str` | — | Destino; extensão `.hyper` obrigatória; diretório-pai deve existir. Sobrescreve se já existir. |
| `table_name` | `str` | `"Extract"` | Criada no schema `Extract` (compatibilidade com Tableau Server antigos). |
| `source_format` | `str` | `"auto"` | `auto` (pela extensão), `csv`, `parquet`. |
| `delimiter` | `str` | `","` | Somente CSV; 1 caractere. |
| `encoding` | `str` | `"utf-8"` | Somente CSV. |
| `header` | `bool` | `true` | Somente CSV. |
| `schema` | `list[InlineColumn] \| None` | `null` | Quando informado, desativa inferência (RF3). |
| `confirm_large_operation` | `bool` | `false` | Exigido quando o arquivo excede `HYPER_MAX_SOURCE_FILE_MB` (RF24). |

**Respostas**

| Resultado | Quando |
| --- | --- |
| `HyperCreateResult` | Criação concluída. |
| `VolumeAlert` | Arquivo acima do limiar sem confirmação. |
| `ToolError(INVALID_FILE)` | Origem inexistente/ilegível/extensão inválida. |
| `ToolError(HYPER_SCHEMA_MISMATCH)` | Schema explícito incompatível com os dados. |
| `ToolError(HYPER_SQL_ERROR)` | Falha do motor Hyper ao carregar (ex.: CSV corrompido). |

**Exemplo — sucesso**

```json
{
  "source_path": "/data/entrada/vendas_2026.csv",
  "hyper_path": "/data/extratos/vendas_2026.hyper",
  "delimiter": ";",
  "encoding": "latin-1"
}
```

Resposta: ver exemplo de `HyperCreateResult` em Modelos de dados.

**Exemplo — arquivo grande sem confirmação**

```json
{
  "source_path": "/data/entrada/historico_10anos.csv",
  "hyper_path": "/data/extratos/historico.hyper"
}
```

Resposta: ver exemplo de `VolumeAlert` em Modelos de dados.

> A criação com confirmação (`confirm_large_operation=true`) executa normalmente e replica o alerta em `warnings` do resultado, mantendo o rastro auditável.

---

#### `create_hyper_from_inline`

Cria um `.hyper` a partir de colunas e linhas enviadas na própria chamada. Indicada para de-paras e tabelas de referência; a docstring orienta o agente a usar `create_hyper_from_file` acima de `HYPER_MAX_INLINE_ROWS` (RF8).

**Parâmetros**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `hyper_path` | `str` | — | Destino `.hyper`; sobrescreve tabela homônima. |
| `table_name` | `str` | — | Nome da tabela (schema `Extract`). |
| `columns` | `list[InlineColumn]` | — | ≥ 1 coluna; nomes únicos. |
| `rows` | `list[list[Any]]` | — | Cada linha com a aridade de `columns`; valores coercíveis ao tipo declarado (datas em ISO-8601). |
| `confirm_large_operation` | `bool` | `false` | Exigido quando `len(rows)` excede `HYPER_MAX_INLINE_ROWS`. |

**Respostas**

| Resultado | Quando |
| --- | --- |
| `HyperCreateResult` (`source="inline"`) | Criação concluída. |
| `VolumeAlert` | Linhas inline acima do limiar sem confirmação. |
| `ToolError(HYPER_SCHEMA_MISMATCH)` | Linha com aridade errada ou valor não coercível — mensagem cita índice da linha e coluna (RF7). |
| `ToolError(VALIDATION_ERROR)` | `columns` vazio, nomes duplicados, tipo desconhecido. |

**Exemplo — sucesso**

```json
{
  "hyper_path": "/data/extratos/depara_filiais.hyper",
  "table_name": "depara_filiais",
  "columns": [
    { "name": "codigo", "type": "big_int", "nullable": false },
    { "name": "nome_filial", "type": "text" }
  ],
  "rows": [
    [101, "Campinas"],
    [102, "Santos"]
  ]
}
```

**Exemplo — linha inconsistente**

```json
{
  "status": "error",
  "error": {
    "code": "HYPER_SCHEMA_MISMATCH",
    "message": "Linha 3: valor 'abc' não é coercível para big_int na coluna 'codigo'. Nenhum dado foi gravado."
  }
}
```

> Validação é **tudo-ou-nada**: qualquer linha inválida aborta a gravação inteira antes de tocar o arquivo.

---

#### `extract_database_to_hyper`

Executa uma query (somente leitura) no banco nomeado e materializa o resultado em `.hyper`. A connection string vem exclusivamente de `HYPER_DB_CONN_<NOME>` (RF9–RF11).

**Parâmetros**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `connection_name` | `str` | — | Nome lógico; resolvido para `HYPER_DB_CONN_<NOME>` (uppercase). Nunca uma URL — valores contendo `://` são rejeitados com `VALIDATION_ERROR`. |
| `query` | `str` | — | SQL executado na origem como recebido; a origem é aberta em transação somente leitura quando o dialeto suportar. |
| `hyper_path` | `str` | — | Destino `.hyper`. |
| `table_name` | `str` | `"Extract"` | Tabela de destino no schema `Extract`. |

**Respostas**

| Resultado | Quando |
| --- | --- |
| `HyperCreateResult` (`source="database"`) | Extração concluída; alerta em `warnings` se exceder `HYPER_MAX_EXTRACT_ROWS`. |
| `ToolError(DB_CONNECTION_NOT_CONFIGURED)` | Variável de ambiente ausente. |
| `ToolError(DB_CONNECTION_FAILED)` | Host/porta/rede indisponível. |
| `ToolError(DB_AUTH_FAILED)` | Credencial recusada. |
| `ToolError(DB_QUERY_ERROR)` | SQL rejeitado pela origem. |

**Exemplo — sucesso**

```json
{
  "connection_name": "VENDAS",
  "query": "SELECT data_venda, filial, valor FROM fato_vendas WHERE ano = 2026",
  "hyper_path": "/data/extratos/vendas_dw.hyper"
}
```

**Exemplo — conexão não configurada**

```json
{
  "status": "error",
  "error": {
    "code": "DB_CONNECTION_NOT_CONFIGURED",
    "message": "Conexão 'FINANCEIRO' não configurada. Defina a variável de ambiente HYPER_DB_CONN_FINANCEIRO no host do servidor MCP."
  }
}
```

> O tipo das colunas do `.hyper` é derivado dos tipos do cursor SQLAlchemy (`cursor.description`/tipos do dialeto), com fallback para `text` em tipos exóticos — comportamento documentado na docstring.

---

#### `query_hyper`

Consulta SQL **de leitura** sobre um `.hyper`. Guarda de leitura: a primeira palavra-chave do comando deve ser `SELECT` ou `WITH`; caso contrário retorna `VALIDATION_ERROR` orientando a usar `execute_hyper_sql`.

**Parâmetros**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `hyper_path` | `str` | — | `.hyper` existente e válido. |
| `query` | `str` | — | `SELECT`/`WITH` apenas. |
| `max_rows` | `int \| None` | `null` → `HYPER_MAX_RESULT_ROWS` | 1–10.000; o motor lê `max_rows+1` linhas para detectar truncamento. |

**Respostas**

| Resultado | Quando |
| --- | --- |
| `HyperQueryResult` | Consulta executada (resultado vazio é sucesso com `rows=[]`). |
| `ToolError(HYPER_INVALID_FILE)` | Arquivo não é um `.hyper` válido. |
| `ToolError(HYPER_SQL_ERROR)` | SQL inválido — mensagem original do Hyper incluída (RF15). |
| `ToolError(VALIDATION_ERROR)` | Comando de escrita, `max_rows` fora do intervalo. |

**Exemplo — sucesso com truncamento**

```json
{
  "hyper_path": "/data/extratos/vendas_2026.hyper",
  "query": "SELECT filial, SUM(valor) AS total FROM \"Extract\".\"Extract\" GROUP BY filial",
  "max_rows": 100
}
```

```json
{
  "status": "success",
  "columns": [
    { "name": "filial", "type": "text", "nullable": true },
    { "name": "total", "type": "double", "nullable": true }
  ],
  "rows": [["Campinas", 1250341.55]],
  "row_count": 100,
  "truncated": true,
  "max_rows": 100
}
```

> Resultado vazio **não é erro** — espelha o padrão de `search_similar_content` (lista vazia = sucesso).

---

#### `inspect_hyper_schema`

Relatório estrutural completo de um `.hyper` — análogo local do `inspect_workbook_structure`.

**Parâmetros**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `hyper_path` | `str` | — | Arquivo existente com extensão `.hyper`. |

**Respostas**

| Resultado | Quando |
| --- | --- |
| `HyperSchemaReport` | Inspeção concluída (contagem de linhas `null` por tabela quando falhar, sem abortar o relatório). |
| `ToolError(HYPER_INVALID_FILE)` | Arquivo inexistente, extensão errada ou não abrível pelo Hyper (RF17). |

**Exemplo — sucesso**: ver `HyperSchemaReport` em Modelos de dados.

**Exemplo — arquivo inválido**

```json
{
  "status": "error",
  "error": {
    "code": "HYPER_INVALID_FILE",
    "message": "O arquivo '/data/entrada/vendas.csv' não é um arquivo .hyper válido. Use create_hyper_from_file para converter dados brutos em extrato."
  }
}
```

---

#### `append_to_hyper`

Acrescenta dados a uma tabela existente, a partir de arquivo (CSV/Parquet) **ou** de dados inline (`columns`+`rows`) — exatamente uma das duas origens deve ser informada. Compatibilidade de schema é validada antes de gravar (RF18).

**Parâmetros**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `hyper_path` | `str` | — | `.hyper` existente. |
| `table_name` | `str` | — | Tabela existente (schema `Extract` ou qualificada `schema.tabela`). |
| `source_path` | `str \| None` | `null` | Mutuamente exclusivo com `columns`/`rows`. |
| `columns` | `list[InlineColumn] \| None` | `null` | Com `rows`; mesma validação da criação inline. |
| `rows` | `list[list[Any]] \| None` | `null` | Com `columns`. |
| `confirm_large_operation` | `bool` | `false` | Mesmos limiares da origem correspondente (arquivo ou inline). |

**Respostas**

| Resultado | Quando |
| --- | --- |
| `HyperMutationResult` (`operation="append"`) | Append concluído com `affected_rows`. |
| `VolumeAlert` | Origem acima do limiar sem confirmação. |
| `ToolError(HYPER_SCHEMA_MISMATCH)` | Colunas da origem divergem da tabela alvo (nome/tipo/aridade). |
| `ToolError(NOT_FOUND)` | Tabela inexistente no arquivo. |
| `ToolError(VALIDATION_ERROR)` | Nenhuma origem, ou ambas, informadas. |

**Exemplo — sucesso (inline)**

```json
{
  "hyper_path": "/data/extratos/depara_filiais.hyper",
  "table_name": "depara_filiais",
  "columns": [
    { "name": "codigo", "type": "big_int", "nullable": false },
    { "name": "nome_filial", "type": "text" }
  ],
  "rows": [[103, "Sorocaba"]]
}
```

---

#### `execute_hyper_sql`

Executa um comando SQL de modificação (`INSERT`, `UPDATE`, `DELETE`) ou de derivação (`CREATE TABLE ... AS`) sobre o `.hyper` (RF19–RF20). Comandos `SELECT` são rejeitados com orientação para `query_hyper`.

**Parâmetros**

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `hyper_path` | `str` | — | `.hyper` existente. |
| `command` | `str` | — | Primeira palavra-chave em {`INSERT`, `UPDATE`, `DELETE`, `CREATE`}; um único comando por chamada. |

**Respostas**

| Resultado | Quando |
| --- | --- |
| `HyperMutationResult` | Comando executado; `operation` derivada da palavra-chave. |
| `ToolError(HYPER_SQL_ERROR)` | Comando rejeitado pelo motor Hyper. |
| `ToolError(HYPER_INVALID_FILE)` | Arquivo inválido. |
| `ToolError(VALIDATION_ERROR)` | Palavra-chave não permitida. |

**Exemplo — tabela derivada (RF20)**

```json
{
  "hyper_path": "/data/extratos/vendas_2026.hyper",
  "command": "CREATE TABLE \"Extract\".\"vendas_por_filial\" AS SELECT filial, SUM(valor_venda) AS total FROM \"Extract\".\"Extract\" GROUP BY filial"
}
```

```json
{
  "status": "success",
  "hyper_path": "/data/extratos/vendas_2026.hyper",
  "operation": "create_table_as",
  "affected_rows": 14,
  "table_name": "vendas_por_filial",
  "warnings": []
}
```

---

#### `publish_datasource` *(modificação — RF21–RF22)*

Única mudança: o conjunto de extensões válidas em `tools/deploy.py` passa de `{".tds", ".tdsx"}` para `{".tds", ".tdsx", ".hyper"}`; docstring atualizada citando o requisito de Tableau Server ≥ 2021.4 para `.hyper` multi-tabela (versões 2021.3↓ exigem tabela única `Extract.Extract`). Parâmetros, política de sobrescrita (`OVERWRITE_NOT_ALLOWED`), retorno `PublishResult` (com `content_id` para encadeamento com as tools de metadados — RF22) e tradução de erros permanecem intactos.

---

## Pontos de integração

- **Tableau Hyper API (`tableauhyperapi`)** — biblioteca local com runtime binário embarcado (~150 MB instalados); sem rede e sem autenticação; telemetria desativada (`DO_NOT_SEND_USAGE_DATA_TO_TABLEAU`). Erros (`HyperException`) traduzidos em `hyper/engine.py` para `HyperEngineError` com `ErrorCode`, preservando a `main_message` do motor (RF15) e removendo paths internos do runtime.
- **Bancos externos via SQLAlchemy** — somente leitura; URL de conexão exclusivamente do ambiente; drivers (ex.: `psycopg`, `pymssql`, `oracledb`) instalados pelo administrador conforme a fonte, documentados no README. Timeout de conexão padrão do driver + `pool_pre_ping`. Classificação de falha: exceções `OperationalError` de rede → `DB_CONNECTION_FAILED`; erros com códigos de autenticação do dialeto → `DB_AUTH_FAILED`; `ProgrammingError`/`DatabaseError` na execução → `DB_QUERY_ERROR`. Toda mensagem passa por sanitização (substring da URL e credenciais removidas) antes de sair do módulo.
- **Tableau Server/Cloud (publicação)** — inalterado: `tableau/client.py` com PAT (`SecretStr`), re-autenticação lazy e tradução de erros existente. O `.hyper` entra pelo mesmo `client.publish_datasource()`.

## Abordagem de testes

Meta: manter o gate `--cov-fail-under=80` do projeto. Estratégia em três camadas, conforme a skill `testing-standards`: unitários com `tableauhyperapi` e SQLAlchemy mockados (suite rápida), integração MCP in-memory (suite rápida) e integração real com runtime Hyper marcada com `@pytest.mark.integration`.

### Testes unitários

**`tests/validation/test_volume.py`** — regras puras, sem mocks:

1. `test_check_source_file_abaixo_do_limiar_retorna_lista_vazia`
2. `test_check_source_file_acima_do_limiar_retorna_dimensao_source_file_mb`
3. `test_check_source_file_exatamente_no_limiar_nao_excede`
4. `test_check_inline_rows_abaixo_do_limiar_retorna_lista_vazia`
5. `test_check_inline_rows_acima_do_limiar_retorna_dimensao_inline_rows`
6. `test_check_extracted_rows_acima_do_limiar_retorna_dimensao_extracted_rows`
7. `test_dimensao_excedida_inclui_limit_actual_e_risk_preenchidos`
8. `test_limiares_customizados_via_settings_sao_respeitados`

**`tests/test_config.py`** (estendido):

9. `test_settings_hyper_defaults_conservadores` (500 MB, 1.000 inline, 200 result, 5.000.000 extract)
10. `test_settings_hyper_limiares_lidos_do_ambiente`
11. `test_settings_hyper_limiar_invalido_gera_config_error_sem_segredos`

**`tests/test_models.py`** (estendido):

12. `test_hyper_create_result_serializa_status_success`
13. `test_volume_alert_serializa_status_volume_alert_e_dimensoes`
14. `test_hyper_query_result_row_count_e_truncated_consistentes`
15. `test_inline_column_tipo_desconhecido_rejeitado_na_validacao`
16. `test_error_code_contem_novos_codigos_hyper_e_db`
17. `test_hyper_table_info_row_count_nulo_permitido`

**`tests/hyper/test_engine.py`** — `tableauhyperapi` mockada (módulo inteiro via `monkeypatch`/`sys.modules`):

18. `test_hyper_session_inicia_processo_com_telemetria_desativada`
19. `test_hyper_session_encerra_processo_mesmo_com_excecao`
20. `test_create_table_from_file_csv_com_schema_usa_copy_com_delimitador_e_encoding`
21. `test_create_table_from_file_csv_sem_schema_usa_external_para_inferencia`
22. `test_create_table_from_file_parquet_usa_external`
23. `test_create_table_from_file_escapa_path_com_escape_string_literal`
24. `test_create_table_from_rows_insere_via_inserter_e_retorna_contagem`
25. `test_append_rows_valida_compatibilidade_antes_de_inserir`
26. `test_append_rows_schema_incompativel_levanta_hyper_schema_mismatch`
27. `test_query_le_max_rows_mais_um_e_sinaliza_truncamento`
28. `test_query_serializa_date_e_timestamp_como_iso8601`
29. `test_query_serializa_numeric_como_string`
30. `test_execute_retorna_linhas_afetadas`
31. `test_describe_lista_todos_schemas_e_tabelas_com_colunas`
32. `test_describe_contagem_de_linhas_falha_vira_none_sem_abortar`
33. `test_hyper_exception_traduzida_para_hyper_engine_error_com_mensagem_original`
34. `test_arquivo_nao_hyper_traduzido_para_hyper_invalid_file`

**`tests/hyper/test_db.py`** — SQLAlchemy mockada:

35. `test_resolve_connection_le_variavel_com_nome_uppercase`
36. `test_resolve_connection_ausente_levanta_db_connection_not_configured`
37. `test_resolve_connection_nao_loga_nem_inclui_url_na_excecao`
38. `test_extract_to_hyper_usa_stream_results_e_lotes`
39. `test_extract_to_hyper_mapeia_tipos_do_cursor_para_sqltype`
40. `test_extract_to_hyper_tipo_exotico_faz_fallback_para_text`
41. `test_operational_error_de_rede_vira_db_connection_failed`
42. `test_erro_de_autenticacao_vira_db_auth_failed`
43. `test_programming_error_vira_db_query_error_com_mensagem_sanitizada`
44. `test_sanitizacao_remove_url_usuario_senha_e_host_da_mensagem`
45. `test_resultado_vazio_cria_hyper_com_zero_linhas_sem_erro`

**`tests/tools/test_hyper.py`** — engine/db mockados (padrão fixture `client`/`session` de `test_deploy.py`):

46. `test_create_hyper_from_file_sucesso_retorna_hyper_create_result`
47. `test_create_hyper_from_file_origem_inexistente_retorna_invalid_file`
48. `test_create_hyper_from_file_extensao_desconhecida_sem_format_retorna_invalid_file`
49. `test_create_hyper_from_file_acima_do_limiar_sem_confirmacao_retorna_volume_alert`
50. `test_create_hyper_from_file_acima_do_limiar_com_confirmacao_executa_e_adiciona_warning`
51. `test_create_hyper_from_file_valida_antes_de_abrir_hyper_session` (nenhum engine chamado em erro local)
52. `test_create_hyper_from_inline_sucesso_retorna_source_inline`
53. `test_create_hyper_from_inline_linha_com_aridade_errada_retorna_schema_mismatch_com_indice`
54. `test_create_hyper_from_inline_valor_nao_coercivel_retorna_schema_mismatch`
55. `test_create_hyper_from_inline_colunas_duplicadas_retorna_validation_error`
56. `test_create_hyper_from_inline_acima_do_limiar_sem_confirmacao_retorna_volume_alert`
57. `test_extract_database_to_hyper_sucesso_retorna_source_database`
58. `test_extract_database_to_hyper_connection_name_com_url_retorna_validation_error`
59. `test_extract_database_to_hyper_conexao_nao_configurada_retorna_erro_com_nome_da_variavel`
60. `test_extract_database_to_hyper_linhas_acima_do_limiar_conclui_com_warning`
61. `test_query_hyper_sucesso_retorna_colunas_e_linhas`
62. `test_query_hyper_resultado_vazio_e_sucesso`
63. `test_query_hyper_comando_de_escrita_retorna_validation_error_orientando_execute_hyper_sql`
64. `test_query_hyper_max_rows_default_vem_de_settings`
65. `test_query_hyper_max_rows_fora_do_intervalo_retorna_validation_error`
66. `test_query_hyper_sql_invalido_retorna_hyper_sql_error_com_mensagem_do_motor`
67. `test_inspect_hyper_schema_sucesso_retorna_relatorio_completo`
68. `test_inspect_hyper_schema_arquivo_invalido_retorna_hyper_invalid_file`
69. `test_append_to_hyper_inline_sucesso_retorna_affected_rows`
70. `test_append_to_hyper_de_arquivo_sucesso`
71. `test_append_to_hyper_sem_origem_retorna_validation_error`
72. `test_append_to_hyper_com_duas_origens_retorna_validation_error`
73. `test_append_to_hyper_tabela_inexistente_retorna_not_found`
74. `test_execute_hyper_sql_update_retorna_linhas_afetadas`
75. `test_execute_hyper_sql_create_table_as_retorna_operation_create_table_as`
76. `test_execute_hyper_sql_select_retorna_validation_error_orientando_query_hyper`
77. `test_execute_hyper_sql_palavra_chave_drop_retorna_validation_error`
78. `test_nenhum_retorno_ou_log_contem_connection_string` (asserção sobre caplog + payloads)

**`tests/tools/test_deploy.py`** (estendido):

79. `test_publish_datasource_aceita_extensao_hyper`
80. `test_publish_datasource_hyper_respeita_politica_de_sobrescrita`
81. `test_publish_datasource_hyper_retorna_content_id_para_encadeamento`

### Testes de integração

**`tests/test_mcp_integration.py`** (estendido — FastMCP in-memory, suite rápida):

82. `test_servidor_expoe_dezessete_tools` (10 existentes + 7 novas)
83. `test_tools_hyper_declaram_schemas_de_entrada_validos`
84. `test_chamada_create_hyper_from_inline_via_cliente_mcp_serializa_resultado`
85. `test_chamada_query_hyper_com_arquivo_inexistente_serializa_tool_error`
86. `test_volume_alert_serializado_via_transporte_mcp_mantem_status_volume_alert`

**`tests/integration/test_hyper_real.py`** — novo, `@pytest.mark.integration`, usa o runtime Hyper real (sem rede; requer `tableauhyperapi` instalada), arquivos em `tmp_path`:

87. `test_ciclo_completo_csv_para_hyper_query_e_inspecao` (cria CSV → `.hyper` → inspeciona → consulta → confere contagens)
88. `test_ciclo_inline_criar_append_e_derivar_tabela`
89. `test_parquet_para_hyper_com_inferencia_de_schema`
90. `test_update_e_delete_refletem_no_row_count`
91. `test_extract_database_para_hyper_com_sqlite_local` (SQLAlchemy + SQLite em `tmp_path` como banco externo real)
92. `test_publicacao_hyper_no_tableau_real` (junto aos demais testes `integration` já existentes, requer credenciais)

**Requisitos de dados de teste**: CSVs pequenos gerados em `tmp_path` pelas próprias fixtures (sem arquivos binários versionados); fixture `sample_hyper` em `tests/conftest.py` que constrói um `.hyper` mínimo sob demanda (marcada para reuso apenas nos testes `integration`); fixture `hyper_env` definindo limiares baixos para exercitar alertas sem arquivos grandes.

### Testes E2E

Não aplicável — não há frontend. O fluxo ponta a ponta "CSV → `.hyper` → datasource publicado" (métrica de sucesso do PRD) é coberto pelos testes `integration` (casos 87 e 92) executados em ambiente de homologação com `uv run pytest -m integration`.

## Sequenciamento do desenvolvimento

### Ordem de construção

1. **Fundações — contratos e config**: novos `ErrorCode`, modelos Pydantic em `models.py`, limiares em `config.py`, `validation/volume.py` e seus testes. Sem dependência de bibliotecas novas; destrava todo o restante.
2. **Engine Hyper + caminho de leitura**: `hyper/engine.py` (`hyper_session`, `describe`, `query`) e as tools `inspect_hyper_schema` e `query_hyper`. Valida a integração com o runtime Hyper com o menor risco (somente leitura) e estabelece o padrão de tradução de erros.
3. **Criação local**: `create_hyper_from_file` (inferência via `external()` + `COPY FROM` com schema) e `create_hyper_from_inline` (`Inserter` + validação tudo-ou-nada), integradas às salvaguardas de volume (`VolumeAlert`).
4. **Mutação**: `append_to_hyper` e `execute_hyper_sql` (reutilizam engine e validações já prontos).
5. **Extração de banco**: `hyper/db.py` (SQLAlchemy, sanitização, classificação de erros) e `extract_database_to_hyper`. Fica por último entre as tools por ter a maior superfície de erro externa.
6. **Publicação e registro**: extensão de `publish_datasource` (`.hyper`), `hyper.register(mcp)` em `server.py`, testes de integração MCP in-memory.
7. **Fechamento**: testes `integration` reais, `.env.example`, README (Capacidade 5, drivers de banco, ciclo de vida/limpeza dos `.hyper` locais), verificação `ruff` + cobertura.

### Dependências técnicas

- `tableauhyperapi>=0.0.23576` (PyPI; suporta Python 3.13; plataformas x64/arm64 Linux/macOS/Windows) — runtime binário embarcado aumenta o tamanho do ambiente (~150 MB).
- `sqlalchemy>=2.0` — core apenas; drivers de banco **não** entram como dependência do projeto (instalação pelo administrador conforme a fonte; SQLite embutido cobre os testes).
- Testes `integration` de publicação exigem as credenciais Tableau já usadas pela suite existente (`.env` real); os demais testes `integration` de Hyper rodam offline.
- Nenhuma infraestrutura nova (restrição do PRD).

## Monitoramento e observabilidade

O projeto não possui Prometheus/Grafana (restrição "sem serviços adicionais"); a observabilidade segue o padrão atual — `logging` do Python com `logger = logging.getLogger(__name__)` por módulo:

- **INFO** — início/fim de operações com dimensões não sensíveis: tool, arquivo destino (path), tabela, linhas processadas, duração. Ex.: `"create_hyper_from_file: 184230 linhas em /data/extratos/vendas_2026.hyper (12.4s)"`.
- **WARNING** — limiares excedidos (com e sem confirmação), truncamento de resultados, fallback de tipos na extração de banco.
- **DEBUG** — parâmetros de `COPY`/`external()` (sem conteúdo de dados), tamanho de lotes de extração.
- **Proibições absolutas (RF11)**: nenhuma connection string, credencial, valor de linha de dados ou SQL de origem completo em logs de nível INFO+ (a query externa só aparece em DEBUG, e mesmo aí sem a URL de conexão).
- Auditabilidade primária permanece nos **retornos estruturados** das tools (relatórios com contagens, warnings e códigos de erro), consumíveis pelo agente e repassáveis ao usuário.

## Considerações técnicas

### Principais decisões

1. **SQLAlchemy Core para bancos externos** (decisão do usuário) — a Hyper API não conecta em bancos; SQLAlchemy dá connection string em URL padrão, ecossistema amplo de dialetos e streaming (`stream_results`) sem ORM. Alternativas descartadas: `pyodbc` puro (exige unixODBC/drivers ODBC configurados no host, setup mais frágil em Linux) e ADBC (Arrow-nativo, porém ecossistema de drivers ainda limitado).
2. **Conexões múltiplas nomeadas `HYPER_DB_CONN_<NOME>`** (decisão do usuário) — a tool recebe apenas o nome lógico; suporta vários bancos por instância sem redeploy. Como `pydantic-settings` não modela chaves dinâmicas, a resolução é feita por `hyper/db.py::resolve_connection` lendo `os.environ` diretamente (com o `.env` já carregado pelo `python-dotenv` do bootstrap) — desvio pontual e documentado do padrão `Settings`.
3. **Estender `publish_datasource` em vez de criar tool nova** (decisão do usuário) — TSC publica `.hyper` diretamente (Server ≥ 2021.4); mudança de uma linha no conjunto de extensões + docstring, zero duplicação de fluxo/política de sobrescrita.
4. **Paths livres, sem workspace sandbox** (decisão do usuário) — o agente informa caminhos absolutos de leitura e escrita. Contrapartida: o ciclo de vida/limpeza dos `.hyper` intermediários é responsabilidade do operador e será documentado no README (recomendação de diretório dedicado e limpeza pós-publicação), atendendo à restrição de privacidade do PRD por documentação, não por enforcement.
5. **`HyperProcess` por chamada** (dentro de `hyper_session()`) — custo de inicialização (~1s) aceito em troca de ausência de estado residente, isolamento entre chamadas e aderência ao modelo sob demanda. Alternativa descartada: processo singleton lazy (economiza latência, mas cria ciclo de vida órfão no processo MCP e complica testes).
6. **`VolumeAlert` como retorno tipado próprio** (não `ToolError`) — o PRD exige alerta *não bloqueante*; um erro sugeriria falha. O discriminador `status="volume_alert"` torna o fluxo de confirmação explícito no contrato e trivialmente tratável pelo agente (RF24).
7. **Guarda de leitura em `query_hyper` por palavra-chave inicial** (`SELECT`/`WITH`) — separação leitura×escrita é de *ergonomia do agente*, não segurança (o mesmo arquivo é gravável via `execute_hyper_sql`); a heurística simples e documentada evita parser SQL próprio.
8. **Inferência de schema via `external()` + carga explícita via `COPY`** — `CREATE TABLE AS SELECT * FROM external(...)` cobre RF3 (inferência) para CSV e Parquet; quando o agente fornece schema, `TableDefinition` + `COPY FROM` dá controle total e erros de tipo mais claros.

### Riscos conhecidos

- **Tamanho/portabilidade do runtime Hyper**: `tableauhyperapi` embarca binários (~150 MB) e restringe plataformas suportadas. Mitigação: dependência principal (não opcional) documentada no QUICKSTART; falha de import gera erro claro na inicialização do servidor.
- **Classificação de erros de banco heterogênea entre dialetos** (RF12): códigos de autenticação variam por driver. Mitigação: classificação por tipo de exceção SQLAlchemy + heurística de mensagens por dialeto, com fallback para `DB_CONNECTION_FAILED`; testes unitários por categoria e teste real com SQLite.
- **Vazamento de credencial em mensagens de driver** (RF11): drivers às vezes ecoam a URL na exceção. Mitigação: sanitização obrigatória em `hyper/db.py` (remoção de URL, usuário, senha, host) coberta por teste dedicado (caso 44 e 78).
- **Tipos do cursor → SqlType imperfeito**: dialetos reportam tipos com fidelidade variável. Mitigação: fallback para `text` com `warning` no resultado; documentado na docstring da tool.
- **Estimativa de volume impossível pré-extração** (RF23): não há como saber o total de linhas antes de executar a query. Mitigação aceita: alerta pós-execução em `warnings` (dimensão `extracted_rows`), comportamento documentado no contrato.
- **Compatibilidade de `.hyper` multi-tabela na publicação**: Tableau Server ≤ 2021.3 exige tabela única `Extract.Extract`. Mitigação: default `table_name="Extract"` no schema `Extract` em todas as criações; aviso na docstring de `publish_datasource`.
- **Concorrência sobre o mesmo `.hyper`**: o Hyper trava o arquivo por conexão; chamadas simultâneas do agente sobre o mesmo arquivo falharão. Mitigação: erro traduzido com mensagem acionável (repetir após concluir a operação anterior); sem lock manager próprio (fora de escopo).

### Conformidade com skills

- **`code-standards`** — aplicável integralmente: tools finas com docstring-contrato, Pydantic para entrada/saída, type hints nativos, integração externa isolada em módulo próprio (`hyper/` análogo a `tableau/`), segredos somente via ambiente, mensagens de erro acionáveis sem dados sensíveis, `ruff` (88 colunas).
- **`testing-standards`** — aplicável integralmente: pirâmide com unitários mockando `tableauhyperapi`/SQLAlchemy, integração MCP in-memory na suite rápida, runtime real sob `@pytest.mark.integration`, fixtures em `conftest.py`, `tmp_path` para arquivos, cobertura ≥ 80%, nomenclatura `test_<unidade>_<cenario>_<resultado>`.
- **`criar-tasks`** — próxima etapa do fluxo: derivar `tasks.md` desta techspec.
- **`executar-qa` / `executar-review`** — usarão as métricas de sucesso do PRD (fluxo CSV→publicação em homologação) e este documento como referência de conformidade.

### Arquivos relevantes e dependentes

| Arquivo | Papel nesta feature |
| --- | --- |
| `src/mcp_tableau/tools/hyper.py` | **novo** — sete tools MCP + `register(mcp)` |
| `src/mcp_tableau/hyper/__init__.py` | **novo** — pacote de integração Hyper |
| `src/mcp_tableau/hyper/engine.py` | **novo** — wrapper `tableauhyperapi` (`hyper_session`, operações, tradução de erros) |
| `src/mcp_tableau/hyper/db.py` | **novo** — extração via SQLAlchemy, resolução `HYPER_DB_CONN_<NOME>`, sanitização |
| `src/mcp_tableau/validation/volume.py` | **novo** — regras puras de limiares de volume |
| `src/mcp_tableau/models.py` | modificado — novos contratos e `ErrorCode` |
| `src/mcp_tableau/config.py` | modificado — limiares `HYPER_*` em `Settings` |
| `src/mcp_tableau/tools/deploy.py` | modificado — `.hyper` aceito em `publish_datasource` |
| `src/mcp_tableau/server.py` | modificado — `hyper.register(mcp)` |
| `pyproject.toml` | modificado — `tableauhyperapi`, `sqlalchemy` |
| `.env.example` | modificado — seção `# Hyper` (limiares + exemplo `HYPER_DB_CONN_<NOME>`) |
| `README.md` / `QUICKSTART.md` | modificados — Capacidade 5, drivers de banco, ciclo de vida dos `.hyper` |
| `tests/validation/test_volume.py` | **novo** |
| `tests/hyper/test_engine.py` | **novo** |
| `tests/hyper/test_db.py` | **novo** |
| `tests/tools/test_hyper.py` | **novo** |
| `tests/integration/test_hyper_real.py` | **novo** |
| `tests/tools/test_deploy.py` | modificado — casos `.hyper` |
| `tests/test_mcp_integration.py` | modificado — 17 tools, serialização dos novos contratos |
| `tests/test_config.py` / `tests/test_models.py` | modificados — limiares e contratos novos |
| `tests/conftest.py` | modificado — fixtures `hyper_env`, `sample_hyper` |
