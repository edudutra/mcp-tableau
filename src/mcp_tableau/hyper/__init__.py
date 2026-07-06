"""Pacote de integração com o motor Hyper (`tableauhyperapi`).

Encapsula o runtime local do Hyper de forma análoga ao pacote `tableau/`:
`engine.py` traz o context manager `hyper_session()` e o `HyperEngine` de alto
nível; `db.py` (tarefa 6.0) cobre a extração de bancos externos. Nenhuma tool
fala com o `tableauhyperapi` diretamente — tudo passa por aqui.
"""
