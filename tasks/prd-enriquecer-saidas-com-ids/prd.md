# Documento de Requisitos do Produto (PRD)

## Visão Geral

As ferramentas de QA estrutural do MCP Tableau (`inspect_workbook_structure`) hoje devolvem worksheets e dashboards apenas como listas de nomes (texto), e referenciam conexões e filtros somente pelo nome da worksheet/fonte. Isso impede que um agente encadeie o resultado em outras ferramentas: para renderizar uma view (`render_view_image` / `render_workbook_pdf`) ou consultar metadados (linhagem, dicionário) é preciso o **identificador** do objeto, que não é retornado. O agente fica obrigado a uma etapa manual de descoberta de ID, quebrando a automação ponta a ponta.

Esta feature enriquece as saídas da inspeção estrutural para que cada worksheet, dashboard, conexão e filtro carregue, além do nome, o seu identificador. O resultado passa a ser diretamente acionável: o agente identifica um problema na estrutura e segue imediatamente para renderizar a view suspeita ou consultar a linhagem do conteúdo, sem buscas intermediárias. O público são agentes de IA e desenvolvedores que orquestram diagnóstico de workbooks Tableau via MCP.

## Objetivos

- Permitir o encadeamento direto da saída estrutural para as ferramentas de renderização e de metadados, eliminando a etapa manual de descoberta de IDs.
- Garantir que todo objeto identificável retornado pela inspeção estrutural (worksheet, dashboard, conexão, filtro) inclua um identificador estável além do nome.
- Métrica de sucesso: 100% dos worksheets e dashboards renderizáveis retornados pela inspeção podem ser passados como entrada para `render_view_image`/`render_workbook_pdf` sem nenhuma chamada intermediária de descoberta.
- Métrica de sucesso: ID de um conteúdo retornado pela inspeção é aceito sem transformação como entrada nas ferramentas de linhagem/dicionário.
- Manter o tempo de resposta da inspeção dentro da mesma ordem de grandeza atual (sem regressão perceptível para o usuário).

## Histórias de Usuário

- US1: Como agente de IA que inspeciona um workbook, quero receber o ID de cada worksheet e dashboard junto do nome, para renderizar a view suspeita de erro visual sem precisar descobrir o ID em uma etapa separada.
- US2: Como agente de IA que detecta um problema estrutural em um conteúdo, quero o ID do conteúdo na resposta, para consultar a linhagem ou o dicionário daquele conteúdo na chamada seguinte.
- US3: Como desenvolvedor que integra o MCP Tableau em um fluxo automatizado, quero que cada conexão e filtro retornado seja identificável de forma não ambígua, para correlacionar problemas estruturais com o objeto correto mesmo quando há nomes repetidos.
- US4: Como consumidor da API, quero um contrato de saída claro e previsível em que objetos identificáveis são representados como estrutura `{id, nome, ...}`, para tratar a resposta de forma uniforme.
- US5 (caso de borda): Como agente, quando um objeto não possuir identificador disponível no upstream (ex.: worksheet não publicada como view), quero que isso seja sinalizado de forma explícita e não ambígua, para distinguir "sem ID" de "erro", sem que a ferramenta falhe.

## Principais funcionalidades

### 1. Worksheets e dashboards identificáveis na inspeção estrutural

- **O que faz**: substitui as listas de nomes de worksheets e dashboards por uma representação estruturada que inclui o identificador renderizável de cada um, além do nome.
- **Por que é importante**: é o habilitador central do encadeamento estrutura → renderização; sem o ID renderizável o resultado não é acionável.
- **Como funciona em alto nível**: a inspeção passa a associar cada worksheet/dashboard ao seu identificador de view no servidor; quando o identificador não estiver disponível, o campo correspondente é explicitamente nulo.
- **Requisitos funcionais**:
  - RF1: A inspeção estrutural deve retornar cada worksheet como um objeto contendo, no mínimo, `id` e `name`.
  - RF2: A inspeção estrutural deve retornar cada dashboard como um objeto contendo, no mínimo, `id` e `name`.
  - RF3: O `id` de worksheets e dashboards retornado deve ser o identificador aceito como entrada pelas ferramentas de renderização de view, sem transformação.
  - RF4: Quando um worksheet ou dashboard não possuir identificador disponível no upstream, o campo `id` deve ser retornado como nulo (e não omitido), preservando o nome.

### 2. Conexões e filtros identificáveis

- **O que faz**: enriquece os itens de conexão e de filtro do relatório estrutural com identificação não ambígua do objeto e do worksheet ao qual pertencem.
- **Por que é importante**: permite correlacionar de forma confiável um problema (conexão inválida, filtro sem lógica) ao objeto exato, inclusive na presença de nomes duplicados, e habilita ações subsequentes sobre o conteúdo correto.
- **Como funciona em alto nível**: cada conexão e cada filtro passa a referenciar o identificador do conteúdo/worksheet relacionado quando disponível, mantendo os campos descritivos atuais.
- **Requisitos funcionais**:
  - RF5: Cada item de conexão retornado deve incluir um identificador da conexão/fonte de dados associada quando disponível, além dos campos atuais.
  - RF6: Cada item de filtro retornado deve incluir o identificador do worksheet ao qual pertence quando disponível, além do nome do worksheet.
  - RF7: Quando o identificador de uma conexão ou filtro não estiver disponível no upstream, o campo deve ser retornado como nulo (e não omitido).

