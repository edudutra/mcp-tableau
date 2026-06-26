# MCP Tableau

Servidor [Model Context Protocol](https://modelcontextprotocol.io) construído com
[FastMCP](https://github.com/jlowin/fastmcp) que expõe ferramentas para automatizar
o ciclo de **publicação e validação** de conteúdo no Tableau Server / Tableau Cloud.

O objetivo é permitir que um agente de IA autônomo complete o fluxo
**descobrir → construir → validar → publicar** sem intervenção humana, com retornos
estruturados e auditáveis. As capacidades cobrem:

- **Deploy** — publicar/sobrescrever workbooks (`.twb`/`.twbx`) e datasources (`.tds`/`.tdsx`).
- **Inspeção visual** — renderizar PNG/PDF de views e sinalizar telas em branco.
- **QA estrutural** — ler campos, filtros e conexões; auditar complexidade contra boas práticas.
- **Metadados** — linhagem ascendente/descendente, dicionário de dados e busca de similaridade.

> ℹ️ Em desenvolvimento. A fundação (configuração, contratos Pydantic e bootstrap do
> servidor) está concluída; as ferramentas de cada capacidade são adicionadas
> incrementalmente. Veja [`tasks/prd-mcp-tableau/`](tasks/prd-mcp-tableau/).

## Stack

- **Linguagem**: Python `>= 3.13`
- **Framework MCP**: FastMCP (`>= 3.4.2`), transporte **stdio**
- **Integração Tableau**: `tableauserverclient` (REST API) + Metadata API (GraphQL)
- **Parsing/validação**: `tableaudocumentapi`, `Pillow`, `rapidfuzz`, `pydantic`
- **Gerenciador de pacotes**: [uv](https://docs.astral.sh/uv/)

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

> O arquivo `.env` é ignorado pelo Git. **Nunca** commite credenciais.

## Execução

Inicia o servidor MCP em transporte stdio:

```bash
uv run python main.py
```

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
uv run pytest                                               # suite rápida
uv run pytest --cov=mcp_tableau --cov-report=term-missing   # com cobertura
uv run pytest -m "not integration"                          # exclui integração real
```

Meta de cobertura: **≥ 80%**. Lint e formatação com Ruff:

```bash
uv run ruff check .
uv run ruff format .
```

## Convenções

Padrões de código e de testes ficam nas skills do projeto
([`code-standards`](.claude/skills/code-standards/SKILL.md) e
[`testing-standards`](.claude/skills/testing-standards/SKILL.md)). Consulte também
o [`AGENTS.md`](AGENTS.md) para a visão geral e boas práticas adotadas.
