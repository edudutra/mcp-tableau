# Tarefa 2.0: Camada de integração REST (`tableau/client.py`)

## Visão geral

Implementa o `TableauClient`, único componente que fala REST com o Tableau via
`tableauserverclient` (TSC). Centraliza autenticação PAT (sign-in/sign-out garantido por context
manager), re-autenticação lazy em expiração/401, publicação de workbook/datasource com
`PublishMode` e chunking automático acima de 64 MB, download de artefato, renderização de imagem
PNG e PDF (`populate_image`/`populate_pdf` com filtros `vf_`), resolução de projeto por nome,
listagem/paginação de conteúdo e tradução de exceções do TSC para o envelope `ToolError`.
Abstrai diferenças entre Tableau Cloud e Server.

<skills>
### Conformidade com skills

- **`code-standards`** — acesso ao Tableau exclusivamente via `tableau/client.py`, credenciais
  por env, sem segredos em logs/erros, erros acionáveis, type hints.
- **`testing-standards`** — TSC sempre mockado nos unitários; nomenclatura
  `test_<unidade>_<cenario>_<resultado>`; fixtures em `conftest.py`.
</skills>

<requirements>
- **RF5**: Suportar publicação de artefatos acima do limite de envio único (chunking
  transparente >64 MB), sem gestão manual de particionamento pelo agente.
- **RF6**: Retornar identificador, projeto de destino e status de cada publicação.
- **RF23**: Traduzir falhas em erro acionável (auth/permissão/not found/payload) sem expor
  credenciais.
- **RF24**: Operar em Tableau Cloud e Server, abstraindo diferenças do ambiente.
</requirements>

## Subtarefas

- [x] 2.1 Implementar sign-in/sign-out PAT com context manager (sign-out garantido mesmo em erro)
  usando a `Settings` da Tarefa 1.0.
- [x] 2.2 Implementar re-autenticação lazy: ao detectar token expirado/401, re-autenticar e
  repetir a operação **uma vez**.
- [x] 2.3 Implementar `publish_workbook`/`publish_datasource` com `PublishMode` (Create/Overwrite)
  e chunking automático >64 MB; expor flag `chunked` no resultado.
- [x] 2.4 Implementar `download_workbook` (artefato para diretório destino) e
  `render_view_image`/`render_view_pdf` com `ImageRequestOptions`/`PDFRequestOptions`
  (filtros `vf_`, `resolution=high`, `page_type`).
- [x] 2.5 Implementar `find_project_id` (resolução por nome) e `search_content` (listagem com
  paginação completa).
- [x] 2.6 Implementar tradução de exceções TSC (`ServerResponseError` 401/403/404,
  `NotSignedInError`, `EndpointUnavailableError`) para códigos `ToolError`
  (`AUTH_FAILED`, `PERMISSION_DENIED`, `NOT_FOUND`, `PAYLOAD_TOO_LARGE`, `UPSTREAM_ERROR`),
  garantindo que o PAT nunca apareça em mensagens.

## Detalhes de implementação

Ver techspec.md § "Principais interfaces" (assinaturas de `TableauClient`),
§ "Pontos de integração" (PAT, `PublishMode`, chunking, `populate_image/pdf`, re-auth),
§ "Parâmetros fixados no upstream" e § "Tratamento de erros".

## Critérios de sucesso

- Sign-in usa o PAT da config; sign-out sempre executado (inclusive em exceção).
- Token expirado dispara re-auth e repete a operação exatamente uma vez.
- Publicação de arquivo grande aciona chunking e reporta `chunked=true`.
- Erros REST 404/403/401 são traduzidos nos códigos corretos do `ToolError`.
- Nenhuma mensagem de erro contém o PAT/secret.
- Paginação retorna todo o conteúdo listável.

## Testes da tarefa

### Testes unitários

- [x] `test_client_sign_in_usa_pat_da_config`
- [x] `test_client_sign_out_garantido_mesmo_em_erro`
- [x] `test_client_token_expirado_dispara_reauth_e_repete_uma_vez`
- [x] `test_client_traduz_serverresponseerror_404_para_not_found`
- [x] `test_client_traduz_403_para_permission_denied`
- [x] `test_client_nunca_inclui_pat_em_mensagem_de_erro`
- [x] `test_client_paginacao_lista_todo_o_conteudo`

### Testes de integração

- [ ] (Tarefa 9.0) `test_integration_publish_e_download_roundtrip` (`@pytest.mark.integration`,
  sandbox real).
- [ ] (Tarefa 9.0) `test_integration_render_view_image_retorna_png_valido`
  (`@pytest.mark.integration`).

## Arquivos relevantes

- `src/mcp_tableau/tableau/__init__.py`
- `src/mcp_tableau/tableau/client.py`
- `tests/tableau/test_client.py`
