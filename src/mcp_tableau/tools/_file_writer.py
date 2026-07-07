"""Escrita atômica de bytes em arquivo para a camada de ferramentas MCP.

Módulo interno (prefixo `_`) que concentra a gravação de exports em disco. A
escrita passa por um arquivo temporário no mesmo diretório do destino e é
promovida ao caminho final via `os.replace`, garantindo que o arquivo de saída
seja escrito por completo ou não exista — nunca um arquivo parcial em caso de
falha (crash, disco cheio, permissão negada). Consumido pelas ferramentas
visuais (`visual.py`) ao salvar PNG/PDF renderizados.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> int:
    """Escreve `data` em `path` de forma atômica e retorna os bytes escritos.

    Cria um arquivo temporário no diretório-pai do destino
    (`tempfile.mkstemp(dir=path.parent, suffix=path.suffix)`) — garantindo o
    mesmo sistema de arquivos que o alvo — e o renomeia sobre `path` com
    `os.replace`, cujo rename é atômico dentro do mesmo filesystem. O destino
    fica, portanto, ou com o conteúdo completo novo ou intocado, jamais parcial.

    Em qualquer falha, o arquivo temporário é removido antes de a exceção
    propagar, de modo que nenhum resto é deixado em disco. O parâmetro `data`
    aceita `b""`: um arquivo vazio é escrito e a função retorna `0`.

    Args:
        path: Caminho de destino final do arquivo. O diretório-pai já deve
            existir (validado a montante por `require_output_destination`).
        data: Bytes a serem gravados.

    Returns:
        A quantidade de bytes escritos (`len(data)`).

    Raises:
        OSError: Propaga falhas de escrita/rename (permissão negada, disco
            cheio, etc.) após remover o arquivo temporário.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=path.suffix)
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        # Limpeza defensiva: fecha o descritor caso ainda esteja aberto (a
        # falha pode ter ocorrido antes de `os.close`) e remove o temporário.
        # Ambos os fechamentos/remoções são protegidos para não mascarar a
        # exceção original que será re-levantada pelo `raise`.
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(data)