### 3. Contrato de saída uniforme e previsível

- **O que faz**: padroniza a representação de objetos identificáveis nas saídas afetadas, substituindo listas de strings por objetos estruturados `{id, name, ...}`.
- **Por que é importante**: torna a resposta consistente e fácil de consumir programaticamente; alinha a saída estrutural ao padrão já adotado por similaridade e linhagem (que retornam `id` + `name`).
- **Como funciona em alto nível**: o esquema de saída das ferramentas afetadas é atualizado para o novo formato estruturado; o contrato é versionado/documentado e comunicado como mudança incompatível.
- **Requisitos funcionais**:
  - RF8: Objetos identificáveis nas saídas afetadas devem ser representados como estrutura `{id, name, ...}` em vez de string simples.
  - RF9: A mudança de contrato deve ser refletida na documentação da ferramenta (descrição/esquema) de forma que o consumidor saiba o novo formato esperado.
  - RF10: A semântica de erro existente deve ser preservada: ausência de identificador é representada por valor nulo no campo, nunca por um envelope de erro; a ferramenta só retorna erro nas mesmas condições de falha já existentes.
  - RF11: As demais ferramentas que já retornam `id` (busca de similaridade e linhagem) devem ser verificadas quanto à consistência do formato; qualquer divergência identificada deve ser alinhada ao mesmo padrão.

## Experiência do usuário

- **Personas e necessidades**: agentes de IA orquestrando diagnóstico/renderização de workbooks e desenvolvedores integrando os fluxos MCP. Ambos precisam de respostas acionáveis sem etapas manuais de descoberta de ID.
- **Fluxos principais**:
  - Inspecionar estrutura → escolher worksheet/dashboard pelo resultado → renderizar a view diretamente com o `id` recebido.
  - Inspecionar estrutura → identificar problema em um conteúdo → consultar linhagem/dicionário com o `id` recebido.
- **Interações**: a saída é JSON estruturado consumido por outra ferramenta MCP; não há interface gráfica. A clareza do contrato (nomes de campos, presença de `id`, valor nulo quando ausente) é o equivalente de "usabilidade" aqui.
- **Considerações de UI/UX**: nomes de campos consistentes e autoexplicativos; representação uniforme de objetos identificáveis; distinção inequívoca entre "ID ausente" (nulo) e "erro" (envelope de erro).
- **Acessibilidade**: como contrato de máquina, a acessibilidade traduz-se em previsibilidade e documentação clara do esquema, permitindo consumo confiável por qualquer cliente; mensagens e campos devem permanecer descritivos e não ambíguos.

## Restrições técnicas de alto nível

- Integração obrigatória com o Tableau existente: os identificadores devem ser os mesmos LUIDs aceitos pelas demais ferramentas (renderização, linhagem, dicionário), para que o encadeamento funcione sem conversão.
- Restrição de origem de dados: a inspeção estrutural opera sobre o arquivo de workbook (`.twb`/`.twbx`), que **não** carrega os identificadores de view do servidor. Obter o `id` renderizável de worksheets/dashboards exige uma consulta ao Tableau (lado servidor), e nem todo worksheet local corresponde a uma view publicada — daí a necessidade de `id` nulo quando não houver correspondência (RF4).
- Segurança: nenhum identificador, mensagem ou log pode expor credenciais, tokens ou PATs; o tratamento de erro sanitizado atual deve ser mantido.
- Compatibilidade: a mudança para objetos `{id, name}` é assumida como **incompatível** com o contrato atual (substitui listas de strings); deve ser comunicada e documentada como breaking change.
- Desempenho: o enriquecimento com IDs não deve introduzir regressão perceptível de latência; chamadas adicionais ao servidor, se necessárias, devem ser minimizadas.
- Privacidade de dados: a saída não deve passar a incluir dados sensíveis além dos identificadores e metadados estruturais já expostos.

(Os detalhes de implementação serão tratados na Especificação Técnica.)

## Fora do escopo

- Adicionar identificadores a campos do dicionário de dados (`DataDictionary`/`DictionaryField`) — não solicitado nesta feature.
- Reescrever a busca de similaridade ou a linhagem, que já retornam `id`; apenas verificação de consistência de formato está no escopo (RF11), não redesenho.
- Renderizar automaticamente views a partir da inspeção; a feature entrega os IDs, mas o disparo da renderização continua sendo uma ação separada do consumidor.
- Camada de compatibilidade retroativa (manter simultaneamente o formato antigo de listas de strings) — explicitamente não será fornecida.
- Novos códigos de erro ou mudança na semântica de falha das ferramentas.
- Persistência, cache ou indexação dos identificadores entre chamadas.

(Nota: riscos técnicos de implementação serão detalhados na Especificação Técnica.)
