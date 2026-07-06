# Documento de Requisitos do Produto (PRD)

## Visão Geral

O servidor MCP Tableau hoje cobre o ciclo de **publicação e validação** de conteúdo (deploy, inspeção visual, QA estrutural e metadados), mas não consegue **criar nem processar os dados** que alimentam esse conteúdo. Quando um agente de IA precisa materializar um datasource — por exemplo, transformar um CSV recebido de uma área de negócio em um extrato publicável — ele depende de um humano ou de ferramentas externas para gerar o arquivo `.hyper`, quebrando o fluxo autônomo **descobrir → construir → validar → publicar**.

Esta feature adiciona ao MCP as capacidades da **Tableau Hyper API**: criar arquivos `.hyper` a partir de arquivos locais (CSV/Parquet), de dados enviados inline pelo agente ou de bancos de dados externos; consultar e transformar esses arquivos via SQL; inspecionar seus schemas; e integrá-los ao fluxo de publicação já existente. O público-alvo são agentes de IA autônomos (e os analistas/engenheiros que os operam) que passam a completar de ponta a ponta a criação de datasources no Tableau Server/Cloud, com retornos estruturados e auditáveis.

## Objetivos

- Permitir que um agente crie um datasource publicado no Tableau a partir de dados brutos (arquivo, inline ou banco) **sem nenhuma intervenção humana**, em uma única sessão de conversa.
- Cobrir 100% do ciclo de vida local de um extrato: criar, inspecionar, consultar, transformar e publicar.
- Toda operação deve retornar resultado estruturado (sucesso ou erro tipado), mantendo o padrão de auditabilidade das tools existentes.
- Operações sobre grandes volumes devem gerar **alerta explícito** (nunca bloqueio), permitindo que o usuário decida prosseguir.
- Métricas de sucesso:
  - Fluxo "CSV → `.hyper` → datasource publicado" completado por um agente de ponta a ponta em ambiente de homologação.
  - Consultas SQL sobre `.hyper` retornando resultados corretos e legíveis pelo agente.
  - Zero exposição de credenciais de banco em logs ou retornos das tools.

## Histórias de Usuário

- **US1** — Como agente de IA, eu quero criar um arquivo `.hyper` a partir de um CSV ou Parquet local para que dados brutos entregues pela área de negócio virem um extrato pronto para publicação.
- **US2** — Como agente de IA, eu quero enviar registros inline (pequenas tabelas, de-para, dados de referência) diretamente na chamada da tool para que eu materialize datasources auxiliares sem precisar de arquivos intermediários.
- **US3** — Como agente de IA, eu quero extrair o resultado de uma query SQL de um banco de dados externo para um `.hyper` para que dados corporativos sejam materializados como extratos Tableau.
- **US4** — Como agente de IA, eu quero executar consultas SQL sobre um `.hyper` existente para que eu valide e explore os dados (contagens, amostras, agregações) antes de publicar.
- **US5** — Como agente de IA, eu quero inspecionar o schema de um `.hyper` (tabelas, colunas, tipos, contagem de linhas) para que eu entenda a estrutura de extratos criados por mim ou por terceiros.
- **US6** — Como agente de IA, eu quero atualizar e transformar um `.hyper` existente (append de dados, INSERT/UPDATE/DELETE, tabelas derivadas) para que eu enriqueça extratos de forma incremental sem recriá-los do zero.
- **US7** — Como agente de IA, eu quero publicar um `.hyper` como datasource no Tableau Server/Cloud, integrado ao fluxo de publicação existente, para que o ciclo termine com o dado disponível aos consumidores finais.
- **US8** — Como analista/engenheiro que opera o agente, eu quero ser alertado quando uma operação envolver grande volume de dados para que eu decida conscientemente se prossigo, sem ser bloqueado.
- **US9** — Como administrador do ambiente, eu quero que credenciais de bancos externos sejam configuradas por variáveis de ambiente e nunca trafeguem nas chamadas das tools para que o risco de vazamento seja minimizado.
- **US10** — Como agente de IA, eu quero receber erros estruturados e acionáveis (arquivo inexistente, schema incompatível, SQL inválido, falha de conexão) para que eu corrija o problema e tente novamente sem ajuda humana.

## Principais funcionalidades

