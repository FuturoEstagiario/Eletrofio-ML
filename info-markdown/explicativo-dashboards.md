# Explicativo de Dashboards — EletroFrio ML

Guia de referência para todos os painéis do sistema de monitoramento preditivo.  
Cada secção explica o **propósito**, os **dados usados**, as **visualizações** e como **interpretar** o que aparece no ecrã, incluindo de onde vem cada valor mostrado.

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

### Origem dos dados e cálculo

| Dado exibido | Fonte | Campo |
|---|---|---|
| Totais de alarmes por criticidade | `alarmes.parquet` (cache `alarmes_raw`) | campo `criticidade` de cada registo |
| Nome da loja | `alarmes.parquet` | campo `lojaNm` |
| "Sem Tratativa" | `alarmes.parquet` | `eventoDhCad is None` — campo de data de resposta vazio = sem atendimento |
| risk_score na tabela | `tele_features.parquet` via OCC SVM | `sigmoid(decision_function(X))` com 36 features |
| Anomalia (Sim/Não) | `tele_features.parquet` via OCC SVM | `predict_raw(X) == -1` |
| Temperatura actual | `tele_features.parquet` | campo `temp_mean` (média do período) |

**Como os KPI cards são calculados:** contagem simples dos registos em `alarmes_raw`. "Sem Tratativa" conta os registos onde o campo `eventoDhCad` (data de cadastro do evento de resposta ao alarme) está ausente. Os dados são servidos a partir do cache em memória carregado de `alarmes.parquet` — não há chamada à API externa em cada pedido de página.

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

### Origem dos dados e cálculo

Chama `saude_frota(alarmes_raw, tele_features, modelos)` em `src/dashboard_service.py`, que por sua vez chama `risco_tabela()` para obter a lista de devices com scores.

| Indicador | Cálculo |
|---|---|
| n_critico | `count` de devices onde `criticidade == "C"` |
| n_atencao | `count` de devices onde `criticidade in ["A", "M"]` |
| n_normal | `count` de devices onde `criticidade in ["B", "I"]` |
| % de cada grupo | `n / total × 100` |
| Score ML Médio (%) | `média(risk_score) × 100` — risk_score vem do OCC SVM (ver Mapa de Risco) |
| Score médio por loja | `média(risk_scores dos devices daquela loja) × 100` |
| Devices críticos por loja | `count(criticidade == "C" por loja)` |

**Quem aparece:** só devices que têm registo simultâneo em **ambos** `alarmes.parquet` (alarme activo) e `tele_features.parquet` (dados de telemetria). Devices sem telemetria não entram no score médio.

---

## 3. Mapa de Risco

**Rota:** `/dashboards/risco`  
**Endpoints de dados:** `/api/dashboard/risco`, `/api/monitoramento/scores/<id>`

### O que é

O painel mais analítico do sistema. Classifica **cada compressor individualmente** por um score composto que combina múltiplas fontes de risco, e estima tendência ao longo do tempo.

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

### Origem dos dados e cálculo

**Fontes:** `alarmes.parquet` (criticidade, loja, nome do device) + `tele_features.parquet` (36 features de temperatura, degelo, pressão).

**Como o risk_score é calculado** (código em `src/dashboard_service.py`, função `risco_tabela()`):

Para cada device que aparece em ambas as fontes:

**Passo 1 — tentativa com RF (falha silenciosamente):**  
O código tenta usar 6 features hardcoded (`temp_mean`, `temp_max`, `temp_min`, `temp_amplitude`, `temp_std`, `temp_taxa_variacao_media`). Como o RF foi treinado com **36 features**, a chamada falha com erro de dimensão. O erro é capturado pelo `except Exception` e `risk_score` fica `None`.

**Passo 2 — fallback: OCC SVM (36 features):**  
Usa os 36 nomes armazenados em `feature_cols.pkl`. Para cada feature, lê `feats.get(c, 0.0)` do parquet. Aplica `decision_function(X)` (que escala internamente com o `scaler.pkl`) e converte com sigmoid:

```
risk_score = 1 / (1 + exp(−decision_score))
```

> **Nota sobre a interpretação do OCC SVM:** o `decision_function` retorna valores **positivos** para dados **dentro** do padrão normal e **negativos** para **anomalias**. Pelo sigmoid, isso resulta em `risk_score > 0.5` para comportamento normal e `risk_score < 0.5` para anomalias — o inverso do que seria intuitivo. O indicador correto de "anomalia detectada" é `predict_raw(X) == -1`, não o valor do risk_score em si.

