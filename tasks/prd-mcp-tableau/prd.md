# Documento de Requisitos do Produto (PRD)

## Visão Geral

O **MCP Tableau** é um servidor Model Context Protocol que conecta um agente de IA autônomo ao Tableau Cloud e ao Tableau Server, dando a esse agente as ferramentas para construir, validar e publicar conteúdo analítico de ponta a ponta sem um humano no loop. Hoje, criar e implantar painéis confiáveis depende de um especialista que publica, abre a tela, confere visualmente o resultado, valida a integridade dos campos e investiga o ambiente antes de criar algo novo. Sem um equivalente programático e estruturado dessas ações, um agente de IA fica cego: consegue gerar artefatos, mas não consegue confirmar que eles funcionam nem que respeitam o que já existe no servidor.

Este produto resolve esse problema oferecendo um conjunto coeso de ferramentas que cobrem quatro capacidades do ciclo de trabalho do agente — **publicação/deploy**, **inspeção visual**, **validação estrutural/QA** e **consulta a metadados/linhagem**. O valor está em permitir que o agente "veja" e "verifique" seu próprio trabalho com retorno estruturado e legível por máquina, reduzindo retrabalho humano, evitando relatórios duplicados ou quebrados e aumentando a confiança em conteúdo gerado por IA antes de ele chegar a usuários finais.

## Objetivos

- **Autonomia de ponta a ponta**: permitir que o agente complete o fluxo "descobrir → construir → validar → publicar" usando exclusivamente ferramentas do MCP, sem intervenção humana manual no Tableau.
- **Confiabilidade do conteúdo publicado**: maximizar a proporção de publicações que passam na validação estrutural e visual na primeira tentativa (meta inicial: ≥ 80% sem reprovação na inspeção).
- **Redução de duplicidade**: garantir que toda criação de conteúdo seja precedida de consulta a metadados/similaridade, reduzindo a criação de relatórios redundantes (meta: ≥ 90% das criações com checagem prévia de similaridade executada).
- **Prevenção de quebras**: assegurar que alterações em fontes de dados sejam avaliadas quanto a impacto via linhagem antes da publicação (meta: 100% das sobrescritas precedidas de consulta de dependências).
- **Detecção precoce de falhas visuais**: identificar telas em branco ou com alertas de carregamento antes da liberação (meta: 100% das publicações de workbook com pelo menos uma renderização de validação).
- **Métricas a acompanhar**: taxa de sucesso de publicação, taxa de aprovação na inspeção visual, número de erros estruturais detectados por publicação, tempo médio do ciclo completo, contagem de duplicações evitadas.

## Histórias de Usuário

- **US1** — Como agente de IA autônomo, quero publicar um novo workbook em um projeto específico para que o relatório que construí fique disponível no servidor.
- **US2** — Como agente de IA autônomo, quero publicar uma nova fonte de dados estruturada para que outros conteúdos possam reutilizá-la.
- **US3** — Como agente de IA autônomo, quero sobrescrever um workbook ou fonte de dados existente criando uma nova versão para que eu corrija ou evolua conteúdo já implantado.
- **US4** — Como agente de IA multimodal, quero extrair imagens (PNG) ou PDFs das páginas de um painel para que eu possa olhar o resultado e validar se o layout está correto.
- **US5** — Como agente de IA autônomo, quero saber se uma tela renderizada contém erros visuais (gráficos em branco, alertas de falha de carregamento) para que eu não libere um painel quebrado.
- **US6** — Como agente de IA autônomo, quero ler a estrutura interna de um painel para garantir que não há campos quebrados, filtros sem lógica ou conexões inválidas antes de liberá-lo.
- **US7** — Como agente de IA autônomo, quero auditar a complexidade de um painel (quantidade de gráficos, excesso de filtros) para avaliar se ele respeita padrões de performance.
- **US8** — Como agente de IA autônomo, quero rastrear quais painéis dependem de quais fontes de dados para que eu evite alterações que quebrem relatórios de terceiros.
- **US9** — Como agente de IA autônomo, quero consultar o dicionário de uma fonte de dados (nomes de campos, fórmulas de cálculo, regras já homologadas) para que eu reutilize definições corretas ao construir algo novo.
- **US10** — Como agente de IA autônomo, quero pesquisar no servidor por painéis ou bases semelhantes ao que pretendo criar para que eu evite duplicar conteúdo existente.
- **US11** *(persona secundária)* — Como engenheiro de BI supervisor, quero que cada ação do agente retorne um resultado estruturado e auditável (status, identificadores, evidências) para que eu possa revisar e confiar no que foi feito de forma autônoma.
- **US12** *(caso de borda)* — Como agente de IA autônomo, quero receber um erro claro e acionável quando uma publicação falhar (credencial inválida, arquivo grande demais, projeto inexistente) para que eu possa corrigir e tentar novamente sem adivinhação.

## Principais funcionalidades

