"""Ponto de entrada: inicia o servidor MCP Tableau em transporte stdio."""

from mcp_tableau.server import run


def main() -> None:
    """Inicia o servidor MCP."""
    run()


if __name__ == "__main__":
    main()
