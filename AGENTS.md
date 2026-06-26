# AGENTS.md - MCP Tableau para publicacao e validacao de dashboards e datasources

## Descricao

Este projeto e um servidor MCP (Model Context Protocol) construido com [FastMCP](https://github.com/jlowin/fastmcp) que expoe ferramentas para automatizar o ciclo de publicacao e validacao de conteudo no Tableau Server / Tableau Cloud.

O objetivo e permitir que agentes de IA interajam com o Tableau de forma programatica para:

- **Publicar dashboards**: enviar workbooks (`.twb`/`.twbx`) para projetos do Tableau.
- **Publicar datasources**: enviar fontes de dados (`.tds`/`.tdsx`) e gerenciar conexoes.
- **Validar dashboards e datasources**: verificar integridade, conexoes, campos e padroes antes da publicacao.
- **Gerenciar conteudo**: consultar, atualizar e organizar projetos, workbooks e datasources existentes.

## Stack

- **Linguagem**: Python (>= 3.13)
- **Framework MCP**: FastMCP (>= 3.4.2)
- **Gerenciador de pacotes**: uv

## Padroes de codigo

Ao escrever, revisar ou refatorar codigo Python deste projeto, siga a skill de padroes de codigo em [.claude/skills/code-standards/SKILL.md](.claude/skills/code-standards/SKILL.md). Ela define convencoes de estilo (ruff), tipagem, estrutura de ferramentas FastMCP, integracao com a Tableau REST API, seguranca de credenciais, tratamento de erros e testes. Consulte-a sempre que for mexer em arquivos `.py` do pacote `mcp_tableau`.

## Padroes de testes

Ao escrever, organizar ou revisar testes, siga a skill de boas praticas de testes em [.claude/skills/testing-standards/SKILL.md](.claude/skills/testing-standards/SKILL.md). Ela define a estrutura com pytest, mocking do cliente Tableau, fixtures, cobertura de ferramentas MCP e validacoes, convencoes de nomeacao e execucao. Consulte-a sempre que for criar ou alterar arquivos em `tests/`.

## Estrutura do projeto

Estrutura recomendada seguindo as melhores praticas para servidores MCP em Python (layout `src/`, separacao por responsabilidade e testes isolados):

```
mcp-tableau/
├── src/
│   └── mcp_tableau/
│       ├── __init__.py          # versao e exports do pacote
│       ├── server.py            # instancia FastMCP e registro das ferramentas
│       ├── config.py            # configuracoes e credenciais via variaveis de ambiente
│       ├── tools/               # ferramentas MCP agrupadas por dominio
│       │   ├── __init__.py
│       │   ├── dashboards.py    # publicar/gerenciar workbooks
│       │   └── datasources.py   # publicar/gerenciar fontes de dados
│       ├── tableau/             # camada de integracao com a Tableau REST API
│       │   ├── __init__.py
│       │   └── client.py        # cliente, autenticacao e sessao
│       ├── validation/          # regras de validacao de conteudo
│       │   ├── __init__.py
│       │   ├── dashboards.py
│       │   └── datasources.py
│       └── models.py            # modelos/schemas (Pydantic) de entrada e saida
├── tests/                       # testes unitarios e de integracao
│   ├── __init__.py
│   └── conftest.py
├── main.py                      # ponto de entrada que inicia o servidor MCP
├── pyproject.toml               # metadados, dependencias e configuracao de ferramentas
├── README.md                    # documentacao do projeto
├── .env.example                 # exemplo das variaveis de ambiente necessarias
└── .gitignore
```

### Boas praticas adotadas

- **Layout `src/`**: isola o codigo do pacote, evitando imports acidentais e garantindo que os testes rodem contra o pacote instalado.
- **Separacao por dominio**: ferramentas (`tools/`), integracao (`tableau/`) e validacao (`validation/`) ficam desacopladas e faceis de testar.
- **`server.py` centraliza o FastMCP**: a instancia do servidor e o registro das ferramentas ficam em um unico lugar; `main.py` apenas inicia.
- **Configuracao via ambiente**: credenciais e URLs do Tableau ficam em `config.py`, lidas de variaveis de ambiente (nunca commitadas), com `.env.example` como referencia.
- **Tipagem e schemas**: use modelos Pydantic em `models.py` para validar entradas/saidas das ferramentas MCP.
- **Testes isolados**: a pasta `tests/` espelha a estrutura de `src/` para cobertura clara.

## Principais dependencias

- **[fastmcp](https://github.com/jlowin/fastmcp)** (>= 3.4.2): framework para construir o servidor MCP e registrar as ferramentas.
- **[tableauserverclient](https://tableau.github.io/server-client-python/)**: cliente oficial da Tableau REST API para autenticacao, publicacao e gerenciamento de conteudo.
- **[pydantic](https://docs.pydantic.dev/)**: validacao e tipagem dos modelos de entrada e saida das ferramentas.
- **[python-dotenv](https://github.com/theskumar/python-dotenv)**: carregamento de variaveis de ambiente a partir de um arquivo `.env` em desenvolvimento.

### Desenvolvimento

- **[pytest](https://docs.pytest.org/)**: execucao de testes unitarios e de integracao.
- **[pytest-cov](https://pytest-cov.readthedocs.io/)**: medicao de cobertura de testes (meta de pelo menos 80%).
- **[ruff](https://docs.astral.sh/ruff/)**: linter e formatador de codigo.
- **[uv](https://docs.astral.sh/uv/)**: gerenciamento de dependencias e ambientes virtuais.

