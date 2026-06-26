# Quickstart — MCP Tableau

Guia rápido para usar o **MCP Tableau** nos principais agentes de IA. O servidor
roda em transporte **stdio** e é executado diretamente do repositório remoto com
[`uvx`](https://docs.astral.sh/uv/guides/tools/), sem clonar nem instalar nada
manualmente.

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/getting-started/installation/) instalado (fornece o `uvx`).
- Um **Personal Access Token (PAT)** do Tableau Server/Cloud.
- Python `>= 3.13` (o `uvx` baixa automaticamente se necessário).

Verifique o `uv`:

```bash
uv --version
```

## Comando de execução

O servidor é iniciado com `uvx` apontando direto para o repositório remoto:

```bash
uvx --from git+https://github.com/edudutra/mcp-tableau.git mcp-tableau
```

> O `uvx` resolve as dependências em um ambiente isolado e efêmero a cada execução.
> Para fixar uma versão, use uma tag ou commit: `git+https://github.com/edudutra/mcp-tableau.git@v0.1.0`.

## Variáveis de ambiente

As credenciais são lidas do ambiente (nunca são logadas nem retornadas):

| Variável | Obrigatória | Default | Descrição |
| --- | --- | --- | --- |
| `TABLEAU_SERVER_URL` | sim | — | URL do Tableau Server/Cloud. |
| `TABLEAU_PAT_NAME` | sim | — | Nome do Personal Access Token. |
| `TABLEAU_PAT_SECRET` | sim | — | Segredo do PAT. |
| `TABLEAU_SITE` | não | `""` | Content URL do site (vazio = site default no Server). |
| `TABLEAU_TIMEOUT` | não | `30` | Tempo limite das requisições, em segundos. |
| `TABLEAU_CA_BUNDLE` | não | `""` | Caminho de um PEM com a CA corporativa (redes com interceptação TLS). |
| `MAX_FILTERS` | não | `15` | Limiar de filtros para auditoria de complexidade. |
| `MAX_WORKSHEETS` | não | `20` | Limiar de worksheets. |
| `MAX_DATA_SOURCES` | não | `5` | Limiar de fontes de dados. |

> **Nunca** commite o segredo do PAT. Configure-o sempre via ambiente do agente.

## Configuração por agente

Em todos os agentes a estrutura é a mesma: um servidor MCP chamado `tableau`, com
`command: uvx`, os `args` apontando para o repositório, e o bloco `env` com as
credenciais.

### Claude Desktop

