"""Integração do protocolo MCP in-memory (suite rápida).

Sobe a instância única do `FastMCP` (via `server.register_tools`) em processo e a
exercita através do `fastmcp.Client` com transporte in-memory — sem rede. As camadas
`tableau/*` são mockadas no nível dos módulos de `tools/`, de modo que o foco aqui é o
contrato do protocolo: descoberta das ferramentas, presença de docstrings, serialização
do envelope de sucesso/erro e dos blocos multimodais (imagem). Erros de registro e de
contrato que passam despercebidos nos testes unitários são pegos por esta camada.

A suíte é síncrona: cada teste embrulha a chamada assíncrona do cliente com
``asyncio.run`` para não exigir um plugin de async no projeto.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
from collections.abc import Awaitable
from unittest.mock import MagicMock

import pytest
from fastmcp import Client
from mcp.types import ImageContent
from PIL import Image as PILImage

import mcp_tableau.server as server
from mcp_tableau.tableau.client import PublishedRef
from mcp_tableau.tools import deploy, metadata, qa, visual

# Conjunto completo de ferramentas que devem estar registradas (RF22): as quatro
# capacidades do produto (deploy, visual, QA estrutural, metadados/linhagem).
_EXPECTED_TOOLS = frozenset(
    {
        "publish_workbook",
        "publish_datasource",
        "render_view_image",
        "render_workbook_pdf",
        "inspect_workbook_structure",
        "audit_workbook_complexity",
        "get_downstream_lineage",
        "get_upstream_lineage",
        "get_datasource_dictionary",
        "search_similar_content",
    }
)


def _await[T](coro: Awaitable[T]) -> T:
    """Executa uma corrotina até o fim numa loop dedicada (testes síncronos)."""
    return asyncio.run(coro)


def _png_bytes(color: str = "white") -> bytes:
    """Gera um PNG 2x2 real para alimentar a heurística de render no caminho feliz."""
    buffer = io.BytesIO()
    PILImage.new("RGB", (2, 2), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def mcp_server() -> server.FastMCP:
    """Registra as ferramentas uma única vez na instância do servidor.

    Escopo de módulo: o registro de ferramentas no FastMCP não é idempotente
    (registrar duas vezes levantaria erro de nome duplicado), por isso é feito
    apenas uma vez para toda a suíte in-memory.
    """
    server.register_tools()
    return server.mcp


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Substitui `load_settings`/`tableau_session` em todos os módulos de tools.

    As ferramentas resolvem a sessão em tempo de chamada a partir dos globais do
    próprio módulo, então o mock é aplicado por teste (independente do registro,
    feito uma única vez). Retorna o `client` mockado para configuração dos cenários.
    """
    client = MagicMock()

    @contextlib.contextmanager
    def fake_session(_settings: object):
        yield client

    for module in (deploy, visual, qa, metadata):
        monkeypatch.setattr(module, "load_settings", lambda: object())
        monkeypatch.setattr(module, "tableau_session", fake_session)
    return client


def test_mcp_todas_ferramentas_registradas_e_descobriveis(
    mcp_server: server.FastMCP,
) -> None:
    async def scenario() -> set[str]:
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
        return {tool.name for tool in tools}

    discovered = _await(scenario())

    assert discovered == set(_EXPECTED_TOOLS)


def test_mcp_docstrings_presentes_em_todas_ferramentas(
    mcp_server: server.FastMCP,
) -> None:
    async def scenario() -> dict[str, str | None]:
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
        return {tool.name: tool.description for tool in tools}

    descriptions = _await(scenario())

    assert set(descriptions) == set(_EXPECTED_TOOLS)
    for name, description in descriptions.items():
        assert description, f"Ferramenta '{name}' sem docstring/descrição."


def test_mcp_publish_workbook_contrato_de_entrada_e_saida_serializa(
    mcp_server: server.FastMCP, fake_client: MagicMock, tmp_path
) -> None:
    workbook = tmp_path / "vendas.twbx"
    workbook.write_bytes(b"fake-twbx")
    fake_client.find_project_id.return_value = "proj-luid"
    fake_client.search_content.return_value = []
    fake_client.publish_workbook.return_value = PublishedRef(
        content_id="wb-1",
        name="vendas",
        content_type="workbook",
        project_id="proj-luid",
        project_name="Financeiro",
        mode="create_new",
        chunked=False,
        webpage_url="https://tableau.example.com/wb-1",
    )

    async def scenario():
        async with Client(mcp_server) as client:
            return await client.call_tool(
                "publish_workbook",
                {"file_path": str(workbook), "project_name": "Financeiro"},
            )

    result = _await(scenario())

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["status"] == "success"
    assert payload["content_id"] == "wb-1"
    assert payload["content_type"] == "workbook"
    assert payload["mode"] == "create_new"
    assert payload["chunked"] is False
    fake_client.publish_workbook.assert_called_once()


def test_mcp_render_view_image_retorna_bloco_imagem_e_json(
    mcp_server: server.FastMCP, fake_client: MagicMock
) -> None:
    fake_client.render_view_image.return_value = _png_bytes("white")

    async def scenario():
        async with Client(mcp_server) as client:
            return await client.call_tool("render_view_image", {"view_id": "view-1"})

    result = _await(scenario())

    assert result.is_error is False
    image_blocks = [b for b in result.content if isinstance(b, ImageContent)]
    assert len(image_blocks) == 1
    assert image_blocks[0].mimeType == "image/png"
    # O JSON estruturado (RenderImageResult) acompanha a imagem como bloco de texto.
    text_blocks = [b for b in result.content if not isinstance(b, ImageContent)]
    assert text_blocks
    assert any("view-1" in getattr(b, "text", "") for b in text_blocks)


def test_mcp_ferramenta_em_erro_retorna_toolerror_serializado(
    mcp_server: server.FastMCP,
) -> None:
    async def scenario():
        async with Client(mcp_server) as client:
            return await client.call_tool(
                "publish_workbook",
                {"file_path": "/caminho/arquivo.txt", "project_name": "Financeiro"},
            )

    result = _await(scenario())

    # ToolError é retornado (não levantado): a chamada conclui com sucesso de protocolo,
    # mas o envelope carrega status="error" e um código acionável.
    assert result.is_error is False
    envelope = result.structured_content["result"]
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "INVALID_FILE"
    assert envelope["error"]["message"]


def test_run_registra_ferramentas_e_inicia_stdio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`run` deve registrar as ferramentas e subir o transporte stdio.

    `register_tools`/`mcp.run` são substituídos por mocks para não registrar em
    duplicidade nem bloquear o processo de teste num servidor real.
    """
    register = MagicMock()
    runner = MagicMock()
    monkeypatch.setattr(server, "register_tools", register)
    monkeypatch.setattr(server.mcp, "run", runner)

    server.run()

    register.assert_called_once_with()
    runner.assert_called_once_with(transport="stdio")
