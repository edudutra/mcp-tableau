"""Bootstrap do servidor FastMCP (transporte stdio) e registro de ferramentas.

Este é o único ponto de instanciação do `FastMCP` e de registro das ferramentas.
O registro efetivo das tools é incremental: cada módulo em ``tools/`` expõe uma
função ``register(mcp)`` que é chamada por `register_tools` conforme as
capacidades vão sendo implementadas (Tarefas 5.0–8.0).
"""

from fastmcp import FastMCP

from mcp_tableau.tools import deploy, hyper, metadata, qa, visual

mcp: FastMCP = FastMCP(name="mcp-tableau")


def register_tools() -> None:
    """Registra todas as ferramentas MCP na instância única do servidor.

    Ponto único de registro. Cada módulo de ``tools/`` expõe ``register(mcp)``
    e é acoplado aqui, cobrindo as cinco capacidades do produto: deploy
    (Capacidade 1), visual (Capacidade 2), QA estrutural (Capacidade 3),
    metadados/linhagem (Capacidade 4) e Hyper Datasources (Capacidade 5).
    """
    deploy.register(mcp)
    visual.register(mcp)
    qa.register(mcp)
    metadata.register(mcp)
    hyper.register(mcp)


def run() -> None:
    """Inicia o servidor MCP em transporte stdio."""
    register_tools()
    mcp.run(transport="stdio")