### 1. Publicação e Implantação (Deploy)
- **O que faz**: envia novos workbooks e fontes de dados ao servidor e atualiza/sobrescreve conteúdo existente, criando novas versões.
- **Por que é importante**: é a forma pela qual o agente materializa seu trabalho no ambiente Tableau.
- **Como funciona em alto nível**: o agente fornece o artefato e o destino (projeto); o MCP realiza a publicação e retorna identificadores e status. Arquivos grandes são suportados de forma transparente.
- **Requisitos funcionais**:
  - **RF1**: O sistema deve permitir publicar um novo workbook em um projeto especificado.
  - **RF2**: O sistema deve permitir publicar uma nova fonte de dados em um projeto especificado.
  - **RF3**: O sistema deve permitir atualizar/sobrescrever um workbook existente, gerando nova versão, mediante indicação explícita de sobrescrita.
  - **RF4**: O sistema deve permitir atualizar/sobrescrever uma fonte de dados existente, gerando nova versão, mediante indicação explícita de sobrescrita.
  - **RF5**: O sistema deve suportar a publicação de artefatos que excedam o limite de envio em requisição única, sem que o agente precise gerenciar manualmente o particionamento.
  - **RF6**: O sistema deve retornar identificador do conteúdo, projeto de destino e status de sucesso/falha de cada publicação.
  - **RF7**: O sistema deve recusar a sobrescrita de conteúdo existente quando a indicação explícita de sobrescrita não for fornecida, retornando erro acionável.

### 2. Inspeção Visual (o "olho" do agente)
- **O que faz**: extrai representações visuais (PNG/PDF) das páginas de um painel e sinaliza indícios de erro visual.
- **Por que é importante**: permite que um agente multimodal valide o layout e detecte falhas que não aparecem na estrutura.
- **Como funciona em alto nível**: o agente solicita a renderização de uma view/painel; o MCP devolve a imagem/PDF e indicadores de possível falha de carregamento.
- **Requisitos funcionais**:
  - **RF8**: O sistema deve permitir extrair a imagem (PNG) de uma página/view de um workbook publicado.
  - **RF9**: O sistema deve permitir extrair o PDF de uma ou mais páginas de um workbook publicado.
  - **RF10**: O sistema deve permitir aplicar filtros/parâmetros na renderização para validar estados específicos da tela.
  - **RF11**: O sistema deve sinalizar indícios de erro visual na renderização (ex.: tela/gráfico em branco, alerta de falha de carregamento), retornando essa avaliação de forma estruturada.
  - **RF12**: O sistema deve retornar a renderização em formato adequado ao consumo por um agente multimodal.

### 3. Validação Estrutural e Técnica (QA)
- **O que faz**: lê a estrutura interna do painel para detectar problemas de integridade e audita boas práticas de performance.
- **Por que é importante**: permite ao agente testar a mecânica do painel antes de liberá-lo, sem depender de teste humano.
- **Como funciona em alto nível**: o MCP inspeciona a composição do conteúdo (campos, filtros, conexões, contagem de elementos) e retorna um diagnóstico estruturado com alertas e recomendações.
- **Requisitos funcionais**:
  - **RF13**: O sistema deve permitir ler a estrutura interna de um workbook (campos, filtros, conexões de dados).
  - **RF14**: O sistema deve identificar campos quebrados, filtros sem lógica aplicável e conexões inválidas, retornando-os de forma estruturada.
  - **RF15**: O sistema deve permitir auditar indicadores de complexidade do painel (ex.: quantidade de gráficos, número de filtros) contra parâmetros de boas práticas.
  - **RF16**: O sistema deve retornar uma avaliação de conformidade com boas práticas, sinalizando riscos de performance e itens que requerem atenção.

### 4. Consulta a Metadados e Contexto (Dicionário)
- **O que faz**: mapeia linhagem, lê o dicionário de dados e busca conteúdo similar no servidor.
- **Por que é importante**: dá ao agente o contexto necessário para construir certo da primeira vez e não quebrar o que já existe.
- **Como funciona em alto nível**: o MCP consulta os metadados do ambiente e retorna dependências, definições de campos/cálculos e candidatos similares ao que o agente pretende criar.
- **Requisitos funcionais**:
  - **RF17**: O sistema deve permitir rastrear quais workbooks/conteúdos dependem de uma determinada fonte de dados (linhagem descendente).
  - **RF18**: O sistema deve permitir rastrear de quais fontes/tabelas um determinado conteúdo depende (linhagem ascendente).
  - **RF19**: O sistema deve permitir consultar o dicionário de uma fonte de dados, incluindo nomes de campos, fórmulas de campos calculados e descrições/regras já homologadas, quando disponíveis.
  - **RF20**: O sistema deve permitir pesquisar no servidor por workbooks e fontes de dados semelhantes a um critério informado, para evitar duplicação.
  - **RF21**: O sistema deve retornar os resultados de metadados de forma estruturada e atribuível (identificadores, nomes, projeto de origem).