> **Sobre a fórmula composta** mostrada na interface (`RF×40% + Criticidade×25% + Degelo×20% + Erro Temp×15%`): é um modelo **conceitual** do que idealmente o score combinaria — **não está implementada no código actual**. O valor exibido é sempre o sigmoid do OCC SVM conforme descrito acima.

**Sparklines e "dias até falha":** calculados a partir do histórico de scores em `scores_historico` no PostgreSQL (se disponível) ou do histórico em memória da sessão actual. A regressão linear é feita sobre os últimos N scores para projectar quando o score atingiria 1.0.

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

### Origem dos dados e cálculo

**Fonte:** `tele_series.parquet` — séries temporais brutas por device (cada linha = um intervalo de 5 minutos).

Chama `temperatura_series(dispositivo_id, tele_series)` em `src/dashboard_service.py`.

| Elemento visual | Cálculo |
|---|---|
| Linha azul (temperatura real) | Array `temp` da série temporal do device |
| Linha tracejada laranja (setpoint) | Array `setpoint`; se ausente, preenchido com `nanmean` do próprio array |
| Banda de tolerância | `setpoint + 2` e `setpoint − 2` ponto a ponto sobre o array |
| Marcadores de anomalia (pontos vermelhos) | Regra simples: `1 if temp[i] > setpoint[i] + 2 else 0` — sem ML |
| % acima do setpoint | `mean(temp > setpoint) × 100` |
| Temperatura média | `np.mean(temp_array)` |
| Temperatura máxima | `np.max(temp_array)` |
| Temperatura mínima | `np.min(temp_array)` |
| Desvio padrão | `np.std(temp_array)` |

**Importante:** os marcadores de anomalia neste dashboard são calculados por regra simples (temperatura acima da banda ±2°C), **não pelo modelo ML**. O OCC SVM só é invocado no endpoint `/api/monitoramento/scores/<id>` (análise individual de device).

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

### Origem dos dados e cálculo

**Fonte:** `alarmes.parquet` (cache `alarmes_raw`) — exclusivamente. Nenhum dado de telemetria ou ML é usado neste dashboard.

Chama `alarmes_por_loja(alarmes_raw)` em `src/dashboard_service.py`. Percorre todos os registos e agrupa por campo `lojaNm`.

| Coluna | Cálculo |
|---|---|
| Total | `count` de registos de alarme por loja |
| C / A / M / B / I | `count` de registos com aquela `criticidade` dentro da loja |
| Sem Tratativa | `count` de registos onde `eventoDhCad is None` |

**Top 15 lojas:** ordenadas por total de alarmes decrescente, truncadas em 15.  
**Gráfico de Pareto:** barras = contagem por loja (ordenada desc), linha = percentual acumulado sobre o total de alarmes.

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

### Origem dos dados e cálculo

**Fontes:** `tele_features.parquet` (features pré-calculadas por device) + `alarmes.parquet` (para nome e loja).

Chama `degelo_analysis(tele_features, alarmes_raw)` em `src/dashboard_service.py`.

| Campo exibido | Feature de origem | Como foi calculada |
|---|---|---|
| % de tempo em degelo | `degelo_fracao × 100` | Fracção dos intervalos de 5 min com status de degelo activo |
| Nº de ciclos | `degelo_num_ciclos` | Contagem de transições ligado→desligado no campo de degelo |
| Duração média (min) | `degelo_duracao_media × 5` | Média de intervalos por ciclo; ×5 porque cada intervalo = 5 minutos |
| Alerta (destaque vermelho) | `degelo_fracao > 0.30` | Threshold fixo de 30% |

**Origem das features:** `degelo_fracao`, `degelo_num_ciclos` e `degelo_duracao_media` são calculadas em `src/features.py` (função `processar_dispositivo`) sobre a série temporal bruta, e persistidas em `tele_features.parquet` pelo script `scripts/coletar_tele.py`. Não são calculadas em tempo real pelo dashboard.

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

### Origem dos dados e cálculo

**Lista de devices** — `pressao_devices(tele_features)` em `src/dashboard_service.py`:

| Campo | Feature de origem | Cálculo |
|---|---|---|
| Pressão de sucção (bar) | `pressao_succao_mean` | Média da série temporal de sucção, calculada em `src/features.py` |
| Pressão de condensação (bar) | `pressao_cond_mean` | Média da série temporal de condensação |
| Razão de pressão | — | `pressao_cond_mean / pressao_succao_mean` calculado on-the-fly |
| Superaquecimento (°C) | `superaquecimento_mean` | Média do diferencial Tcondensação − Tsaturação |

