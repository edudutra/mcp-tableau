"""Integração com um Tableau Server/Cloud real (fora da suite rápida).

Estes testes exercitam a camada `tableau/*` contra um Tableau de verdade: publicação +
download roundtrip, render PNG e linhagem via Metadata API. São **lentos** e dependem de
credenciais e de conteúdo de sandbox, por isso:

- Estão marcados com ``@pytest.mark.integration`` e ficam **fora** da suite rápida
  (``addopts`` exclui ``integration`` por padrão; rode com ``pytest -m integration``).
- Pulam automaticamente quando ``TABLEAU_INTEGRATION`` não está habilitado, evitando
  falhas em ambientes sem sandbox.

A configuração real é lida do ambiente via `load_settings`; as variáveis de sandbox que
parametrizam cada cenário (projeto de destino, ids de view/datasource/workbook) também
vêm do ambiente. Cobrem a degradação esperada para ``null``/``UPSTREAM_ERROR`` (RF24)
quando aplicável.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from mcp_tableau.config import load_settings
from mcp_tableau.models import (
    ErrorCode,
    PublishResult,
    RenderImageResult,
    StructureReport,
)
from mcp_tableau.tableau.client import tableau_session
from mcp_tableau.tools import deploy, metadata, qa, visual

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TABLEAU_INTEGRATION") != "1",
        reason="Defina TABLEAU_INTEGRATION=1 e as credenciais de sandbox para rodar.",
    ),
]


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"Variável de sandbox '{name}' ausente.")
    return value


def test_integration_publish_e_download_roundtrip() -> None:
    """Publica um workbook de sandbox e o baixa de volta, validando o roundtrip."""
    file_path = _required_env("TABLEAU_IT_WORKBOOK_PATH")
    project_name = _required_env("TABLEAU_IT_PROJECT")

    published = deploy.publish_workbook(file_path, project_name, overwrite=True)
    assert isinstance(published, PublishResult)
    assert published.status == "success"
    assert published.content_type == "workbook"

    with (
        tableau_session(load_settings()) as client,
        tempfile.TemporaryDirectory() as tmp,
    ):
        downloaded = client.download_workbook(published.content_id, Path(tmp))
        assert downloaded.exists()
        assert downloaded.stat().st_size > 0


def test_integration_render_view_image_retorna_png_valido() -> None:
    """Renderiza uma view real e confere que o bloco PNG tem assinatura válida."""
    view_id = _required_env("TABLEAU_IT_VIEW_ID")

    result = visual.render_view_image(view_id)
    assert isinstance(result, tuple)
    payload, image = result
    assert isinstance(payload, RenderImageResult)
    # Assinatura do cabeçalho PNG.
    assert bytes(image.data).startswith(b"\x89PNG\r\n\x1a\n")


def test_integration_metadata_lineage_responde() -> None:
    """Consulta a linhagem descendente de uma fonte de dados real via Metadata API.

    Regressão BUG-03: a asserção anterior (`status in {"success", "error"}`) passava
    mesmo quando a linhagem falhava — mascarando LUIDs de sandbox desatualizados que
    retornavam ``NOT_FOUND``. Para um LUID sabidamente indexado exigimos
    ``status == "success"`` com ``direction`` correto e ``root`` resolvido.
    """
    datasource_id = _required_env("TABLEAU_IT_DATASOURCE_ID")

    result = metadata.get_downstream_lineage(datasource_id)
    status = getattr(result, "status", None)

    # RF24: em Cloud/Server sem Metadata API a degradação é tolerada, mas APENAS como
    # UPSTREAM_ERROR explícito. NOT_FOUND aqui indicaria o defeito original
    # (dado de teste desatualizado), então não é aceito.
    if status == "error":
        assert result.error.code is ErrorCode.UPSTREAM_ERROR, (
            f"Linhagem falhou com {result.error.code}; verifique se "
            "TABLEAU_IT_DATASOURCE_ID existe na Metadata API (BUG-03)."
        )
        return

    assert status == "success"
    assert result.direction == "downstream"
    assert result.root.id, "root da linhagem não foi resolvido"


def test_real_inspect_structure_retorna_luids_validos() -> None:
    """Inspeciona um workbook real: views publicadas têm `id` renderizável.

    Worksheets visíveis (views publicadas) devem vir com `id` não nulo e aceito
    por `render_view_image`; sheets ocultas/não publicadas vêm com `id=None`
    (degradação esperada por design, não erro).
    """
    workbook_id = _required_env("TABLEAU_IT_WORKBOOK_ID")

    result = qa.inspect_workbook_structure(workbook_id)
    assert isinstance(result, StructureReport), getattr(result, "error", result)
    assert result.status == "success"

    renderizaveis = [w for w in result.worksheets if w.id is not None]
    assert renderizaveis, "esperava ao menos uma worksheet com LUID renderizável"

    # O LUID de uma worksheet visível é aceito pela ferramenta de render real.
    rendered = visual.render_view_image(renderizaveis[0].id)
    assert isinstance(rendered, tuple)
    _payload, image = rendered
    assert bytes(image.data).startswith(b"\x89PNG\r\n\x1a\n")