### F1. Criação de `.hyper` a partir de arquivos locais

- **O que faz**: cria um arquivo `.hyper` a partir de um CSV ou Parquet acessível no filesystem do servidor MCP, com schema inferido automaticamente ou definido explicitamente pelo agente.
- **Por que é importante**: é a porta de entrada mais comum de dados brutos; sem ela o agente não consegue iniciar o ciclo de criação de datasources.
- **Como funciona em alto nível**: o agente informa o caminho do arquivo de origem, o destino do `.hyper`, o nome da tabela e, opcionalmente, o schema; recebe de volta um relatório estruturado (tabela criada, colunas, tipos, linhas carregadas).

Requisitos funcionais:

1. **RF1** — O sistema deve criar um `.hyper` a partir de um arquivo CSV local, com opções de delimitador, encoding e presença de cabeçalho.
2. **RF2** — O sistema deve criar um `.hyper` a partir de um arquivo Parquet local.
3. **RF3** — O sistema deve inferir o schema (nomes e tipos de colunas) quando não informado, e aceitar schema explícito quando fornecido pelo agente.
4. **RF4** — O sistema deve retornar um relatório estruturado da criação: caminho do arquivo gerado, tabela, colunas com tipos e total de linhas carregadas.
5. **RF5** — O sistema deve retornar erro estruturado quando o arquivo de origem não existir, estiver corrompido ou o schema informado for incompatível com os dados.

### F2. Criação de `.hyper` a partir de dados inline

- **O que faz**: cria (ou adiciona dados a) um `.hyper` a partir de registros enviados diretamente na chamada da tool.
- **Por que é importante**: habilita casos de pequeno volume (tabelas de-para, dimensões de referência, dados sintéticos de teste) sem arquivos intermediários.
- **Como funciona em alto nível**: o agente envia a definição das colunas e as linhas na própria chamada; o sistema valida, grava e retorna o relatório de criação.

Requisitos funcionais:

6. **RF6** — O sistema deve criar um `.hyper` a partir de colunas e linhas fornecidas inline pelo agente.
7. **RF7** — O sistema deve validar os dados inline contra o schema declarado e reportar, em erro estruturado, as linhas/colunas inconsistentes.
8. **RF8** — O sistema deve documentar e aplicar um limite recomendado de volume para dados inline, orientando o agente a usar arquivos quando excedido.

### F3. Extração de bancos de dados externos para `.hyper`

- **O que faz**: executa uma query SQL em um banco de dados externo e materializa o resultado em um arquivo `.hyper`.
- **Por que é importante**: conecta o MCP às fontes corporativas de dados, o cenário mais valioso para criação de datasources reais.
- **Como funciona em alto nível**: a conexão é configurada pelo administrador via variável de ambiente (connection string/DSN genérica, agnóstica de banco); o agente informa apenas a query e o destino; o sistema extrai, grava o `.hyper` e retorna o relatório.

Requisitos funcionais:

9. **RF9** — O sistema deve materializar em `.hyper` o resultado de uma query SQL executada em um banco externo configurado via connection string em variável de ambiente.
10. **RF10** — O sistema deve ser agnóstico de banco: qualquer fonte com driver compatível configurável pela connection string deve funcionar, sem lógica específica por fornecedor.
11. **RF11** — Credenciais e connection strings nunca devem ser aceitas como parâmetro de tool, nem aparecer em logs, mensagens de erro ou retornos.
12. **RF12** — O sistema deve retornar erro estruturado distinguindo falha de conexão, falha de autenticação e erro de SQL na fonte.

### F4. Consulta SQL sobre arquivos `.hyper`

- **O que faz**: executa consultas SQL de leitura sobre um `.hyper` existente e retorna os resultados de forma estruturada.
- **Por que é importante**: permite ao agente validar e explorar dados (contagens, amostras, agregações) antes de publicar — etapa central de QA de dados.
- **Como funciona em alto nível**: o agente informa o caminho do `.hyper` e a consulta; o sistema executa e retorna colunas e linhas, com limite configurável de linhas retornadas para proteger o contexto do agente.

Requisitos funcionais:

