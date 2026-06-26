Desenvolver um MCP para conexao com Tableau Server/Cloud com as seguintes capacidades

### 1. Capacidade de Publicação e Implantação (Deploy)

As ferramentas que permitem ao agente materializar o trabalho dele no servidor.

* **Publicação de Painéis (Workbooks):** Capacidade de enviar novos relatórios para projetos específicos.
* **Publicação de Fontes de Dados (Datasources):** Capacidade de disponibilizar novas bases de dados estruturadas.
* **Atualização/Sobrescrita:** Capacidade de atualizar painéis ou fontes de dados que já existem, criando novas versões.

### 2. Capacidade de Inspeção Visual (O "Olho" do Agente)

Como o humano não está testando, o agente precisa de ferramentas para "ver" o resultado do que criou.

* **Renderização de Telas:** Capacidade de extrair imagens (PNG) ou PDFs das páginas do painel gerado. *Isso permite que um agente multimodal olhe para a imagem e valide se o layout está correto.*
* **Captura de Erros Visuais:** Capacidade de identificar se a tela renderizada gerou algum alerta de erro visual (como gráficos em branco ou alertas de falha de carregamento).

### 3. Capacidade de Validação Estrutural e Técnica (QA)

Ferramentas para o agente testar a mecânica do painel antes de liberá-lo.

* **Checagem de Integridade:** Capacidade de ler a estrutura interna do painel para garantir que não existem campos quebrados, filtros sem lógica ou conexões inválidas.
* **Auditoria de Boas Práticas:** Capacidade de analisar a complexidade do painel (quantidade de gráficos, excesso de filtros) para avaliar se ele respeita padrões de performance e se vai carregar rápido para o usuário.

### 4. Capacidade de Consulta a Metadados e Contexto (Dicionário)

Ferramentas para o agente entender o ambiente antes de começar a construir algo novo.

* **Mapeamento de Linhagem:** Capacidade de rastrear quais painéis dependem de quais fontes de dados (para evitar alterações que quebrem relatórios de terceiros).
* **Leitura de Dicionário de Dados:** Capacidade de consultar as fontes de dados existentes para entender os nomes dos campos, fórmulas de cálculos e regras de negócio já homologadas na empresa.
* **Busca de Similaridade:** Capacidade de pesquisar no servidor por painéis ou bases parecidas, evitando criar relatórios duplicados.

### 5. Capacidade de Ciclo de Vida e Atualização de Dados

Ferramentas para garantir que o painel exibe a informação correta durante os testes.

* **Disparo de Carga de Dados:** Capacidade de ordenar que uma base de dados seja atualizada naquele momento para refletir os dados mais recentes.
* **Monitoramento de Processamento:** Capacidade de acompanhar o andamento dessa atualização e saber se ela terminou com sucesso ou se falhou.

### 6. Capacidade de Organização e Governança

Ferramentas para manter a casa organizada e segura.

* **Movimentação de Conteúdo:** Capacidade de mover painéis e bases entre projetos (ex: tirar da pasta "Rascunhos de IA" e mover para a pasta "Produção/Finanças").
* **Tagueamento e Certificação:** Capacidade de aplicar etiquetas (tags) de identificação (ex: `Gerado por IA`, `Em Teste`) e aplicar selos oficiais de aprovação ("Fonte de Dados Certificada").
* **Estruturação de Pastas:** Capacidade de criar novos projetos ou pastas organizacionais quando necessário.