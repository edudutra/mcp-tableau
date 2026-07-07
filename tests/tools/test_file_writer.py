"""Testes unitários do escritor atômico de bytes.

`atomic_write_bytes` (tools/_file_writer.py) grava um arquivo temporário no
diretório-pai do destino e o promove via `os.replace`. Os testes usam `tmp_path`
para exercitar escritas reais em disco e `monkeypatch` sobre `os.write`/
`os.replace` para simular falhas, verificando que nenhum arquivo temporário
sobra e que a exceção propaga.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_tableau.tools._file_writer import atomic_write_bytes


def test_atomic_write_bytes_escreve_conteudo_e_retorna_contagem(
    tmp_path: Path,
) -> None:
    path = tmp_path / "export.png"
    data = b"\x89PNG\r\n\x1a\n conteudo binario"

    written = atomic_write_bytes(path, data)

    assert written == len(data)
    assert path.read_bytes() == data


def test_atomic_write_bytes_sobrescreve_arquivo_existente_atomicamente(
    tmp_path: Path,
) -> None:
    path = tmp_path / "export.pdf"
    path.write_bytes(b"conteudo antigo bem maior que o novo")

    novo = b"novo"
    written = atomic_write_bytes(path, novo)

    assert written == len(novo)
    assert path.read_bytes() == novo


def test_atomic_write_bytes_conteudo_completo_nao_parcial(tmp_path: Path) -> None:
    path = tmp_path / "grande.bin"
    data = bytes(range(256)) * 4096  # 1 MiB, checa gravação completa

    atomic_write_bytes(path, data)

    assert path.read_bytes() == data
    assert path.stat().st_size == len(data)


def test_atomic_write_bytes_retorna_contagem_igual_len_data(
    tmp_path: Path,
) -> None:
    for tamanho in (1, 10, 1024, 65536):
        path = tmp_path / f"size_{tamanho}.bin"
        data = b"x" * tamanho
        assert atomic_write_bytes(path, data) == tamanho


def test_atomic_write_bytes_bytes_vazios_cria_arquivo_vazio(tmp_path: Path) -> None:
    path = tmp_path / "vazio.png"

    written = atomic_write_bytes(path, b"")

    assert written == 0
    assert path.exists()
    assert path.read_bytes() == b""


def test_atomic_write_bytes_limpa_temp_em_falha_de_escrita(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "export.png"

    def falha_write(*args: object, **kwargs: object) -> int:
        raise OSError("simulação: falha de escrita")

    monkeypatch.setattr(os, "write", falha_write)

    with pytest.raises(OSError):
        atomic_write_bytes(path, b"dados")

    assert not path.exists()
    # Nenhum arquivo temporário deixado no diretório-pai.
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_bytes_limpa_temp_em_falha_de_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "export.png"

    def falha_replace(*args: object, **kwargs: object) -> None:
        raise OSError("simulação: falha de replace")

    monkeypatch.setattr(os, "replace", falha_replace)

    with pytest.raises(OSError):
        atomic_write_bytes(path, b"dados")

    assert not path.exists()
    # O temporário foi gravado e fechado, mas o rename falhou: deve ser removido.
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_bytes_falha_de_limpeza_nao_mascara_erro_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "export.png"

    def falha_replace(*args: object, **kwargs: object) -> None:
        raise OSError("erro original de replace")

    def falha_unlink(*args: object, **kwargs: object) -> None:
        raise OSError("erro secundario de unlink")

    monkeypatch.setattr(os, "replace", falha_replace)
    monkeypatch.setattr(os, "unlink", falha_unlink)

    with pytest.raises(OSError, match="erro original de replace"):
        atomic_write_bytes(path, b"dados")