13. **RF13** — O sistema deve executar consultas SQL de leitura sobre um `.hyper` e retornar resultados estruturados (colunas, tipos e linhas).
14. **RF14** — O sistema deve limitar a quantidade de linhas retornadas por padrão (limite configurável), informando ao agente quando houver truncamento.
15. **RF15** — O sistema deve retornar erro estruturado com a mensagem original do motor SQL quando a consulta for inválida.

### F5. Inspeção de schema de arquivos `.hyper`

- **O que faz**: lista schemas, tabelas, colunas (com tipos e nulabilidade) e contagem de linhas de um `.hyper` existente.
- **Por que é importante**: dá visibilidade sobre extratos criados por terceiros ou em etapas anteriores, no mesmo espírito do `inspect_workbook_structure` já existente.
- **Como funciona em alto nível**: o agente informa o caminho do arquivo e recebe um relatório estrutural completo.

Requisitos funcionais:

16. **RF16** — O sistema deve listar todos os schemas e tabelas de um `.hyper`, com colunas, tipos, nulabilidade e contagem de linhas por tabela.
17. **RF17** — O sistema deve retornar erro estruturado quando o arquivo não for um `.hyper` válido.

### F6. Atualização e transformação de arquivos `.hyper`

- **O que faz**: modifica um `.hyper` existente — append de dados de arquivos ou inline, comandos INSERT/UPDATE/DELETE e criação de tabelas derivadas via SQL.
- **Por que é importante**: evita recriar extratos do zero a cada mudança, habilitando enriquecimento incremental e preparação de dados dentro do próprio extrato.
- **Como funciona em alto nível**: o agente indica o `.hyper` alvo e a operação desejada; o sistema executa e retorna o resultado (linhas afetadas, nova estrutura quando aplicável).

Requisitos funcionais:

18. **RF18** — O sistema deve permitir append de dados a uma tabela existente de um `.hyper`, a partir de arquivo local ou de dados inline, validando compatibilidade de schema.
19. **RF19** — O sistema deve executar comandos SQL de modificação (INSERT, UPDATE, DELETE) sobre um `.hyper`, retornando o número de linhas afetadas.
20. **RF20** — O sistema deve permitir a criação de tabelas derivadas dentro do `.hyper` a partir de consultas SQL sobre tabelas existentes.

### F7. Integração com o fluxo de publicação existente

- **O que faz**: publica o `.hyper` gerado como datasource no Tableau Server/Cloud, reutilizando o fluxo de publicação já existente no MCP.
- **Por que é importante**: fecha o ciclo — o valor final é o dado disponível no servidor, não o arquivo local.
- **Como funciona em alto nível**: o agente aciona a publicação apontando para o `.hyper` (empacotado como datasource publicável quando necessário), com as mesmas garantias de projeto de destino e sobrescrita do `publish_datasource` atual.

Requisitos funcionais:

21. **RF21** — O sistema deve permitir publicar um arquivo `.hyper` como datasource no Tableau Server/Cloud, integrado ao fluxo de publicação existente (mesmos parâmetros de projeto de destino e política de sobrescrita).
22. **RF22** — O retorno da publicação deve incluir os identificadores do datasource criado/atualizado no servidor, permitindo encadeamento imediato com as tools de metadados e QA existentes.

### F8. Salvaguardas de volume

- **O que faz**: detecta operações potencialmente pesadas (arquivos de origem grandes, resultados extensos, extrações longas) e alerta o agente/usuário antes e durante o processamento, sem impedir a execução.
- **Por que é importante**: o servidor MCP roda no host local; operações de grande volume podem esgotar disco, memória ou tempo, e o usuário deve decidir conscientemente.
- **Como funciona em alto nível**: limiares configuráveis (no padrão dos existentes `MAX_FILTERS`/`MAX_WORKSHEETS`); ao exceder um limiar, a resposta inclui um alerta claro com a dimensão excedida, e o agente pode confirmar o prosseguimento.

Requisitos funcionais:

23. **RF23** — O sistema deve emitir alerta estruturado (não bloqueante) quando uma operação exceder limiares configuráveis de volume (ex.: tamanho do arquivo de origem, número de linhas estimado).
24. **RF24** — O alerta deve indicar a dimensão excedida e o risco associado, e a operação deve prosseguir apenas mediante confirmação explícita do agente na chamada (parâmetro de confirmação).
25. **RF25** — Os limiares de volume devem ser configuráveis por variáveis de ambiente, com defaults conservadores documentados.

