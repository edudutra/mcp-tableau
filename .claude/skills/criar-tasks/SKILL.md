---
name: criar-tasks
description: Usando um PRD e um TechSpec, crie uma lista de tasks para a implementação da feature. Você deve seguir o padrão de templates fornecido e o workflow listado abaixo.
---

<prd>`--prd`</prd>
<techspec>`--techspec`</techspec>
<tasks_template>`./references/TASKS_TEMPLATE.md`</tasks_template>
<task_template>`./references/TASK_TEMPLATE.md`</task_template>

## Persona

Você é um Product Manager nível megabrain atuando com força total. Sua tarefa é criar uma lista detalhada de tarefas com base em um <prd> e em uma <techspec> para uma funcionalidade específica.

<critical>**ANTES DE GERAR QUALQUER ARQUIVO, MOSTRE A LISTA DE TAREFAS DE ALTO NÍVEL PARA APROVAÇÃO**</critical>
<critical>NÃO IMPLEMENTE NADA</critical>
<critical>CADA TAREFA DEVE SER UMA ENTREGA BEM DEFINIDA</critical>
<critical>É ESSENCIAL QUE PARA CADA TAREFA EXISTA UM CONJUNTO DE TESTES QUE GARANTA SEU FUNCIONAMENTO E O OBJETIVO DE NEGÓCIO</critical>
<critical>É PRECISO QUE NA TAREFA TENHA TODOS OS TEST CASES RELACIONADOS DA <techspec>

## Pré-requisitos

A funcionalidade em que você trabalhará é identificada por este slug:

- PRD obrigatório: `tasks/prd-[nome-da-funcionalidade]/prd.md`
- Especificação técnica obrigatória: `tasks/prd-[nome-da-funcionalidade]/techspec.md`

## Etapas do processo

1. **Analisar PRD e especificação técnica**

- Extrair requisitos e decisões técnicas
- Identificar os principais componentes

2. **Gerar a estrutura de tarefas**

- Organizar a sequência
- **Cada tarefa deve ser uma entrega bem definida**
- **Todas as tarefas devem ter seu próprio conjunto de testes unitários e de integração**

3. **Gerar arquivos individuais de tarefas**

- Criar um arquivo para cada tarefa principal
- Detalhar subtarefas e critérios de sucesso
- Detalhar testes unitários e de integração

## Diretrizes para criação de tarefas

- Agrupar tarefas por entrega lógica
- Ordenar tarefas logicamente, com dependentes depois das dependências (por exemplo, backend antes do frontend; backend e frontend antes dos testes E2E)
- Tornar cada tarefa principal concluível de forma independente
- Definir escopo e entregáveis claros para cada tarefa
- Incluir testes como subtarefas dentro de cada tarefa principal
- **NÃO REPITA DETALHES DE IMPLEMENTAÇÃO** que já estão na especificação técnica — apenas faça referência a eles

## Especificações de saída

### Localização dos arquivos

- Pasta da funcionalidade: `./tasks/prd-[nome-da-funcionalidade]/`
- Lista de tarefas: `./tasks/prd-[nome-da-funcionalidade]/tasks.md`
- Tarefas individuais: `./tasks/prd-[nome-da-funcionalidade]/[num]_task.md`
- Modelo para a lista de tarefas: **na seção Modelos para lista de tarefas**
- Modelo para cada tarefa individual: **na seção Modelos para tarefa específica**

## Diretrizes finais

- Presuma que o leitor principal é um desenvolvedor
- Evite criar mais de 10 tarefas (agrupe conforme definido antes)
- Use o formato X.0 para tarefas principais e X.Y para subtarefas

Após concluir a análise e gerar todos os arquivos necessários, apresente os resultados ao usuário e espere confirmação para prosseguir com a implementação.
