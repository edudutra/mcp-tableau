---
name: testing-standards
description: Use when escrevendo, organizando ou revisando testes deste projeto MCP Tableau - define estrutura com pytest, mocking do cliente Tableau, fixtures, cobertura de ferramentas MCP e validacoes, e convencoes de nomeacao
---

# Testing Standards - MCP Tableau

## Overview

Boas práticas de testes para o servidor MCP Tableau (Python >= 3.13, pytest). O objetivo é garantir que ferramentas MCP, integração com o Tableau e regras de validação sejam testadas de forma rápida, isolada e determinística — sem depender de um Tableau Server real.

## Quando usar

- Adicionando uma nova ferramenta MCP (`tools/`) — ela precisa de teste.
- Corrigindo um bug — escreva primeiro o teste que reproduz a falha.
- Escrevendo/alterando regras de validação (`validation/`).
- Mexendo na camada de integração (`tableau/`).
- Revisando um PR para garantir cobertura adequada.

## Camadas de teste (piramide)

Diferencie as camadas e respeite o peso de cada uma — a maior parte do esforco fica na base.

### Unitarios (maioria)
- Testam uma funcao/classe isolada, com dependencias **mockadas**.
- Alvos principais: `validation/` (funcoes puras), `tools/` (orquestracao e validacao de entrada com o cliente Tableau mockado), `models.py` (Pydantic).
- Rapidos, deterministicos, sem rede. Sao a base da suite e rodam sempre.

### Integracao (quantidade moderada)
- **Integracao do protocolo MCP (in-memory)**: suba o servidor FastMCP em processo e chame as ferramentas via cliente de teste, sem rede. Verifica registro, contrato e serializacao das ferramentas — pega erros que o teste unitario nao ve. Faz parte da suite rapida padrao.
- **Integracao com o Tableau real (opcional)**: exercita `tableau/client.py` contra um Tableau Server/sandbox de verdade. E valioso, porem lento e dependente de ambiente/credenciais. Marque com `@pytest.mark.integration` e **mantenha fora da suite rapida** (rode sob demanda ou em CI dedicado).

### E2E (poucos ou nenhum)
- Fluxo completo agente → servidor MCP → Tableau real. Util conceitualmente, mas fragil e caro.
- Para este projeto, **evite automacao extensa**: prefira poucos smoke tests manuais ou em pipeline separado. Nao tente cobrir regras de negocio por aqui — isso e papel dos unitarios.

### Resumo de prioridade
1. Base ampla de **unitarios** (sempre mockando rede/Tableau).
2. **Integracao MCP in-memory** rapida, na suite padrao.
3. **Integracao com Tableau real** marcada e opcional.
4. **E2E** apenas como excecao (smoke).

## Estrutura

- `tests/` espelha `src/mcp_tableau/`:
  - `tests/tools/test_dashboards.py`, `tests/tools/test_datasources.py`
  - `tests/tableau/test_client.py`
  - `tests/validation/test_dashboards.py`, `tests/validation/test_datasources.py`
- `tests/conftest.py` concentra fixtures compartilhadas (cliente fake, modelos de exemplo, dados de configuração).
- Um arquivo de teste por módulo testado; um teste por comportamento.

## Convencoes de nomeacao

- Arquivos: `test_<modulo>.py`.
- Funções: `test_<unidade>_<cenario>_<resultado_esperado>` — ex.: `test_publish_dashboard_arquivo_invalido_levanta_erro`.
- Classes (opcional, para agrupar): `Test<Unidade>`.
- Nomes descritivos em vez de `test_1`, `test_ok`.

## Isolamento e mocking

- **Nunca** acesse um Tableau Server real em testes unitários. Faça **mock** do `tableauserverclient` e da camada `tableau/client.py`.
- Use `pytest` + `unittest.mock` (`MagicMock`, `patch`) ou `pytest-mock` (`mocker`).
- Faça mock no limite da integração (o cliente), não da lógica que você está testando.
- Testes não devem depender de rede, relógio, ordem de execução ou estado global.
- Para variáveis de ambiente/config, use `monkeypatch.setenv` em vez de alterar o ambiente real.

## Fixtures

- Centralize em `conftest.py`: cliente Tableau fake, workbook/datasource de exemplo, configuração válida.
- Prefira fixtures pequenas e componíveis a uma fixture "gigante".
- Use `tmp_path` para arquivos temporários (`.twbx`, `.tdsx` de exemplo); não escreva fora do diretório de teste.
- Escopo adequado: `function` por padrão; `session` apenas para recursos caros e imutáveis.

## O que testar

### Ferramentas MCP (`tools/`)
- Caminho feliz: entrada válida → chamada esperada ao cliente + saída Pydantic correta.
- Validação de entrada: extensões/paths inválidos são rejeitados antes de chamar o Tableau.
- Propagação de erro: falha do cliente vira erro de ferramenta claro (sem vazar segredos).

### Integração (`tableau/`)
- Autenticação faz sign-in e garante sign-out (inclusive em erro).
- Paginação e limites tratados corretamente ao listar conteúdo.

### Validação (`validation/`)
- Funções de validação são puras: mesma entrada → mesmo resultado estruturado.
- Cobrir casos válidos, inválidos e de borda; checar severidade e lista de problemas.

## Asserts e qualidade

- Asserts específicos: verifique valores e chamadas (`mock.assert_called_once_with(...)`), não apenas "não deu erro".
- Use `pytest.raises(ExcecaoEspecifica)` para erros esperados; evite capturar `Exception` genérica.
- Use `pytest.mark.parametrize` para variações do mesmo comportamento em vez de duplicar testes.
- Um teste deve falhar por um único motivo. Evite múltiplos comportamentos por teste.

## Cobertura

- **Meta: pelo menos 80% de cobertura** de linhas no pacote `mcp_tableau`. Trate como objetivo a perseguir, não como número a inflar com testes vazios.
- Priorize cobrir lógica de ferramentas, integração e validação; foque em comportamento, não apenas em "linhas executadas".
- Use `pytest-cov`: `uv run pytest --cov=mcp_tableau --cov-report=term-missing`.
- Para falhar abaixo da meta: `uv run pytest --cov=mcp_tableau --cov-fail-under=80`.
- Use `--cov-report=term-missing` para identificar linhas/ramos não cobertos e priorizar testes relevantes.

## Execucao

- Rodar a suite rapida (unitarios + integracao MCP in-memory): `uv run pytest`.
- Rápido com saída curta: `uv run pytest -q`.
- Com cobertura: `uv run pytest --cov=mcp_tableau --cov-report=term-missing`.
- Um arquivo/teste: `uv run pytest tests/tools/test_dashboards.py::test_nome`.
- Excluir integracao real no dia a dia: `uv run pytest -m "not integration"`.
- Rodar apenas integracao com Tableau real (sob demanda): `uv run pytest -m integration`.
- Testes da suite rapida devem ser rápidos (sem `sleep`, sem I/O de rede). Marque integração real lenta com `@pytest.mark.integration`.

## Checklist antes de concluir

- [ ] Toda ferramenta/validação nova tem teste.
- [ ] Bug corrigido tem teste que reproduz a falha (RED antes do fix).
- [ ] Cliente Tableau / rede mockados — sem dependência de servidor real.
- [ ] Casos de erro e de borda cobertos, não só o caminho feliz.
- [ ] Nomes de teste descritivos e asserts específicos.
- [ ] `uv run pytest` passando.
- [ ] Cobertura de pelo menos 80% (`--cov=mcp_tableau --cov-fail-under=80`).