### Requisitos transversais
- **RF22**: Toda ferramenta deve retornar um resultado estruturado e legível por máquina, com status explícito de sucesso ou falha.
- **RF23**: Em caso de falha, o sistema deve retornar uma mensagem de erro acionável que identifique a causa provável (ex.: autenticação, permissão, conteúdo inexistente, artefato grande demais) sem expor credenciais.
- **RF24**: O sistema deve operar tanto em Tableau Cloud quanto em Tableau Server, abstraindo diferenças do ambiente para o agente.

## Experiência do usuário

- **Personas e necessidades**:
  - *Primária — Agente de IA autônomo*: precisa de ferramentas determinísticas, com entradas e saídas estruturadas, que permitam encadear descoberta, construção, validação e publicação sem supervisão.
  - *Secundária — Engenheiro de BI supervisor*: precisa de rastreabilidade e evidências (status, identificadores, renderizações, diagnósticos) para confiar e auditar o trabalho autônomo.
- **Fluxo principal (jornada do agente)**:
  1. **Descobrir** — consulta metadados, dicionário e similaridade para entender o ambiente e evitar duplicação (Capacidade 4).
  2. **Construir/Publicar** — publica ou sobrescreve o conteúdo no projeto de destino (Capacidade 1).
  3. **Validar estrutura** — verifica integridade e boas práticas do conteúdo publicado (Capacidade 3).
  4. **Inspecionar visualmente** — renderiza a tela e avalia erros visuais (Capacidade 2).
  5. **Decidir** — com base nas evidências estruturadas, o agente confirma a entrega ou inicia uma correção.
- **Casos de borda**: artefato acima do limite de envio único, credencial/token inválido ou expirado, projeto de destino inexistente, sobrescrita não autorizada, tela renderizada em branco. Em todos, o agente deve receber retorno suficiente para decidir o próximo passo.
- **Considerações de UI/UX e acessibilidade**: a "interface" deste produto é a superfície de ferramentas MCP consumida por um agente; portanto, a usabilidade se traduz em **clareza, consistência e previsibilidade** dos nomes de ferramentas, parâmetros e formatos de retorno. As saídas devem ser autodescritivas e consistentes entre ferramentas, com mensagens de erro compreensíveis. A acessibilidade do conteúdo final do Tableau (cores, contraste, leitura de telas) é responsabilidade do artefato gerado pelo agente, mas o produto deve preservar e expor evidências (renderizações) que permitam ao agente avaliar a qualidade visual do resultado.

## Restrições técnicas de alto nível

- **Integração externa obrigatória**: Tableau REST API para publicação, renderização e inspeção; Tableau Metadata API (GraphQL) para linhagem, dicionário e busca de similaridade. Ambas compartilham o mesmo mecanismo de autenticação.
- **Compatibilidade de ambiente**: deve funcionar em Tableau Cloud e Tableau Server, considerando diferenças de versão e de recursos disponíveis entre eles.
- **Protocolo não negociável**: as capacidades devem ser expostas como ferramentas via Model Context Protocol (MCP), consumíveis por agentes.
- **Segurança e credenciais**: autenticação via Personal Access Token (PAT). Tokens e segredos não podem ser expostos em logs, retornos de ferramentas ou mensagens de erro. As permissões efetivas no Tableau são herdadas da identidade associada ao PAT.
- **Limites da plataforma**: o envio de artefatos em requisição única é limitado pela plataforma (64 MB por requisição única; artefatos maiores exigem envio particionado de forma transparente). Atualizações específicas podem ter limites adicionais definidos por configuração do servidor.
- **Privacidade de dados**: renderizações (PNG/PDF) e metadados podem conter dados de negócio sensíveis; o tratamento deve respeitar as permissões do ambiente e não persistir dados além do necessário para a resposta.
- **Desempenho/escala**: operações de renderização e de metadados podem ser custosas; o produto deve refletir adequadamente operações assíncronas/demoradas da plataforma sem mascarar falhas.

*Os detalhes de implementação serão tratados na Especificação Técnica.*

## Fora do escopo

- **Capacidade 5 — Ciclo de Vida e Atualização de Dados** (disparo de carga/refresh de extração e monitoramento de processamento de jobs): considerada evolução futura, fora do MVP.
- **Capacidade 6 — Organização e Governança** (movimentação de conteúdo entre projetos, tagueamento e certificação, criação de projetos/pastas): considerada evolução futura, fora do MVP.
- **Autoria/edição do conteúdo do painel**: o MCP não cria nem edita o design interno do workbook (gráficos, cálculos, layout); ele publica, valida e inspeciona artefatos. A construção do artefato é responsabilidade do agente por outros meios.
- **Suporte a métodos de autenticação distintos de PAT** (ex.: usuário/senha, SAML/SSO interativo): fora do escopo inicial.
- **Gestão de usuários, grupos e permissões** no Tableau: fora do escopo.
- **Interface gráfica para humanos**: o produto é uma superfície de ferramentas para agentes, sem UI própria.
- **Correção automática de erros detectados**: o produto detecta e reporta problemas estruturais/visuais, mas não corrige automaticamente o conteúdo.

*(Nota: riscos técnicos de implementação serão detalhados na Especificação Técnica.)*
