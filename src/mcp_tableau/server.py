"""Bootstrap do servidor FastMCP (transporte stdio) e registro de ferramentas.

Este é o único ponto de instanciação do `FastMCP` e de registro das ferramentas.
O registro efetivo das tools é incremental: cada módulo em ``tools/`` expõe uma
função ``register(mcp)`` que é chamada por `register_tools` conforme as
capacidades vão sendo implementadas (Tarefas 5.0–8.0).
"""

from fastmcp import FastMCP

mcp: FastMCP = FastMCP(name="mcp-tableau")


def register_tools() -> None:
    """Registra todas as ferramentas MCP na instância única do servidor.

    Ponto único de registro. À medida que as capacidades são implementadas,
    cada módulo de ``tools/`` é importado aqui e tem suas ferramentas
    registradas em `mcp`.
    """
    # As ferramentas das Capacidades 1–4 são registradas nas tarefas seguintes.
    return


def run() -> None:
    """Inicia o servidor MCP em transporte stdio."""
    register_tools()
    mcp.run(transport="stdio")