**Série temporal** — `pressao_series(dispositivo_id, tele_series)`: lê arrays `pressao_succao`, `pressao_cond`, `superaquecimento` e `labels` directamente de `tele_series.parquet` para o device seleccionado.

**Nota:** se `pressao_succao_mean` for `None` para um device (sensor não presente ou não reportado pela API), o device **não aparece** na lista de pressão. Este dashboard só mostra devices com sensores de pressão activos.

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

### Origem dos dados e cálculo

**Fonte primária:** PostgreSQL (tabela `chamados`) — persistência total entre sessões e redeploys.  
**Fallback:** `_cache["chamados_log"]` em memória — perdido ao reiniciar a aplicação.

Campos armazenados por chamado: `dispositivo_id`, `dispositivo_nome`, `loja`, `motivo` (texto gerado pelo OCC SVM via `gerar_motivo()` ou preenchido manualmente), `status` ("aberto"/"fechado"), `timestamp`.

| KPI | Cálculo |
|---|---|
| Total | `COUNT(*)` na tabela `chamados` |
| Hoje | `COUNT(*) WHERE DATE(timestamp) = CURRENT_DATE` |
| Abertos | `COUNT(*) WHERE status = 'aberto'` |
| Resolvidos | `COUNT(*) WHERE status = 'fechado'` |

**Gráfico por hora:** `EXTRACT(HOUR FROM timestamp)` agrupado, contando chamados por hora do dia (0–23).

**Abertura automática:** o scheduler de 6h invoca `avaliar_e_abrir_chamados()` (em `src/dev/chamado_service.py`), que abre chamados para devices com `risk_score` acima do threshold configurado. O `motivo` é gerado por `OneClassSVMModel.gerar_motivo()` baseado nos valores das features de temperatura e degelo do device.

---

## 9. Impacto Financeiro

**Rota:** `/dashboards/financeiro`  
**Endpoint de dados:** `/api/dashboard/financeiro`

### O que é

Estimativa do **impacto económico** dos problemas detectados. Traduz os dados técnicos em linguagem de negócio: quanto custa (ou pode custar) cada falha em termos de energia, mercadoria comprometida e tempo de paragem.

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

### Origem dos dados e cálculo

Os valores financeiros **não provêm de nenhum sistema contábil ou ERP da Eletrofrio**. São estimativas calculadas a partir de constantes hardcoded no código combinadas com o `risk_score` do modelo ML.

**Fonte dos dados:** `alarmes.parquet` + `tele_features.parquet`, processados primeiro por `risco_tabela()` (obtém criticidade e risk_score por device) e depois por `financeiro_impacto()` em `src/dashboard_service.py`.

---

#### Constantes hardcoded (linhas 338–339 de `src/dashboard_service.py`)

| Constante | Valor | Representa |
|---|---|---|
| `CUSTO_HORA["C"]` | R$ 3.500/h | Estimativa de custo de downtime para alarme Crítico |
| `CUSTO_HORA["A"]` | R$ 1.500/h | Estimativa para alarme de Alta prioridade |
| `CUSTO_HORA["M"]` | R$ 800/h | Estimativa para alarme Médio |
| `CUSTO_HORA["B"]` | R$ 300/h | Estimativa para alarme Baixo |
| `CUSTO_HORA["I"]` | R$ 80/h | Estimativa para alarme Informativo |
| `CUSTO_INTERVENCAO` | R$ 450 | Custo fixo estimado de um chamado técnico |

Estes valores são **estimativas de referência do setor de refrigeração comercial** — representam o custo médio estimado de perda de mercadoria perecível, energia desperdiçada e paragem operacional por hora de compressor em falha, por nível de criticidade. **Podem e devem ser ajustados no código** para reflectir os valores reais da Eletrofrio.

---

#### Fórmulas aplicadas por device

```
risk_score        → sigmoid do OCC SVM, valor entre 0.0 e 1.0
custo_hora        → CUSTO_HORA[criticidade]   (tabela acima)

exposicao_hora    = custo_hora × risk_score            (R$/h)
exposicao_diaria  = exposicao_hora × 24               (R$/dia)
exposicao_semanal = exposicao_diaria × 7              (R$/semana)
roi               = exposicao_diaria / 450             (vezes que a intervenção se paga)
economia_diaria   = exposicao_diaria − 450             (ganho líquido ao intervir hoje)
```

