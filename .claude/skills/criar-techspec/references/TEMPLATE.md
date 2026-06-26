# Especificação técnica

## Resumo executivo

[Fornecer uma visão técnica breve da abordagem da solução. Resumir as principais decisões de arquitetura e a estratégia de implementação em 1–2 parágrafos.]

## Arquitetura do sistema

### Visão dos componentes

[Descrição breve dos principais componentes e suas responsabilidades:

- Nomes dos componentes e funções principais **Certifique-se de listar cada componente novo ou modificado**
- Principais relacionamentos entre componentes
- Visão geral do fluxo de dados]

## Design de implementação

### Principais interfaces

[Definir as principais interfaces de serviço (≤20 linhas por exemplo):

```python
# Exemplo de definição de interface
class ServiceName:
    def method_name(self, input: InputType) -> OutputType:
        pass
```

]

### Modelos de dados

<critical>
**OBRIGATÓRIO — formatação visual e legível:**

- **NÃO** descrever contratos como tipos inline em bullet points (ex.: `location: { name, admin1, ... }`).
- **SEMPRE** documentar cada entidade/contrato em subseção própria (`#### \`NomeDoTipo\` — descrição`).
- **SEMPRE** incluir tabela de campos (Campo | Tipo | Obrigatório | Descrição) antes do JSON de exemplo.
- **SEMPRE** incluir bloco ` ```json ` formatado e indentado com valores realistas (não placeholders genéricos).
- Variantes/degradações (ex.: campo `null`) devem ter JSON separado + blockquote explicando o comportamento.
- Envelopes de erro: tabela Código | HTTP | Significado + exemplo JSON.
- Mapeamentos externos → contrato: tabela Origem | Destino.
- Parâmetros de upstream/config fixados: tabela API | Parâmetros principais.
- Campos ausentes no upstream normalizados para `null` — mencionar isso no parágrafo introdutório.
</critical>

Contratos JSON do backend — prontos para exibição na UI. [Completar contexto específico da feature. Campos ausentes no upstream são normalizados para `null`.]

#### `[NomeDoTipo]` — [descrição curta]

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `[campo]` | `[tipo]` | sim/não | [Descrição] |

```json
{
  "[campo]": "[valor realista]"
}
```

[Repetir o padrão acima para cada entidade/contrato principal: payload agregado, tipos de entrada, tipos de erro, etc.]

> **[Variante/degradação (se aplicável)]:** [Explicar quando ocorre e o impacto no payload.]

```json
{
  "[secao_afetada]": null
}
```

#### `[NomeDoErro]` — envelope de erro tipado

| Código | HTTP | Significado |
| --- | --- | --- |
| `[codigo]` | `[status]` | [Descrição] |

```json
{
  "error": {
    "code": "[codigo]",
    "message": "[mensagem em inglês ou PT-BR conforme padrão do projeto]"
  }
}
```

#### Mapeamento [Origem externa] → contrato

| Origem ([API/fonte]) | Destino (contrato) |
| --- | --- |
| `[campo_origem]` | `[campo_destino]` |

#### Parâmetros fixados no upstream (backend)

| API | Parâmetros principais |
| --- | --- |
| **[Nome da API]** | `[param1=valor]`, `[param2=valor]` |

[Se aplicável: esquemas de banco de dados — usar o mesmo padrão (subseção + tabela + exemplo JSON/SQL).]

### Endpoints da API

<critical>
**OBRIGATÓRIO — formatação visual e legível:**

- **NÃO** listar endpoints como bullet points compactos com tudo inline.
- **SEMPRE** começar com tabela de visão geral (Método | Rota | Descrição).
- **SEMPRE** documentar cada endpoint em subseção própria (`#### \`MÉTODO /rota\``).
- **SEMPRE** incluir, por endpoint: tabela de query params/body, tabela de respostas (Status | Corpo | Quando), blocos ` ```http ` com a requisição e blocos ` ```json ` com exemplos de resposta.
- Cobrir **todos** os cenários relevantes: sucesso, lista vazia, erro de validação, erro upstream, degradação parcial.
- Evitar JSON comprimido em uma linha — usar indentação ou referenciar o exemplo completo da seção Modelos de dados.
- Usar blockquote (`>`) para comportamentos não óbvios (ex.: "lista vazia não é erro HTTP").
- Separar endpoints com `---`.
</critical>

