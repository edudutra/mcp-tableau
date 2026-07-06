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
from mcp_tableau.hyper.engine import TableReport
from mcp_tableau.models import (
    ContentRef,
    ErrorCode,
    FilterInfo,
    HyperColumn,
    LineageNode,
    SheetRef,
    SimilarityMatch,
    StructureReport,
)
from mcp_tableau.tableau.client import PublishedRef, TableauClientError
from mcp_tableau.tools import deploy, hyper, metadata, qa, visual

# Ferramentas das quatro capacidades base (deploy, visual, QA, metadados/linhagem).
_BASE_TOOLS = frozenset(
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

# Ferramentas da Capacidade 5 (Hyper Datasources).
_HYPER_TOOLS = frozenset(
    {
        "inspect_hyper_schema",
        "query_hyper",
        "create_hyper_from_file",
        "create_hyper_from_inline",
        "extract_database_to_hyper",
        "append_to_hyper",
        "execute_hyper_sql",
    }
)

# Conjunto completo esperado no servidor (RF22): 10 base + 7 Hyper = 17 tools.
_EXPECTED_TOOLS = _BASE_TOOLS | _HYPER_TOOLS


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


# -- Contrato SheetRef / worksheet_id serializado (Tarefa 5.0) -----------------


def _structure_report_fixture() -> StructureReport:
    """Relatório com uma worksheet renderizável, uma oculta e um dashboard."""
    return StructureReport(
        workbook_id="wb-it",
        worksheets=[SheetRef(name="Vendas por Região"), SheetRef(name="Oculta")],
        dashboards=[SheetRef(name="Painel Executivo")],
        filters=[
            FilterInfo(
                worksheet="Vendas por Região",
                field="Região",
                kind="categorical",
                has_logic=True,
            )
        ],
    )


def test_inspect_workbook_structure_contrato_serializa_sheetref(
    mcp_server: server.FastMCP,
    fake_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client.download_workbook.return_value = "/tmp/ignored.twbx"
    fake_client.list_workbook_view_luids.return_value = {
        "Vendas por Região": "luid-vendas",
        "Painel Executivo": "luid-painel",
    }
    monkeypatch.setattr(
        qa, "inspect_structure", lambda *a, **k: _structure_report_fixture()
    )

    async def scenario():
        async with Client(mcp_server) as client:
            return await client.call_tool(
                "inspect_workbook_structure", {"workbook_id": "wb-it"}
            )

    result = _await(scenario())

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["status"] == "success"
    # worksheets[].id / worksheets[].name presentes e tipados.
    ws = {w["name"]: w["id"] for w in payload["worksheets"]}
    assert ws["Vendas por Região"] == "luid-vendas"
    assert ws["Oculta"] is None
    assert payload["dashboards"][0]["id"] == "luid-painel"
    # filters[].worksheet_id presente e casado por nome.
    assert payload["filters"][0]["worksheet_id"] == "luid-vendas"


def test_inspect_workbook_structure_degradado_serializa_id_null(
    mcp_server: server.FastMCP,
    fake_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client.download_workbook.return_value = "/tmp/ignored.twbx"
    fake_client.list_workbook_view_luids.side_effect = TableauClientError(
        ErrorCode.UPSTREAM_ERROR, "Falha ao comunicar com o Tableau."
    )
    monkeypatch.setattr(
        qa, "inspect_structure", lambda *a, **k: _structure_report_fixture()
    )

    async def scenario():
        async with Client(mcp_server) as client:
            return await client.call_tool(
                "inspect_workbook_structure", {"workbook_id": "wb-it"}
            )

    result = _await(scenario())

    assert result.is_error is False
    payload = result.structured_content["result"]
    # Degradação: status success, campo id presente e null (não omitido).
    assert payload["status"] == "success"
    for ws in payload["worksheets"]:
        assert "id" in ws
        assert ws["id"] is None
    assert payload["dashboards"][0]["id"] is None
    assert "worksheet_id" in payload["filters"][0]
    assert payload["filters"][0]["worksheet_id"] is None


def test_render_aceita_id_do_structure_report(
    mcp_server: server.FastMCP,
    fake_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1) Inspeção produz um SheetRef.id (LUID) por correspondência de nome.
    fake_client.download_workbook.return_value = "/tmp/ignored.twbx"
    fake_client.list_workbook_view_luids.return_value = {
        "Vendas por Região": "luid-vendas",
        "Painel Executivo": "luid-painel",
    }
    monkeypatch.setattr(
        qa, "inspect_structure", lambda *a, **k: _structure_report_fixture()
    )
    fake_client.render_view_image.return_value = _png_bytes("white")

    async def scenario():
        async with Client(mcp_server) as client:
            inspected = await client.call_tool(
                "inspect_workbook_structure", {"workbook_id": "wb-it"}
            )
            view_id = inspected.structured_content["result"]["worksheets"][0]["id"]
            # 2) O id é aceito sem transformação pela ferramenta de render.
            rendered = await client.call_tool("render_view_image", {"view_id": view_id})
            return view_id, rendered

    view_id, rendered = _await(scenario())

    assert view_id == "luid-vendas"
    assert rendered.is_error is False
    # O mesmo id chegou ao cliente de render, sem transformação.
    assert fake_client.render_view_image.call_args.args[0] == "luid-vendas"


# -- RF11: consistência do formato de `id` em similaridade/linhagem ------------


def test_rf11_id_consistente_em_similaridade_e_linhagem() -> None:
    """`SimilarityMatch`/`LineageNode`/`ContentRef` expõem `id: str` obrigatório.

    Garante que o `id` retornado por busca de similaridade e linhagem tem o mesmo
    formato (string LUID) consumido por inspeção/render — não há divergência.
    """
    for model in (SimilarityMatch, LineageNode, ContentRef):
        field = model.model_fields.get("id")
        assert field is not None, f"{model.__name__} deve expor 'id'"
        assert field.annotation is str, f"{model.__name__}.id deve ser str"

    match = SimilarityMatch(id="luid-x", name="X", type="workbook", score=0.9)
    node = LineageNode(id="luid-y", name="Y", type="datasource")
    ref = ContentRef(id="luid-z", name="Z", type="workbook")
    assert match.model_dump()["id"] == "luid-x"
    assert node.model_dump()["id"] == "luid-y"
    assert ref.model_dump()["id"] == "luid-z"


# -- Capacidade 5: Hyper Datasources via transporte MCP (Tarefa 7.0) -----------


@pytest.fixture
def hyper_engine(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Substitui `hyper_session`/`load_settings` no módulo `hyper` das tools.

    As tools de Hyper resolvem o motor e as configurações em tempo de chamada a
    partir dos globais do próprio módulo; o mock é aplicado por teste, sem tocar
    o runtime Hyper real. Retorna o `engine` mockado para configurar cenários.
    """
    engine = MagicMock(name="HyperEngine")

    @contextlib.contextmanager
    def fake_session():
        yield engine

    settings = MagicMock(name="Settings")
    settings.hyper_max_result_rows = 1_000
    settings.hyper_max_source_file_mb = 500
    settings.hyper_max_inline_rows = 1_000
    settings.hyper_max_extract_rows = 5_000_000

    monkeypatch.setattr(hyper, "hyper_session", fake_session)
    monkeypatch.setattr(hyper, "load_settings", lambda: settings)
    return engine


def test_servidor_expoe_dezessete_tools(mcp_server: server.FastMCP) -> None:
    async def scenario() -> set[str]:
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
        return {tool.name for tool in tools}

    discovered = _await(scenario())

    assert len(discovered) == 17
    assert discovered == set(_EXPECTED_TOOLS)
    # As sete tools de Hyper Datasources estão entre as descobertas.
    assert _HYPER_TOOLS <= discovered


def test_tools_hyper_declaram_schemas_de_entrada_validos(
    mcp_server: server.FastMCP,
) -> None:
    async def scenario() -> dict[str, dict]:
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
        return {
            tool.name: tool.inputSchema for tool in tools if tool.name in _HYPER_TOOLS
        }

    schemas = _await(scenario())

    assert set(schemas) == set(_HYPER_TOOLS)
    for name, schema in schemas.items():
        assert schema.get("type") == "object", f"{name} sem schema de objeto"
        assert schema.get("properties"), f"{name} sem propriedades de entrada"
    # Amostra: o parâmetro obrigatório de inspeção está declarado.
    assert "hyper_path" in schemas["inspect_hyper_schema"]["properties"]


def test_chamada_create_hyper_from_inline_via_cliente_mcp_serializa_resultado(
    mcp_server: server.FastMCP, hyper_engine: MagicMock, tmp_path
) -> None:
    hyper_path = tmp_path / "referencia.hyper"
    hyper_engine.create_table_from_rows.return_value = TableReport(
        schema_name="Extract",
        table_name="Extract",
        columns=[
            HyperColumn(name="codigo", type="big_int", nullable=False),
            HyperColumn(name="nome", type="text", nullable=True),
        ],
        row_count=1,
    )

    async def scenario():
        async with Client(mcp_server) as client:
            return await client.call_tool(
                "create_hyper_from_inline",
                {
                    "hyper_path": str(hyper_path),
                    "table_name": "Extract",
                    "columns": [
                        {"name": "codigo", "type": "big_int", "nullable": False},
                        {"name": "nome", "type": "text", "nullable": True},
                    ],
                    "rows": [[101, "Campinas"]],
                },
            )

    result = _await(scenario())

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["status"] == "success"
    assert payload["source"] == "inline"
    assert payload["table_name"] == "Extract"
    assert payload["row_count"] == 1
    assert [c["name"] for c in payload["columns"]] == ["codigo", "nome"]


def test_chamada_query_hyper_com_arquivo_inexistente_serializa_tool_error(
    mcp_server: server.FastMCP, hyper_engine: MagicMock, tmp_path
) -> None:
    ausente = tmp_path / "nao_existe.hyper"  # não criado

    async def scenario():
        async with Client(mcp_server) as client:
            return await client.call_tool(
                "query_hyper",
                {"hyper_path": str(ausente), "query": "SELECT 1"},
            )

    result = _await(scenario())

    # ToolError é retornado (não levantado): sucesso de protocolo com envelope de erro.
    assert result.is_error is False
    envelope = result.structured_content["result"]
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "HYPER_INVALID_FILE"
    assert envelope["error"]["message"]
    # Validação local barata: o motor Hyper nunca foi acionado.
    hyper_engine.query.assert_not_called()


def test_volume_alert_serializado_via_transporte_mcp_mantem_status_volume_alert(
    mcp_server: server.FastMCP, hyper_engine: MagicMock, tmp_path
) -> None:
    hyper_path = tmp_path / "grande.hyper"
    # Limiar baixo + confirmação ausente → VolumeAlert (pré-execução, não bloqueia).
    hyper_engine_settings = hyper.load_settings()
    hyper_engine_settings.hyper_max_inline_rows = 1

    async def scenario():
        async with Client(mcp_server) as client:
            return await client.call_tool(
                "create_hyper_from_inline",
                {
                    "hyper_path": str(hyper_path),
                    "table_name": "Extract",
                    "columns": [{"name": "codigo", "type": "big_int"}],
                    "rows": [[1], [2], [3]],
                },
            )

    result = _await(scenario())

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["status"] == "volume_alert"
    assert payload["exceeded"]
    assert payload["exceeded"][0]["dimension"] == "inline_rows"
    assert payload["how_to_proceed"]
    # A operação NÃO foi executada: o motor não gravou nada.
    hyper_engine.create_table_from_rows.assert_not_called()


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