## Experiência do usuário

- **Personas e necessidades**:
  - *Agente de IA autônomo* (persona primária): consome as tools via MCP; precisa de contratos claros, retornos estruturados e erros acionáveis para operar sem intervenção humana.
  - *Analista/engenheiro de dados* (persona secundária): conversa com o agente; precisa de mensagens finais compreensíveis, alertas de volume claros e confiança de que credenciais estão protegidas.
  - *Administrador do ambiente* (persona secundária): configura variáveis de ambiente (connection strings, limiares); precisa de documentação objetiva de configuração.
- **Fluxos principais**:
  1. *Arquivo → publicação*: criar `.hyper` de CSV/Parquet → inspecionar schema → consultar amostras → publicar como datasource → validar com tools de metadados existentes.
  2. *Banco → publicação*: extrair query de banco externo → transformar/derivar tabelas → publicar.
  3. *Enriquecimento incremental*: inspecionar `.hyper` existente → append/modificação → republicar.
  4. *Fluxo com alerta de volume*: operação excede limiar → tool retorna alerta → agente repassa ao usuário → usuário decide → agente repete a chamada com confirmação.
- **Considerações de UI/UX**: não há interface gráfica; a "UX" é o design dos contratos das tools — nomes autoexplicativos, parâmetros com defaults sensatos, descrições que orientem o agente a escolher a tool correta, e respostas que caibam no contexto do agente (truncamento informado).
- **Acessibilidade**: todas as mensagens de retorno e alertas devem ser textuais, claras e em linguagem natural (além dos campos estruturados), para que o agente as repasse a qualquer usuário final sem perda de significado; documentação em português seguindo o padrão do repositório.

## Restrições técnicas de alto nível

- **Tableau Hyper API** (`tableauhyperapi`) como motor obrigatório de criação/consulta de `.hyper`; compatível com Python >= 3.13 (requisito da stack atual). A biblioteca embarca o runtime proprietário Hyper (binário local), o que aumenta o tamanho da instalação e exige plataforma suportada (Linux/macOS/Windows x64/arm64).
- **Integração obrigatória** com o servidor FastMCP existente (transporte stdio) e com o fluxo de publicação atual via `tableauserverclient` — as novas tools seguem o mesmo padrão de registro e de retornos tipados do projeto.
- **Segurança de credenciais**: connection strings e segredos de banco somente via variáveis de ambiente; proibido trafegar credenciais em parâmetros, logs ou retornos (mesmo padrão do PAT do Tableau já adotado).
- **Execução local**: o processamento ocorre no host do servidor MCP; disco e memória locais são o limite físico. Grandes volumes geram alerta, não bloqueio (RF23–RF25).
- **Privacidade de dados**: os dados extraídos podem conter informação sensível; arquivos `.hyper` intermediários residem no filesystem local e seu ciclo de vida (localização e limpeza) deve ser documentado.
- **Sem serviços adicionais**: nenhuma dependência de infraestrutura nova (filas, bancos auxiliares, schedulers); tudo roda no processo do servidor MCP sob demanda.

## Fora do escopo

- **Governança e permissões Tableau**: nenhuma gestão de permissões, projetos, usuários ou grupos além do que o fluxo de publicação atual já faz.
- **Agendamento/orquestração**: sem schedules, refresh recorrente ou pipelines automáticos; cada execução é disparada pelo agente sob demanda.
- **UI/visualização de dados**: nenhuma interface gráfica; consumo exclusivamente via tools MCP.
- **Atualização incremental de extratos remotos** (Update Hyper Data REST API): atualizar extratos já publicados diretamente no servidor fica como evolução futura; nesta versão a atualização é local, seguida de republicação.
- **Modelagem semântica avançada**: criação de cálculos, relacionamentos e hierarquias de datasources (camada `.tds`) limita-se ao mínimo necessário para tornar o `.hyper` publicável; edição rica de XML de workbooks/datasources não faz parte desta feature.
- **Conectores específicos por fornecedor de banco**: otimizações ou autenticações proprietárias (ex.: Kerberos, IAM) ficam fora; a primeira versão cobre o caminho genérico via connection string.
- **Escrita de volta em bancos externos**: o fluxo é somente leitura na origem; o MCP não grava dados em bancos corporativos.
