---
name: code-standards
description: Use when escrevendo, revisando ou refatorando codigo Python deste projeto MCP Tableau - define convencoes de estilo, tipagem, estrutura de ferramentas FastMCP, integracao com a Tableau REST API, tratamento de erros, seguranca de credenciais e testes
---

# Code Standards - MCP Tableau

## Overview

Padroes de codigo para o servidor MCP Tableau (Python >= 3.13, FastMCP, tableauserverclient). O objetivo e manter o codigo consistente, tipado, seguro e testavel. Aplique estes padroes ao criar ou alterar qualquer arquivo `.py` do pacote `mcp_tableau`.

## Quando usar

- Adicionando ou alterando uma ferramenta MCP (`tools/`).
- Mexendo na integracao com o Tableau (`tableau/`).
- Escrevendo regras de validacao (`validation/`).
- Definindo modelos de entrada/saida (`models.py`).
- Revisando um PR ou refatorando codigo existente.

## Estilo e formatacao

- Use **ruff** como linter e formatador (`ruff check` e `ruff format`). Não introduza estilos manuais que conflitem com ele.
- Linha de até 88 caracteres.
- Imports ordenados: stdlib, terceiros, locais — deixe o ruff/isort organizar.
- Use aspas duplas para strings.
- Prefira f-strings a `.format()` ou concatenação.
- Nomes: `snake_case` para funcoes/variaveis, `PascalCase` para classes, `UPPER_SNAKE` para constantes.

## Tipagem

- **Type hints obrigatórios** em toda função pública (parametros e retorno).
- Use os tipos nativos modernos: `list[str]`, `dict[str, int]`, `str | None` (não `Optional`/`List` do `typing`).
- Modelos de dados sempre via **Pydantic** (`models.py`), nunca dicts soltos como contrato de ferramenta.
- Evite `Any`; quando inevitavel, isole e comente o motivo.

## Ferramentas MCP (FastMCP)

- Cada ferramenta é uma função registrada com `@mcp.tool` em `tools/`, agrupada por domínio (dashboards, datasources).
- A **docstring é o contrato exposto ao agente**: descreva claramente o que faz, parametros e o que retorna. Escreva-a pensando em quem chama a ferramenta.
- Entrada e saída tipadas com modelos Pydantic — não retorne strings ad-hoc para dados estruturados.
- Mantenha ferramentas **finas**: orquestram, mas delegam regras de negócio para `tableau/` e `validation/`.
- Uma ferramenta = uma responsabilidade. Não combine publicar e validar na mesma função.
- Operações idempotentes quando possível; deixe claro na docstring quando houver efeito colateral (publicação, sobrescrita).

## Integracao com a Tableau REST API

- Todo acesso ao Tableau passa pela camada `tableau/client.py`. Ferramentas **não** instanciam `tableauserverclient` diretamente.
- Use `tableauserverclient` (cliente oficial) em vez de chamadas HTTP manuais.
- Gerencie autenticação/sessão de forma centralizada (context manager / sign-in e sign-out garantidos).
- Trate paginação e limites da API explicitamente ao listar conteúdo.

## Configuracao e seguranca

- **Nunca** hardcode credenciais, tokens, URLs de servidor ou nomes de site. Leia tudo de variáveis de ambiente via `config.py`.
- Atualize o `.env.example` ao introduzir uma nova variável de ambiente.
- Não logue segredos (tokens, senhas, PATs). Redija valores sensíveis antes de logar.
- Prefira **Personal Access Tokens (PAT)** a usuário/senha para autenticação.
- Valide caminhos de arquivos (`.twb/.twbx/.tds/.tdsx`) antes de publicar; rejeite extensões inesperadas.

## Tratamento de erros

- Capture exceções específicas do `tableauserverclient` (ex.: erros de autenticação, item não encontrado) em vez de `except Exception` genérico.
- Falhe com mensagens acionáveis: diga o que falhou e como corrigir, sem vazar detalhes sensíveis.
- Não silencie erros (`except: pass`). Propague ou converta em um erro de ferramenta claro para o agente.
- Valide a entrada nos limites (na ferramenta) antes de chamar o Tableau.

## Validacao de conteudo

- Regras de validação ficam em `validation/`, separadas das ferramentas e da integração.
- Retorne resultados de validação estruturados (Pydantic): status, lista de problemas, severidade.
- Validações devem ser puras e testáveis sem rede sempre que possível.

## Testes

- Use **pytest**. Estrutura de `tests/` espelha `src/mcp_tableau/`.
- Toda ferramenta nova precisa de teste. Toda correção de bug começa com um teste que reproduz a falha.
- **Mock** o cliente Tableau / chamadas de rede em testes unitários; não dependa de um servidor real.
- Nomeie testes descritivamente: `test_<unidade>_<cenario>_<resultado_esperado>`.
- Use `conftest.py` para fixtures compartilhadas (cliente fake, modelos de exemplo).

## Documentacao

- Docstrings em funções públicas e ferramentas MCP.
- Comente o **porquê**, não o **o quê**. Não comente código óbvio.
- Mantenha o `README.md` e o `AGENTS.md` atualizados ao mudar estrutura ou dependências.

## Checklist antes de concluir

- [ ] `ruff check` e `ruff format` sem erros.
- [ ] Type hints completos.
- [ ] Sem credenciais/segredos no código ou nos logs.
- [ ] Modelos Pydantic para entrada/saída.
- [ ] Testes adicionados/atualizados e passando.
- [ ] `.env.example` atualizado se houver nova variável.
- [ ] Docstrings das ferramentas claras para o agente.
