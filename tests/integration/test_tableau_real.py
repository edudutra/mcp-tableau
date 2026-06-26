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
from mcp_tableau.models import PublishResult, RenderImageResult
from mcp_tableau.tableau.client import tableau_session
from mcp_tableau.tools import deploy, metadata, visual

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
    """Consulta a linhagem descendente de uma fonte de dados real via Metadata API."""
    datasource_id = _required_env("TABLEAU_IT_DATASOURCE_ID")

    result = metadata.get_downstream_lineage(datasource_id)
    # Sucesso com dependências (possivelmente vazias) ou degradação acionável (RF24).
    status = getattr(result, "status", None)
    assert status in {"success", "error"}