Edite o arquivo de configuração:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tableau": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/edudutra/mcp-tableau.git",
        "mcp-tableau"
      ],
      "env": {
        "TABLEAU_SERVER_URL": "https://SEU-SERVIDOR.online.tableau.com",
        "TABLEAU_SITE": "seu-site",
        "TABLEAU_PAT_NAME": "seu-pat",
        "TABLEAU_PAT_SECRET": "seu-segredo"
      }
    }
  }
}
```

Reinicie o Claude Desktop após salvar.

### GitHub Copilot (VS Code)

Crie `.vscode/mcp.json` no workspace (ou use o comando **MCP: Add Server**):

```json
{
  "servers": {
    "tableau": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/edudutra/mcp-tableau.git",
        "mcp-tableau"
      ],
      "env": {
        "TABLEAU_SERVER_URL": "https://SEU-SERVIDOR.online.tableau.com",
        "TABLEAU_SITE": "seu-site",
        "TABLEAU_PAT_NAME": "seu-pat",
        "TABLEAU_PAT_SECRET": "seu-segredo"
      }
    }
  }
}
```

Abra o **Chat** no modo *Agent* e habilite o servidor `tableau` na lista de ferramentas.

> Para disponibilizar globalmente (todos os workspaces), adicione o mesmo bloco
> `servers` em **Settings → `mcp`** (`settings.json` do usuário).

### Cursor

Crie `.cursor/mcp.json` no projeto (ou `~/.cursor/mcp.json` para uso global):

```json
{
  "mcpServers": {
    "tableau": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/edudutra/mcp-tableau.git",
        "mcp-tableau"
      ],
      "env": {
        "TABLEAU_SERVER_URL": "https://SEU-SERVIDOR.online.tableau.com",
        "TABLEAU_SITE": "seu-site",
        "TABLEAU_PAT_NAME": "seu-pat",
        "TABLEAU_PAT_SECRET": "seu-segredo"
      }
    }
  }
}
```

Verifique em **Settings → MCP** que o servidor `tableau` aparece como ativo.

### Kiro

Crie `.kiro/settings/mcp.json` no workspace (ou o equivalente global em
`~/.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "tableau": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/edudutra/mcp-tableau.git",
        "mcp-tableau"
      ],
      "env": {
        "TABLEAU_SERVER_URL": "https://SEU-SERVIDOR.online.tableau.com",
        "TABLEAU_SITE": "seu-site",
        "TABLEAU_PAT_NAME": "seu-pat",
        "TABLEAU_PAT_SECRET": "seu-segredo"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### Windsurf

Edite `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "tableau": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/edudutra/mcp-tableau.git",
        "mcp-tableau"
      ],
      "env": {
        "TABLEAU_SERVER_URL": "https://SEU-SERVIDOR.online.tableau.com",
        "TABLEAU_SITE": "seu-site",
        "TABLEAU_PAT_NAME": "seu-pat",
        "TABLEAU_PAT_SECRET": "seu-segredo"
      }
    }
  }
}
```

### Claude Code (CLI)

Registre o servidor com uma única linha:

```bash
claude mcp add tableau \
  --env TABLEAU_SERVER_URL=https://SEU-SERVIDOR.online.tableau.com \
  --env TABLEAU_SITE=seu-site \
  --env TABLEAU_PAT_NAME=seu-pat \
  --env TABLEAU_PAT_SECRET=seu-segredo \
  -- uvx --from git+https://github.com/edudutra/mcp-tableau.git mcp-tableau
```

### Outros agentes (formato genérico)

Qualquer cliente compatível com MCP aceita a mesma definição stdio:

```json
{
  "command": "uvx",
  "args": ["--from", "git+https://github.com/edudutra/mcp-tableau.git", "mcp-tableau"],
  "env": {
    "TABLEAU_SERVER_URL": "https://SEU-SERVIDOR.online.tableau.com",
    "TABLEAU_PAT_NAME": "seu-pat",
    "TABLEAU_PAT_SECRET": "seu-segredo"
  }
}
```

## Validação rápida

Antes de plugar em um agente, confirme que o comando sobe localmente:

```bash
TABLEAU_SERVER_URL=https://SEU-SERVIDOR.online.tableau.com \
TABLEAU_PAT_NAME=seu-pat \
TABLEAU_PAT_SECRET=seu-segredo \
uvx --from git+https://github.com/edudutra/mcp-tableau.git mcp-tableau
```

O processo fica aguardando mensagens MCP via stdio (sem saída). Encerre com `Ctrl+C`.

## Dicas e solução de problemas

- **Fixar versão**: troque a URL por `git+https://github.com/edudutra/mcp-tableau.git@v0.1.0`
  (tag) ou `@<commit>` para builds reproduzíveis.
- **Atualizar**: o `uvx` cacheia o ambiente; force a recriação com
  `uvx --refresh --from git+https://github.com/edudutra/mcp-tableau.git mcp-tableau`.
- **TLS em rede corporativa**: se a conexão falhar com erro de certificado, aponte
  `TABLEAU_CA_BUNDLE` para o PEM da CA interna.
- **`uvx` não encontrado**: garanta que o diretório de binários do `uv` está no `PATH`
  (reabra o terminal após instalar o `uv`).

## Próximos passos

- Detalhes de capacidades e arquitetura: [`README.md`](README.md).
- Visão geral para agentes e convenções: [`AGENTS.md`](AGENTS.md).
