# Explicativo de Dashboards — EletroFrio ML

Guia de referência para todos os painéis do sistema de monitoramento preditivo.  
Cada secção explica o **propósito**, os **dados usados**, as **visualizações** e como **interpretar** o que aparece no ecrã.

---

## Índice

1. [Visão Geral (Página Principal)](#1-visão-geral-página-principal)
2. [Saúde da Frota](#2-saúde-da-frota)
3. [Mapa de Risco](#3-mapa-de-risco)
4. [Temperatura](#4-temperatura)
5. [Alarmes por Loja](#5-alarmes-por-loja)
6. [Ciclos de Degelo](#6-ciclos-de-degelo)
7. [Pressão](#7-pressão)
8. [Chamados](#8-chamados)
9. [Impacto Financeiro](#9-impacto-financeiro)
10. [Qualidade do Modelo](#10-qualidade-do-modelo)

---

## 1. Visão Geral (Página Principal)

**Rota:** `/`  
**Endpoint de dados:** `/api/alarmes`, `/api/unidades`, `/api/stats`

### O que é

A página de entrada do sistema. Funciona como um **painel executivo de alto nível** — dá uma leitura rápida do estado geral da frota sem entrar em detalhes de dispositivos individuais.

### O que mostra

**KPI Cards (linha de topo):**

| Card | O que mede | Quando preocupar |
|---|---|---|
| Total de Alarmes | Nº de alarmes activos no momento | — (referência) |
| Críticos (C) | Alarmes de nível máximo de urgência | Qualquer valor > 0 |
| Alta (A) | Alarmes de alta urgência | Tendência crescente |
| Média (M) | Alarmes de urgência moderada | — (monitorar) |
| Baixa (B) | Alarmes informativos de baixo impacto | — |
| Sem Tratativa | Alarmes que ainda não tiveram resposta | Idealmente = 0 |

**Gráfico "Alarmes por Criticidade":** rosca ou barras mostrando a proporção de cada nível de urgência. Um gráfico dominado por laranja (Alta) ou vermelho (Crítico) indica necessidade de intervenção imediata.

**Tabela "Top Lojas com Mais Alarmes":** ranking das lojas com maior volume de ocorrências, destacando quantos são críticos e quantos estão sem tratativa. Serve para priorizar visitas técnicas por região.

**Tabela "Alarmes Ativos":** listagem completa dos alarmes com:
- Criticidade (badge colorido)
- Loja e dispositivo (tag do compressor)
- Score de risco ML (0.0 – 1.0, calculado pelo Random Forest)
- Indicador de anomalia (OneClass SVM)
- Temperatura actual vs setpoint
- Status de tratativa
- Botão "Abrir Chamado" para escalar directamente

### Como interpretar

- **Score de risco > 0.75 em vermelho** → dispositivo candidato imediato a chamado técnico
- **Anomalia = Sim** → comportamento fora do padrão histórico, mesmo que não haja alarme crítico activo
- **Sem Tratativa elevado** → equipa de campo não está a responder aos alertas, processo operacional a falhar

---

## 2. Saúde da Frota

**Rota:** `/dashboards/saude`  
**Endpoint de dados:** `/api/dashboard/saude`

### O que é

Visão **consolidada da frota inteira** num único painel. Enquanto a Visão Geral mostra alarmes, este dashboard mostra a **distribuição de saúde** dos compressores combinando criticidade de alarme com score ML.

### O que mostra

**KPI Cards:**

| Card | Definição |
|---|---|
| Total Devices | Nº de compressores com dados disponíveis |
| Críticos | Devices com alarme de nível C activo |
| Atenção (A+M) | Devices com alarme A ou M — atenção moderada |
| Normal (B+I) | Devices sem alarmes urgentes |
| Score ML Médio (%) | Média do risk_score de todos os devices × 100 |

**Gráfico "Distribuição da Frota" (rosca):** proporção de dispositivos por nível de criticidade. O ideal é ter a fatia azul/verde (Normal) dominando > 70%. Se o segmento Crítico (vermelho) ultrapassar 10% da frota, é sinal de problema sistémico.

**Gráfico "Score Médio por Loja" (barras + linha):** barras cinza = score ML médio dos compressores por loja. Linha vermelha = nº de devices críticos nessa loja (eixo direito). Lojas com barra alta E linha vermelha > 0 são prioridade máxima: o ML confirma risco elevado com alarmes activos.

### Como interpretar

- **Score ML Médio > 50%** com vários Críticos → frota em degradação sistémica, plano de manutenção preventiva necessário
- **Loja com score alto mas zero críticos** → o modelo detectou degradação antes dos alarmes — boa candidata a visita preventiva
- **Loja com vários críticos mas score baixo** → alarmes podem ser de configuração (setpoints errados) e não de falha mecânica real

---

## 3. Mapa de Risco

**Rota:** `/dashboards/risco`  
**Endpoints de dados:** `/api/dashboard/risco`, `/api/monitoramento/scores/<id>`

### O que é

O painel mais analítico do sistema. Classifica **cada compressor individualmente** por um score composto que combina múltiplas fontes de risco, e estima tendência ao longo do tempo.

### Fórmula do Score Composto

```
Score Final = RF_score     × 40%
            + Criticidade  × 25%
            + Degelo       × 20%
            + Erro de Temp × 15%
```

| Componente | O que mede | Peso |
|---|---|---|
| RF_score | Probabilidade de falha (Random Forest) | 40% |
| Criticidade | Nível do alarme activo (C=1.0, A=0.7, M=0.4, B=0.2, I=0.1) | 25% |
| Degelo | % do tempo em ciclo de degelo (> 30% = anómalo) | 20% |
| Erro de Temp | Desvio da temperatura média em relação ao setpoint | 15% |

### O que mostra

**Tabela de risco por device:**
- Score composto com barra de cor (verde < 40%, amarelo 40–70%, vermelho > 70%)
- Sparkline de tendência dos últimos scores históricos (linha de mini-gráfico)
- Estimativa de "dias até falha" baseada em regressão linear sobre o histórico de scores
- Criticidade actual, loja, tag do dispositivo

**Filtros disponíveis:** criticidade (C/A/M/B/I), loja, ordenação (por score, por tendência, por loja)

### Como interpretar

- **Score > 70% + sparkline ascendente** → intervenção urgente (dispositivo a degradar rapidamente)
- **Score > 70% + sparkline estável** → risco elevado mas estável, monitorar
- **Score < 40% + sparkline descendente** → recuperação após manutenção (bom sinal)
- **"Dias até falha" < 7** → abertura de chamado recomendada imediatamente
- **Anomalia OCC SVM = Sim** mesmo com score moderado → comportamento atípico, investigar

---

## 4. Temperatura

**Rota:** `/dashboards/temperatura`  
**Endpoints de dados:** `/api/dashboard/temperatura/devices`, `/api/dashboard/temperatura/<dispositivo_id>`

### O que é

Análise detalhada da **série temporal de temperatura** de um compressor específico. Permite ver o comportamento ao longo das últimas 24 horas com o setpoint como referência.

### O que mostra

**Selector de dispositivo:** dropdown ou lista de compressores com telemetria disponível. Ao seleccionar, o gráfico actualiza.

**Gráfico de linha (Chart.js):**
- Linha azul = temperatura real do compressor
- Linha tracejada laranja = setpoint (temperatura alvo configurada)
- Banda de tolerância ±2°C sombreada em torno do setpoint
- Marcadores vermelhos nos pontos onde anomalia foi detectada pelo modelo

**KPIs do device seleccionado:**
- Temperatura média (últimas 24h)
- Temperatura máxima registada
- % do tempo acima do setpoint
- Nº de anomalias detectadas

### Como interpretar

- **Temperatura consistentemente acima da banda** → compressor com dificuldade de atingir o setpoint (possível falta de gás, problema de compressão ou sobrecarga)
- **Picos bruscos isolados** → eventos de degelo ou abertura de porta (normais se ocasionais)
- **Oscilações de alta frequência** → comportamento de liga-desliga (on/off cycling) excessivo — desgaste acelerado
- **Temperatura muito abaixo do setpoint** → sensor defeituoso ou problema de calibração
- **Muitos marcadores de anomalia seguidos** → sequência de comportamento anómalo, risco real

---

## 5. Alarmes por Loja

**Rota:** `/dashboards/alarmes-loja`  
**Endpoint de dados:** `/api/dashboard/alarmes-loja`

### O que é

Visão **geográfica/organizacional** dos alarmes — em vez de ver por device, agrupa por loja. Útil para o gestor de operações perceber quais unidades têm mais problemas e priorizar deslocações de equipa.

### O que mostra

**Gráfico de barras agrupadas por loja:** cada barra tem segmentos coloridos por criticidade (C=vermelho, A=laranja, M=amarelo, B=azul, I=cinza). Permite comparar volume total e composição de urgência entre lojas.

**Gráfico de Pareto:** barras ordenadas da loja com mais alarmes para a com menos, com linha acumulativa. O "princípio 80/20" aplicado: normalmente 20% das lojas geram 80% dos problemas.

**Tabela de detalhes por loja:**
- Nome da loja
- Total de alarmes
- Breakdown por criticidade
- Nº de devices sem tratativa

### Como interpretar

- **Loja no topo do Pareto com muitos Críticos** → visita prioritária imediata
- **Loja com muitos alarmes mas todos de nível B/I** → pode ser configuração de setpoint, não falha mecânica
- **Loja nova no topo do ranking** (não estava antes) → mudança repentina, investigar causa
- **"Sem Tratativa" > 50% numa loja** → equipa local não está a tratar alarmes, problema de processo

---

## 6. Ciclos de Degelo

**Rota:** `/dashboards/degelo`  
**Endpoint de dados:** `/api/dashboard/degelo`

### O que é

Análise específica dos **ciclos de degelo** dos compressores. O degelo é um processo normal em que o compressor aquece brevemente para remover a camada de gelo que se forma no evaporador. No entanto, ciclos excessivos ou muito longos indicam problema.

### Conceito técnico

Os compressores de refrigeração formam gelo no evaporador durante a operação normal. O degelo é controlado (automático ou por timer) para remover esse gelo. Um sistema saudável faz degelo de forma periódica e breve. Problemas surgem quando:
- O compressor fica muito tempo em degelo (evaporador com gelo excessivo por falha)
- Os ciclos são muito frequentes (sistema a tentar compensar temperatura elevada)

### O que mostra

**Gráfico de barras horizontais (Plotly):** um por device, mostrando a % do tempo total em degelo. Linha de threshold a 30% marcada em vermelho.

**KPIs:**
- % de devices acima do threshold de 30%
- Duração média dos ciclos de degelo por device
- Nº médio de ciclos por dia

### Como interpretar

- **% de degelo > 30%** → sistema anómalo, evaporador provavelmente com gelo excessivo ou sensor de degelo defeituoso
- **Ciclos muito curtos e frequentes** → o sistema está a entrar e sair de degelo sem conseguir resolver o problema de gelo
- **Device com 0% de degelo** → sensor não está a reportar eventos de degelo — possível falha de sensor ou configuração
- **Degelo normalizado após manutenção** → evidência de que a intervenção resolveu o problema

---

## 7. Pressão

**Rota:** `/dashboards/pressao`  
**Endpoint de dados:** `/api/dashboard/pressao`

### O que é

Monitoramento das **pressões de sucção e condensação** dos compressores. A pressão é um indicador directo do estado do ciclo de refrigeração e da quantidade de gás refrigerante no sistema.

### Conceito técnico

O ciclo de refrigeração tem dois lados de pressão:
- **Sucção (baixa pressão):** antes do compressor, onde o refrigerante gasoso é aspirado
- **Condensação (alta pressão):** após o compressor, onde o refrigerante é comprimido e liquefaz

A **razão de pressão** (condensação / sucção) indica a eficiência do compressor. Valores fora do intervalo normal indicam problemas de carga de refrigerante, válvulas ou compressor.

### O que mostra

**Lista de devices com pressões actuais:**
- Pressão de sucção (bar) — valor actual
- Pressão de condensação (bar) — valor actual
- Razão de pressão calculada
- Indicador de status (normal / alerta / crítico)

**Série temporal de pressão:** gráfico de linha para o device seleccionado mostrando evolução da pressão ao longo do tempo.

### Como interpretar

- **Pressão de sucção muito baixa** → pouco refrigerante (fuga de gás), evaporador com gelo excessivo ou expansor bloqueado
- **Pressão de condensação muito alta** → condensador sujo, ventilação insuficiente ou excesso de refrigerante
- **Razão de pressão < 2** ou **> 6** → eficiência do compressor comprometida
- **Pressão de sucção negativa (vácuo)** → fuga grave, compressor aspirando ar (perigoso para o sistema)

---

## 8. Chamados

**Rota:** `/dashboards/chamados`  
**Endpoint de dados:** `/api/dashboard/chamados` (PostgreSQL)

### O que é

Gestão do **histórico de chamados técnicos** abertos pelo sistema (automaticamente ou manualmente via dashboard). Registo persistente em PostgreSQL — sobrevive a reboots e redeploys.

### O que mostra

**KPI Cards:**

| Card | Definição |
|---|---|
| Total de Chamados | Todos os chamados registados (histórico completo) |
| Hoje | Chamados abertos no dia actual |
| Abertos | Chamados ainda por resolver (status = 'aberto') |
| Resolvidos | Chamados marcados como fechados |

**Gráfico "Chamados por Hora do Dia" (barras):** distribuição dos chamados pelas 24 horas. Revela os períodos do dia com mais ocorrências (ex: picos nocturnos ou em horário de entrega de mercadoria).

**Tabela de chamados:**
- Data/hora de criação
- Tag do dispositivo e ID
- Loja
- Motivo (texto truncado com tooltip)
- Status (badge "Aberto" / "Fechado")
- Botão "Resolver" (para chamados abertos)

### Como interpretar

- **Muitos chamados abertos acumulados** → equipa técnica sem capacidade de resposta ou problema sistémico na frota
- **MTTR (tempo médio de resolução)** elevado → chamados demoram muito a ser fechados após abertura
- **Picos em horários específicos** → correlacionar com eventos operacionais (recepção de mercadoria, abertura de loja, etc.)
- **Mesmo device com chamados repetidos** → reincidência, possível causa raiz não resolvida (ver dashboard Mapa de Risco / endpoint reincidência)

---

## 9. Impacto Financeiro

**Rota:** `/dashboards/financeiro`  
**Endpoint de dados:** `/api/dashboard/financeiro`

### O que é

Estimativa do **impacto económico** dos problemas detectados. Traduz os dados técnicos em linguagem de negócio: quanto custa (ou pode custar) cada falha em termos de energia, mercadoria comprometida e tempo de paragem.

### Metodologia de cálculo

O impacto é estimado combinando:

1. **Score de risco × tarifa de energia:** compressores com risco elevado tendem a consumir mais energia por trabalhar fora do ponto óptimo
2. **Criticidade × custo estimado de downtime:** alarmes críticos são associados a probabilidade de paragem × valor médio de mercadoria perecível por loja
3. **Tempo de degelo excessivo × eficiência perdida:** % de degelo acima do normal × tarifa de energia × horas do período

> **Nota:** os valores são estimativas baseadas em modelos de referência do sector. Não são facturação real — servem para priorização relativa entre lojas.

### O que mostra

**Ranking de lojas por impacto estimado:** barras horizontais ordenadas da loja com maior impacto potencial para a menor.

**KPIs:**
- Impacto total estimado da frota (R$)
- Loja de maior risco financeiro
- Nº de devices com impacto > threshold definido

**Breakdown por componente:** quanto do impacto vem de energia vs. risco de mercadoria vs. degelo ineficiente.

### Como interpretar

- **Loja no topo do ranking financeiro + muitos críticos** → caso de negócio claro para intervenção preventiva imediata
- **Loja com impacto alto mas sem alarmes críticos** → o modelo ML está a detectar degradação silenciosa com custo energético elevado
- **Impacto total da frota a crescer semana a semana** → degradação sistémica sem manutenção adequada

---

## 10. Qualidade do Modelo

**Rota:** `/dashboards/modelo`  
**Endpoint de dados:** `/api/dashboard/modelo`

### O que é

Painel de **transparência e auditoria do ML**. Expõe as métricas de qualidade dos modelos treinados, quais features são mais importantes e a distribuição dos scores gerados. Essencial para validar se o sistema está a fazer previsões fiáveis.

### Modelos exibidos

| Modelo | Tipo | O que faz |
|---|---|---|
| Random Forest | Classificação supervisionada | Gera `risk_score` ∈ [0.0, 1.0] — probabilidade de falha |
| OneClass SVM | Detecção de anomalia (não supervisionado) | Detecta comportamento fora do padrão histórico (normal vs. anómalo) |

### O que mostra

**Metadados dos modelos:**
- Data do último treino
- Nº de devices usados no treino
- Nº de features utilizadas
- Métricas de avaliação (Stratified 5-Fold CV): accuracy, precision, recall, F1
- Parâmetros do modelo (nº de árvores, profundidade máxima, etc.)

**Gráfico "Feature Importance" (barras horizontais):** top 15 features mais importantes para as previsões do Random Forest. Mostra quais sinais de telemetria têm mais peso na decisão do modelo.

**Distribuição de scores:** histograma dos `risk_score` actuais de todos os devices. Uma distribuição saudável tem a maioria dos devices com score baixo (< 0.4) e apenas uma minoria com score alto.

### Como interpretar a Feature Importance

| Feature com alto peso | O que significa para o negócio |
|---|---|
| `temp_mean` (temperatura média) | Temperatura é o principal preditor — esperado |
| `temp_std` (variabilidade de temperatura) | Instabilidade térmica é sinal de problema |
| `degelo_pct` (% de degelo) | Degelo excessivo é forte preditor de falha |
| `temp_error_mean` (erro vs setpoint) | Incapacidade de atingir o setpoint indica degradação |
| `onoff_cycles` (ciclos liga/desliga) | Muitos ciclos = desgaste acelerado |

### Como interpretar as métricas de avaliação

| Métrica | Definição | Valor ideal |
|---|---|---|
| Accuracy | % de previsões correctas no total | > 80% |
| Precision | Dos alertas emitidos, quantos eram reais | > 70% (evita falsos alarmes) |
| **Recall** | Das falhas reais, quantas foram detectadas | **> 80%** (crítico — falha não detectada é perigosa) |
| F1 | Equilíbrio entre precision e recall | > 75% |

> **O Recall é a métrica mais importante neste domínio.** Uma falha não detectada (falso negativo) pode comprometer produtos perecíveis e gerar perdas significativas. É preferível ter alguns falsos alarmes (precision baixa) do que deixar passar falhas reais (recall baixo).

### Quando re-treinar o modelo

- F1 < 0.65 no CV
- Nº de devices no treino aumentou > 20% desde o último treino
- Features importantes mudaram significativamente (indica mudança no perfil dos dados)
- Após campanha de feedback intensiva dos técnicos (muitos labels novos em `feedback.parquet`)

O re-treino pode ser disparado manualmente via `POST /api/admin/treinar` ou ocorre automaticamente quando novos devices são detectados pelo scheduler de 6 horas.

---

## Resumo Rápido — Qual Dashboard Usar Para Quê

| Objetivo | Dashboard |
|---|---|
| Ver o estado geral da frota agora | Visão Geral / Saúde da Frota |
| Priorizar qual device chamar primeiro | Mapa de Risco |
| Investigar comportamento de temperatura de um device | Temperatura |
| Priorizar qual loja visitar | Alarmes por Loja / Impacto Financeiro |
| Suspeita de problema de gelo/degelo | Ciclos de Degelo |
| Suspeita de fuga de gás ou problema de compressão | Pressão |
| Gerir tickets abertos e histórico de intervenções | Chamados |
| Verificar se o ML está a funcionar bem | Qualidade do Modelo |

---

*Documentação gerada em 07/06/2026. Para detalhes técnicos de implementação, ver [DOCUMENTACAO.md](DOCUMENTACAO.md).*
