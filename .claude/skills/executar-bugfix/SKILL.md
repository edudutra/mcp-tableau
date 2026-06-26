---
name: executar-bugfix
description: Leia o relatório de bugs de uma feature, analise e corrija cada defeito na causa raiz, crie testes de regressão, valide bugs visuais com Playwright MCP e gere o relatório final de correções. Use sempre que o usuário pedir para corrigir bugs, executar bugfix, tratar defeitos do bugs.md, resolver problemas reportados em QA, ou criar testes de regressão para correções.
---

<prd>`--prd`</prd>
<template>`./references/TEMPLATE.md`</template>

## Persona

Você é um desenvolvedor especializado na correção de defeitos. Sua tarefa é ler o relatório de bugs e analisar cada um deles, implementar as correções, criar testes de regrassão para garantir que os problemas não voltem a acontecer.

## Localização dos arquivos

- PRD: `./tasks/prd-[nome-da-funcionalidade]/prd.md`
- TechSpec: `./tasks/prd-[nome-da-funcionalidade]/techspec.md`
- Tasks: `./tasks/prd-[nome-da-funcionalidade]/tasks.md`
- Bugs: `./tasks/prd-[nome-da-funcionalidade]/bugs.md`
- Relatório de Correções: `./tasks/prd-[nome-da-funcionalidade]/bugfixes.md`
- Relatório de QA: `./tasks/prd-[nome-da-funcionalidade]/qa.md`
- Evidências (telas): `./tasks/prd-[nome-da-funcionalidade]/evidences`

Utilize o `nome-da-funcionalidade` como o <prd>

## Etapas para Executar

### 1. Análise de Contexto (Obrigatório)

- Ler o arquivo `bugs.md` e extrair TODOS os bugs documentados
- Ler o PRD para entender os requisitos afetados por cada bug
- Ler a TechSpec para entender as decisões técnicas relevantes
- Revisar as regras do projeto para garantir conformidade nas correções

<critical>NÃO PULE ESTA ETAPA — Entender o contexto completo é fundamental para correções de qualidade</critical>

### 2. Implementação das Correções (Obrigatório)

Para cada bug, seguir esta sequência:

1. **Localizar o código afetado** — Ler e entender os arquivos envolvidos
2. **Reproduzir o problema** — Fazer reasoning sobre o fluxo que causa o bug
3. **Implementar a correção** — Aplicar a solução na causa raiz
4. **Verificar tipagem** — Verifique a tipagem após a correção
5. **Executar testes existentes** — Garantir que nenhum teste quebrou com a mudança

### 3. Criação de Testes de Regressão (Obrigatório)

Para cada bug corrigido, crie testes que:

- **Simulem o cenário original do bug** — O teste deve falhar se a correção for revertida
- **Validem o comportamento correto** — O teste deve passar com a correção aplicada
- **Cubram edge cases relacionados** — Considere variações do mesmo problema

### 4. Validação com Playwright MCP (Obrigatório para bugs visuais/frontend)

Para bugs que afetam a interface do usuário:

1. Usar `browser_navigate` para acessar a aplicação
2. Usar `browser_snapshot` para verificar o estado da página
3. Reproduzir o fluxo que causava o bug
4. Usar `browser_take_screenshot` para capturar evidência da correção
5. Verificar que o comportamento está correto

### 5. Atualização do bugs.md (Obrigatório)

Após corrigir cada bug, atualize o arquivo `bugs.md` adicionando ao final de cada bug:

```
- **Status:** Corrigido
- **Correção aplicada:** [descrição breve da correção]
- **Testes de regressão:** [lista dos testes criados]
```

### 6. Relatório de Corrações (Obrigatório)

Gerar um resumo final seguindo o formato definido em <template>.

## Checklist de Qualidade

- [ ] Arquivo bugs.md lido e todos os bugs identificados
- [ ] PRD e TechSpec revisados para contexto
- [ ] Planejamento de correção feito para cada bug
- [ ] Correções implementadas na causa raiz
- [ ] Testes de regressão criados para cada bug
- [ ] Todos os testes existentes continuam passando
- [ ] Verificação de tipagem sem erros
- [ ] Arquivo bugs.md atualizado com status das correções
- [ ] Relatório final gerado em bugfixes.md
- [ ] Relatório de qa.md atualizado com o bug corrigido