**Lógica:** o `risk_score` funciona como um **factor de probabilidade**. Um device com criticidade A (R$ 1.500/h de custo de downtime) mas risk_score 0.20 contribui apenas com R$ 300/h de exposição. Um device com criticidade M (R$ 800/h) mas risk_score 0.95 contribui com R$ 760/h — mais do que o anterior, apesar da criticidade menor.

---

#### Exemplo concreto

**Device com criticidade "A" e `risk_score = 0.80`:**
```
exposicao_hora    = 1.500 × 0.80 = R$ 1.200/h
exposicao_diaria  = 1.200 × 24  = R$ 28.800/dia
roi               = 28.800 / 450 = 64×   → categoria "Urgente" (roi ≥ 50)
economia_diaria   = 28.800 − 450 = R$ 28.350  (ganho líquido se intervir hoje)
```

**Device com criticidade "M" e `risk_score = 0.30`:**
```
exposicao_hora    = 800 × 0.30 = R$ 240/h
exposicao_diaria  = 240 × 24  = R$ 5.760/dia
roi               = 5.760 / 450 = 12.8×  → categoria "Recomendado" (10 ≤ roi < 50)
economia_diaria   = 5.760 − 450 = R$ 5.310
```

---

#### Categorias de recomendação

| roi calculado | Categoria | Significado |
|---|---|---|
| ≥ 50 | Urgente | A intervenção (R$450) paga-se 50× por dia — intervir imediatamente |
| ≥ 10 | Recomendado | Intervenção com retorno claro — agendar com prioridade |
| ≥ 2 | Monitorar | Retorno positivo mas baixo — monitorar de perto |
| < 2 | Normal | Custo de intervenção não justificado pelos dados actuais |

---

#### Totais da frota

| KPI exibido | Cálculo |
|---|---|
| Exposição diária total (R$) | Soma de `exposicao_diaria` de todos os devices |
| Exposição semanal total (R$) | `exposicao_diaria_total × 7` |
| Economia potencial diária (R$) | Soma das `economia_diaria > 0` dos devices "Urgente" e "Recomendado" |
| Custo total de intervenção (R$) | `count(Urgente + Recomendado) × 450` |
| ROI médio da frota | Média dos `roi` de todos os devices com `roi > 0` |
| Ranking por loja | Soma das `exposicao_diaria` dos devices agrupados por loja, ordem decrescente |

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

### Origem dos dados e cálculo

**Feature Importance:**

| Dado | Origem | Cálculo |
|---|---|---|
| Importâncias | `rf.model.feature_importances_` | Atributo do `RandomForestClassifier` — Gini impurity reduction média |
| Nomes das features | `ocsvm.feature_cols` (de `feature_cols.pkl`) | Lista dos 36 nomes em ordem; se ausente, mostra "feat_0", "feat_1", etc. |
| Top 15 | — | Ordenado por importância desc, truncado em 15 |

**Metadados do Random Forest:**
- `n_estimators = 200` — fixo no código de treino (`busca_hiperpar=False`)
- `n_features_in_ = 36` — lido do modelo carregado
- Métricas (accuracy, precision, recall, F1): calculadas durante o treino em `scripts/treinar_modelos.py` via Stratified 5-Fold CV — **não são recalculadas em tempo real** pelo dashboard, são estáticas do momento do treino

**Dados do treino actual:**
- 25 devices totais (de `tele_features.parquet`)
- Labels: criticidade C ou A → `anomalo=1` (18 devices); M, B ou I → `anomalo=0` (7 devices)
- 36 features seleccionadas automaticamente por variância > 1e-6 (excluiu `onoff_duracao_media` e `onoff_num_ciclos` com variância ≈ 0)

**Metadados do OCC SVM:**
- `kernel = "rbf"`, `nu = 0.05` (taxa máxima esperada de falsos positivos)
- `n_support_` = número de support vectors (pontos na fronteira de decisão aprendida)
- Treinado **apenas** com as 7 amostras normais (criticidade M/B/I)

**Distribuição de scores:**
- Lê `_cache["tele_features"]` — campo `risk_score` por device (calculado no batch scoring do scheduler)
- Agrupa em: Baixo (`risk_score < 0.40`), Médio (`0.40 ≤ risk_score < 0.70`), Alto (`risk_score ≥ 0.70`)

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
