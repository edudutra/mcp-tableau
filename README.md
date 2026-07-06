# MCP Tableau

Servidor [Model Context Protocol](https://modelcontextprotocol.io) construído com
[FastMCP](https://github.com/jlowin/fastmcp) que expõe ferramentas para automatizar
o ciclo de **publicação e validação** de conteúdo no Tableau Server / Tableau Cloud.

O objetivo é permitir que um agente de IA autônomo complete o fluxo
**descobrir → construir → validar → publicar** sem intervenção humana, com retornos
estruturados e auditáveis. As capacidades cobrem:

- **Deploy** — publicar/sobrescrever workbooks (`.twb`/`.twbx`) e datasources (`.tds`/`.tdsx`/`.hyper`).
- **Inspeção visual** — renderizar PNG/PDF de views e sinalizar telas em branco.
- **QA estrutural** — ler campos, filtros e conexões; auditar complexidade contra boas práticas.
- **Metadados** — linhagem ascendente/descendente, dicionário de dados e busca de similaridade.
- **Hyper Datasources** — criar, consultar, inspecionar e transformar extratos `.hyper` locais (de CSV/Parquet, dados inline ou bancos externos) antes de publicar.



> 🚀 **Começando agora?** Veja o [**QUICKSTART**](QUICKSTART.md) para rodar o servidor
> via `uvx` e configurar nos principais agentes (Claude, GitHub Copilot, Cursor, Kiro e outros).

## Stack

- **Linguagem**: Python `>= 3.13`
- **Framework MCP**: FastMCP (`>= 3.4.2`), transporte **stdio**
- **Integração Tableau**: `tableauserverclient` (REST API) + Metadata API (GraphQL)
- **Extratos Hyper**: `tableauhyperapi` (runtime local `.hyper`) + `sqlalchemy` (extração de bancos externos)
- **Parsing/validação**: `tableaudocumentapi`, `Pillow`, `rapidfuzz`, `pydantic`
- **Gerenciador de pacotes**: [uv](https://docs.astral.sh/uv/)

> ⚠️ O `tableauhyperapi` embarca um runtime binário (~150 MB) e só roda em
> plataformas x64/arm64 de Linux, macOS e Windows. Ver [QUICKSTART](QUICKSTART.md).

## Instalação

Requer [uv](https://docs.astral.sh/uv/) e Python `>= 3.13`.

```bash
uv sync
```

## Configuração

As credenciais são lidas de variáveis de ambiente (autenticação via
**Personal Access Token**). Copie o exemplo e preencha os valores:

```bash
cp .env.example .env
```

| Variável | Obrigatória | Default | Descrição |
| --- | --- | --- | --- |
| `TABLEAU_SERVER_URL` | sim | — | URL do Tableau Server/Cloud. |
| `TABLEAU_PAT_NAME` | sim | — | Nome do Personal Access Token. |
| `TABLEAU_PAT_SECRET` | sim | — | Segredo do PAT (nunca é logado nem retornado). |
| `TABLEAU_SITE` | não | `""` | Content URL do site (vazio = site default no Server). |
| `TABLEAU_TIMEOUT` | não | `30` | Tempo limite das requisições à API, em segundos. |
| `MAX_FILTERS` | não | `15` | Limiar de filtros para auditoria de complexidade. |
| `MAX_WORKSHEETS` | não | `20` | Limiar de worksheets. |
| `MAX_DATA_SOURCES` | não | `5` | Limiar de fontes de dados. |
| `HYPER_MAX_SOURCE_FILE_MB` | não | `500` | Limiar de tamanho (MB) do arquivo de origem em `create_hyper_from_file`. |
| `HYPER_MAX_INLINE_ROWS` | não | `1000` | Limiar de linhas inline em `create_hyper_from_inline`. |
| `HYPER_MAX_RESULT_ROWS` | não | `200` | Default de linhas retornadas por `query_hyper` (teto rígido 10.000). |
| `HYPER_MAX_EXTRACT_ROWS` | não | `5000000` | Limiar de linhas extraídas em `extract_database_to_hyper`. |
| `HYPER_DB_CONN_<NOME>` | não | — | Connection string SQLAlchemy de uma conexão nomeada (ver Capacidade 5). |

> O arquivo `.env` é ignorado pelo Git. **Nunca** commite credenciais.
>
> Os limiares `HYPER_*` geram **alertas não bloqueantes** (nunca bloqueio): ao
> exceder um limiar, a tool retorna um `VolumeAlert` e a operação só prossegue com
> `confirm_large_operation=true`.

## Execução

Inicia o servidor MCP em transporte stdio:

```bash
uv run python main.py
```

## Capacidade 5 — Hyper Datasources

Ferramentas para o ciclo de vida **local** de extratos `.hyper` antes da
publicação. Todas operam sobre caminhos locais informados pelo agente e delegam ao
runtime `tableauhyperapi` (iniciado sob demanda, sem processo residente).

| Ferramenta | O que faz |
| --- | --- |
| `create_hyper_from_file` | Cria um `.hyper` a partir de CSV/Parquet. Parquet infere o schema automaticamente; para **CSV informe `schema` explícito** (o runtime não infere schema de CSV). |
| `create_hyper_from_inline` | Cria um `.hyper` a partir de colunas + linhas enviadas na chamada (de-paras e tabelas de referência pequenas). |
| `extract_database_to_hyper` | Extrai o resultado de uma query de um banco externo (via conexão nomeada) para um `.hyper`. |
| `inspect_hyper_schema` | Lista schemas, tabelas, colunas e contagem de linhas de um `.hyper`. |
| `query_hyper` | Executa uma consulta **de leitura** (`SELECT`/`WITH`) com truncamento configurável. |
| `append_to_hyper` | Acrescenta dados (de arquivo ou inline) a uma tabela existente, validando o schema antes de gravar. |
| `execute_hyper_sql` | Executa um comando de **modificação** (`INSERT`/`UPDATE`/`DELETE`/`CREATE TABLE AS`). |

O `.hyper` gerado é publicado como datasource com `publish_datasource` (aceita
`.tds`/`.tdsx`/`.hyper`), fechando o fluxo **CSV/banco → `.hyper` → datasource**.

### Conexões de banco externo (nomeadas)

`extract_database_to_hyper` recebe **apenas o nome lógico** da conexão — a
connection string vem da variável de ambiente `HYPER_DB_CONN_<NOME>` (com `<NOME>`
em maiúsculas) no host do servidor MCP. Credenciais **nunca** são parâmetro das
tools, nem aparecem em logs, erros ou retornos.

```bash
# A tool chamada com connection_name="VENDAS" lê esta variável:
HYPER_DB_CONN_VENDAS=postgresql+psycopg://usuario:senha@host:5432/base
```

**Drivers de banco não são dependência do projeto** — apenas o SQLAlchemy Core é
instalado. O administrador instala no host o driver correspondente a cada fonte,
conforme a connection string usada:

| Fonte | Driver (exemplo) | Connection string |
| --- | --- | --- |
| PostgreSQL | `psycopg` | `postgresql+psycopg://…` |
| SQL Server | `pymssql` | `mssql+pymssql://…` |
| Oracle | `oracledb` | `oracle+oracledb://…` |
| MySQL | `pymysql` | `mysql+pymysql://…` |
| SQLite | (embutido) | `sqlite:///caminho/arquivo.db` |

### Ciclo de vida e limpeza dos `.hyper`

O agente informa caminhos absolutos de leitura e escrita — **não há workspace
sandbox**. A localização e a limpeza dos `.hyper` intermediários são
responsabilidade do operador. Recomendações:

- Use um **diretório dedicado** para os extratos (ex.: `/data/extratos/`), fora de
  áreas versionadas ou sincronizadas.
- **Remova os `.hyper` intermediários após a publicação** — são reprodutíveis a
  partir da origem e podem ocupar bastante espaço.
- Trate o conteúdo dos extratos como dado sensível: aplique as mesmas políticas de
  acesso/retenção da fonte original.

## Estrutura do projeto

```
mcp-tableau/
├── src/mcp_tableau/
│   ├── __init__.py          # versão do pacote
│   ├── server.py            # instância FastMCP + registro das tools (stdio)
│   ├── config.py            # Settings (env) e carregamento validado
│   ├── models.py            # contratos Pydantic de saída + envelope ToolError
│   ├── tableau/             # integração REST (client.py) e GraphQL (metadata.py)
│   ├── tools/               # ferramentas MCP por capacidade
│   └── validation/          # regras de validação puras (sem rede)
├── tests/                   # testes espelhando src/ (pytest)
├── main.py                  # ponto de entrada (inicia o servidor)
└── pyproject.toml           # dependências e configuração de ferramentas
```

## Testes

A suite rápida (unitários + integração MCP in-memory) mocka toda a rede/Tableau:

```bash
uv run pytest                                               # suite rápida + cobertura
uv run pytest -m integration                                # integração com Tableau real
```

A suite rápida exclui a integração real e aplica o gate de cobertura **≥ 80%**
(`--cov-fail-under=80`) automaticamente — ambos configurados em `addopts` no
`pyproject.toml`. A integração com Tableau real (publish/download roundtrip, render PNG e
linhagem) é marcada com `@pytest.mark.integration`, fica fora da suite rápida e só roda
com `TABLEAU_INTEGRATION=1` e as variáveis de sandbox definidas
(`TABLEAU_IT_WORKBOOK_PATH`, `TABLEAU_IT_PROJECT`, `TABLEAU_IT_VIEW_ID`,
`TABLEAU_IT_DATASOURCE_ID`); caso contrário, esses testes são pulados.

Os testes de integração do Hyper (`tests/integration/test_hyper_real.py`) usam o
runtime real do `tableauhyperapi` e **rodam offline** (sem Tableau): pulam apenas
se o runtime não estiver instalado. A exceção é a publicação do `.hyper` no
Tableau real, que exige `TABLEAU_INTEGRATION=1` + `TABLEAU_IT_PROJECT`.

Lint e formatação com Ruff:

```bash
uv run ruff check .
uv run ruff format .
```

## Convenções

Padrões de código e de testes ficam nas skills do projeto
([`code-standards`](.claude/skills/code-standards/SKILL.md) e
[`testing-standards`](.claude/skills/testing-standards/SKILL.md)). Consulte também
o [`AGENTS.md`](AGENTS.md) para a visão geral e boas práticas adotadas.