#### Visão geral

| Método | Rota | Descrição |
| --- | --- | --- |
| `[GET/POST/...]` | `[ /api/... ]` | [Descrição breve] |

---

#### `[MÉTODO] [ /api/rota ]`

[Descrição breve do propósito do endpoint.]

**Query params** _(ou **Body** para POST/PUT/PATCH)_

| Param | Tipo | Default | Regras |
| --- | --- | --- | --- |
| `[param]` | `[tipo]` | `[default ou —]` | [Validações e regras] |

**Respostas**

| Status | Corpo | Quando |
| --- | --- | --- |
| `[200]` | `[TipoResposta]` | [Condição de sucesso] |
| `[400]` | `[TipoErro]` | [Condição de erro de validação] |
| `[502]` | `[TipoErro]` | [Condição de falha upstream] |

**Exemplo — sucesso**

```http
[MÉTODO] [ /api/rota?param=valor ]
```

```json
{
  "[campo]": "[valor realista]"
}
```

**Exemplo — [cenário alternativo, ex.: nenhuma correspondência]**

```http
[MÉTODO] [ /api/rota?param=valor ]
```

```json
{
  "[corpo]": []
}
```

> [Nota sobre comportamento no frontend/cliente, se aplicável.]

**Exemplo — [cenário de erro]**

```http
[MÉTODO] [ /api/rota ]
```

```json
{
  "error": {
    "code": "[codigo]",
    "message": "[mensagem]"
  }
}
```

[Repetir o padrão acima para cada endpoint. Para payloads grandes já documentados em Modelos de dados, referenciar o exemplo JSON existente em vez de duplicar.]

---

## Pontos de integração

[Incluir apenas se a funcionalidade exigir integrações externas:

- Serviços ou APIs externos
- Requisitos de autenticação
- Abordagem de tratamento de erros]

## Abordagem de testes

### Testes unitários

[Descrever estratégia de testes unitários:

- Principais componentes a testar
- Requisitos de mocks (somente para serviços externos)
- Cenários de teste críticos]

### Testes de integração

[Se necessário, descrever testes de integração:

- Componentes a testar em conjunto
- Requisitos de dados de teste]

### Testes E2E

[Se necessário, descrever testes E2E:

- Testar o frontend junto com o backend **usando Playwright**]

## Sequenciamento do desenvolvimento

### Ordem de construção

[Definir sequência de implementação:

1. Primeiro componente/funcionalidade (por que primeiro)
2. Segundo componente/funcionalidade (dependências)
3. Componentes subsequentes
4. Integração e testes]

### Dependências técnicas

[Listar bloqueadores de dependências:

- Infraestrutura necessária
- Disponibilidade de serviços externos]

## Monitoramento e observabilidade

[Definir abordagem de monitoramento usando a infraestrutura existente:

- Métricas a expor (formato Prometheus)
- Principais logs e níveis de log
- Integração com dashboards Grafana existentes]

## Considerações técnicas

### Principais decisões

[Documentar decisões técnicas importantes:

- Escolha da abordagem e justificativa
- Trade-offs considerados
- Alternativas descartadas e por quê]

### Riscos conhecidos

[Identificar riscos técnicos:

- Desafios potenciais
- Abordagens de mitigação
- Áreas que precisam de pesquisa]

### Conformidade com skills

[Pesquisar as skills na pasta @.claude/skills que se encaixem e se apliquem a esta especificação técnica e listá-las abaixo:]

### Arquivos relevantes e dependentes

[Listar aqui os arquivos relevantes e dependentes]
