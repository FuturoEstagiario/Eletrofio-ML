# Atualização — 06/06/2026
### EletroFrio ML — PoC Dashboard

---

## Resumo Executivo

Sessão de desenvolvimento completa que adicionou **6 funcionalidades novas** ao dashboard, corrigiu o gráfico de pressão e renovou a apresentação visual de várias telas. Total: **14 ficheiros criados ou modificados**, **2 novos dashboards**, **1 sistema de pontuação composta**, **1 modelo financeiro** e **intros contextuais em todos os dashboards existentes**.

---

## 1. Correção — Gráfico de Pressão em Branco

**Ficheiro:** [`views/dashboards/pressao.js`](views/dashboards/pressao.js)

**Causa raiz identificada:** O `WhiteNoise` serve ficheiros estáticos a partir de uma snapshot em memória na inicialização do servidor — alterações ao JS não são servidas sem reinício. Além disso, `updateDiagnostics()` fazia `getElementById()` em elementos que ainda não existiam no HTML, lançando `TypeError` silencioso antes de o gráfico ser renderizado.

**Fixes aplicados:**

| Problema | Fix |
|---|---|
| `TypeError` em `updateDiagnostics` ao aceder elementos inexistentes | Guard `if (!alertsEl) return;` no topo da função |
| Plotly renderizava com `height: 0` | `container.style.height = '100%'` + `height: 400` no layout |
| Alterações JS ignoradas | Reinício do servidor após cada mudança de estático |

---

## 2. Badges de Diagnóstico — Dashboard Pressão

**Ficheiros:** [`views/dashboards/pressao.html`](views/dashboards/pressao.html) · [`views/dashboards/dashboards.css`](views/dashboards/dashboards.css)

Três badges contextuais injetados dinamicamente entre os KPIs e o gráfico:

- **Bloqueio de condensador** (vermelho) — ativa quando razão PC/PS > 3,5
- **Superaquecimento elevado** (amarelo) — ativa quando superaquecimento > 35 °C
- **Sistema estável** (verde) — exibido quando nenhum alerta está ativo

**Classes CSS adicionadas:**
```css
.diag-alerts-row  /* container flex vertical */
.diag-badge       /* base do badge */
.diag-danger      /* fundo vermelho translúcido */
.diag-warning     /* fundo amarelo translúcido */
.diag-ok          /* fundo verde translúcido */
```

---

## 3. Redesign — Cards KPI (Tela Principal)

**Ficheiros:** [`views/index.html`](views/index.html) · [`views/style.css`](views/style.css)

Substituição do layout horizontal simples por **cards verticais com barra de proporção**:

**Antes:** ícone + número + label em linha única, sem hierarquia visual.

**Depois:**
- Layout coluna: label (topo) + ícone colorido + número grande + barra de progresso (fundo)
- A barra de proporção mostra visualmente o peso de cada criticidade no total
- Fonte `clamp(1.85rem, 2.5vw, 2.5rem)` — escala com o viewport
- Cores específicas por criticidade via classes `.kpi-crit-C`, `.kpi-crit-A`, etc.

**Gráfico de Alarmes por Criticidade:** convertido de barras verticais para **barras horizontais** com `indexAxis: 'y'`, tema escuro completo no Chart.js, `barThickness: 28`, `borderRadius: 4`.

---

## 4. Mapa de Risco — Melhorias nos Cabeçalhos

**Ficheiro:** [`views/dashboards/risco.html`](views/dashboards/risco.html)

Todas as colunas da tabela ganharam **ícones Bootstrap** e **tooltips** descritivos:

| Coluna (antes) | Coluna (depois) | Tooltip |
|---|---|---|
| Temperatura | `🌡 Temp` | "Temperatura média atual do compressor" |
| ΔSetpoint | `↔ Δ Setpoint` | "Erro médio vs. setpoint — positivo = acima do alvo" |
| Volatilidade | `📉 Volatilidade` | "Desvio padrão — mede instabilidade do ciclo térmico" |
| Degelo % | `❄ Degelo` | "% do tempo em degelo nas últimas 24h — alerta > 30%" |
| Score ML | `🖥 Score / Tend.` | "Score composto: ML×40% + Criticidade×25% + Degelo×20% + ΔSP×15%" |

Adicionada opção `Ordenar: Prioridade` ao filtro de ordenação.

---

## 5. Mapa de Risco — Score Composto + Sparklines

**Ficheiro:** [`views/dashboards/risco.js`](views/dashboards/risco.js) *(reescrito completamente)*

### Score Composto
Substituiu o score ML puro por uma pontuação multidimensional:

```
score = ML×40% + Criticidade×25% + Degelo×20% + ΔSetpoint×15%
```

| Componente | Peso | Normalização |
|---|---|---|
| Score ML (Random Forest / OC-SVM) | 40% | 0–1 direto |
| Criticidade | 25% | C=1.0, A=0.75, M=0.5, B=0.25, I=0.1 |
| Degelo fração | 20% | min(fração/50, 1) |
| Erro de temperatura | 15% | min(abs(erro)/10, 1) |

### Sparklines
Minigráficos SVG inline que mostram a **tendência histórica** do score nas últimas 8 leituras, armazenadas em `localStorage` (`ef_score_history`).

- Linha **vermelha** → score agravando (último > penúltimo + 0,02)
- Linha **verde** → score melhorando (último < penúltimo - 0,02)
- Linha **bege** → estável

### Ordenação por Prioridade
Algoritmo que combina criticidade + score composto para uma fila de atendimento acionável.

---

## 6. Análise de Pareto — Dashboard Alarmes/Loja

**Ficheiros:** [`views/dashboards/alarmes_loja.html`](views/dashboards/alarmes_loja.html) · [`views/dashboards/alarmes_loja.js`](views/dashboards/alarmes_loja.js)

Gráfico misto (Chart.js tipo `bar` + `line`) adicionado acima da tabela:
- **Barras vermelhas** = lojas que ainda contribuem para atingir 80% do volume total
- **Barras bege** = lojas na "cauda" após o limiar de 80%
- **Linha bege** = percentagem acumulada (eixo Y secundário)
- Referência visual `80%` destacada
- Tema escuro completo, sem dependências extras além do Chart.js já carregado

---

## 7. Novo Dashboard — Saúde da Frota

**Ficheiros criados:**
- [`views/dashboards/saude.html`](views/dashboards/saude.html)
- [`views/dashboards/saude.js`](views/dashboards/saude.js)

**Back-end:**
- [`src/dashboard_service.py`](src/dashboard_service.py) — função `saude_frota()` adicionada
- [`poc_app.py`](poc_app.py) — rotas `/dashboards/saude` e `/api/dashboard/saude`

**Conteúdo do dashboard:**
- KPIs: Total, N.º Críticos, N.º Atenção, N.º Normais + Score Médio
- **Donut** de distribuição por criticidade (Chart.js doughnut)
- **Gráfico misto** Scores × Críticos por loja (bar + line)
- **Tabela Top-10** com barras de risco inline
- Fórmula `avg_score = média dos risk_scores × 100`

**Rota adicionada à sidebar de todos os dashboards.**

---

## 8. Novo Dashboard — Impacto Financeiro *(sessão atual)*

**Ficheiros criados:**
- [`views/dashboards/financeiro.html`](views/dashboards/financeiro.html)
- [`views/dashboards/financeiro.js`](views/dashboards/financeiro.js)

**Back-end:**
- [`src/dashboard_service.py`](src/dashboard_service.py) — função `financeiro_impacto()` adicionada
- [`poc_app.py`](poc_app.py) — rotas `/dashboards/financeiro` e `/api/dashboard/financeiro`

### Modelo Financeiro

```
exposicao_hora   = custo_hora[criticidade] × risk_score
exposicao_diaria = exposicao_hora × 24
exposicao_semanal = exposicao_diaria × 7
ROI              = exposicao_diaria ÷ R$ 450
economia_diaria  = exposicao_diaria − R$ 450
```

**Custos de parada por criticidade:**

| Criticidade | Custo/hora |
|---|---|
| C — Crítica | R$ 3.500 |
| A — Alta | R$ 1.500 |
| M — Média | R$ 800 |
| B — Baixa | R$ 300 |
| I — Info | R$ 80 |

**Thresholds de recomendação:**

| ROI | Recomendação |
|---|---|
| ≥ 50× | **Urgente** — intervir hoje |
| ≥ 10× | **Recomendado** — planejar esta semana |
| ≥ 2× | **Monitorar** — acompanhar de perto |
| < 2× | **Normal** — sem ação imediata |

### 6 KPI Cards
1. Exposição Diária Total (R$)
2. Exposição Semanal (R$)
3. Intervenções Urgentes (contagem)
4. Economia Potencial/dia (R$) — se todos os Urgentes+Recomendados forem atendidos
5. Investimento Recomendado (R$) — `n_recomendados × R$450`
6. ROI Médio da Frota (×)

### 4 Gráficos
1. **Top-10 devices** por exposição diária — barras horizontais coloridas por criticidade
2. **Donut** de distribuição por recomendação (Urgente/Recomendado/Monitorar/Normal)
3. **Loja × Urgentes** — barras mistas: exposição (bege) + urgentes (vermelho), eixo duplo
4. **Scatter Score ML × Exposição** — eixo X = score ML (0–100%), eixo Y = R$/dia, cor por criticidade; tooltip com nome, exposição e ROI

### Tabela Completa
Colunas: Recomendação · Dispositivo · Loja · Criticidade · Score ML · R$/hora · Exposição/dia · Exposição/semana · ROI × · Economia/dia

Filtros: por recomendação e por criticidade, sem reload.

### Seção de Premissas
Cards individuais por criticidade mostrando o custo de parada estimado por hora, mais o custo fixo de intervenção.

---

## 9. Intros Contextuais — Todos os Dashboards *(sessão atual)*

**CSS adicionado em** [`views/dashboards/dashboards.css`](views/dashboards/dashboards.css):

```css
.dash-intro {
  border-left: 2px solid var(--beige-deep);
  background: rgba(201,184,154,.04);
  /* estilo consistente com o design token bege do projeto */
}
```

Bloco `.dash-intro` inserido em **8 dashboards** logo após o cabeçalho da página:

| Dashboard | Texto foco |
|---|---|
| **Mapa de Risco** | Explica score composto (pesos ML/crit/degelo/ΔSP) e como ler a tendência |
| **Temperatura** | Banda ±2 °C ao redor do setpoint e o que anomalias persistentes indicam |
| **Alarmes/Loja** | Regra de Pareto 80/20 e como identificar os alvos prioritários |
| **Degelo** | Limiar 30% e como distinguir degelo programado de evento contínuo |
| **Pressão** | Significado da razão PC/PS e do superaquecimento como indicadores de falha |
| **Saúde da Frota** | Panorama executivo e como usar o top-10 para priorizar intervenções |
| **Chamados** | Propósito do histórico para auditoria e otimização de contratos |
| **Impacto Financeiro** | Lógica ROI e por que intervir antes da falha é sempre mais barato |

---

## 10. Navegação — Links Adicionados

**Ficheiros:** [`views/dashboards/_base.html`](views/dashboards/_base.html) · [`views/index.html`](views/index.html)

Adicionado link **"Impacto Financeiro"** com ícone `bi-currency-exchange` na sidebar de todos os dashboards e na tela principal, abaixo de uma nova `sidebar-divider` após Chamados.

---

## 11. Mapa de Risco — Abrir Chamado Habilitado *(sessão continuação)*

**Ficheiros:** [`views/dashboards/_base.html`](views/dashboards/_base.html) · [`views/dashboards/risco.js`](views/dashboards/risco.js) · [`src/dashboard_service.py`](src/dashboard_service.py)

Modal técnico centralizado no template base — disponível automaticamente em todos os dashboards sem duplicação de código.

### Modal `#modalChamado` (`_base.html`)
- Exibe badge de criticidade + nome do dispositivo + loja no card de contexto
- Campo de texto livre para motivo/observação
- Checkbox "Requer técnico presencial" (pré-marcado)
- Feedback inline de sucesso/erro após submissão
- Chama `POST /api/abrir-chamado` via `fetch` com payload:
  ```json
  { "loja_id", "loja_nome", "dispositivo_id", "tag", "motivo_ia", "requer_tecnico" }
  ```
- Toast de confirmação ao sucesso + modal fecha automaticamente após 1,6s

### Funções JS globais (`_base.html`)
- `abrirChamadoModal(d)` — popula o modal com os dados do device e exibe via `bootstrap.Modal`
- `confirmarChamado()` — envia o POST, trata sucesso/erro, desabilita botão durante envio

### `risco.js`
Substituiu o stub `showToast(...)` pela chamada real:
```javascript
function abrirChamado(d) {
  abrirChamadoModal(d);
}
```

### `dashboard_service.py`
Campo `loja_id` adicionado ao payload de `risco_tabela()` (mapeado de `lojaId` camelCase da API externa):
```python
"loja_id": int(raw.get("lojaId", 0)),
```

---

## 12. Saúde da Frota — Correções e Tooltips *(sessão continuação)*

**Ficheiros:** [`views/dashboards/saude.js`](views/dashboards/saude.js) · [`src/dashboard_service.py`](src/dashboard_service.py)

### Coluna Loja visível no Top-10
`var(--text-secondary)` não está definida no tema — texto ficava invisível (cor de fundo).

```javascript
// Antes (invisível):
<td style="font-size:.78rem;color:var(--text-secondary)" ...>

// Depois (usa mesma classe do risco.js):
<td class="td-loja" ...>
```

### Top-10 ordenação corrigida
Com modelos não treinados `risk_score = null` — o filtro `filter(d => d.get("risk_score") is not None)` devolvia lista vazia.

```python
# Antes (vazio sem modelos):
top10 = sorted([d for d in devices if d.get("risk_score") is not None], ...)[:10]

# Depois (inclui todos, sort estável por criticidade + score):
top10 = sorted(devices, key=lambda d: (CRIT_ORDER.get(d["criticidade"], 99), -(d["risk_score"] or 0)))[:10]
```

### Tooltips enriquecidos
**Donut de criticidade** — ao passar o rato mostra:
- Número de devices + percentagem da frota
- Descrição da criticidade (ex.: "Parada imediata — intervenção urgente")

**Gráfico Lojas × Score** — tooltip com painel detalhado:
```
─────────────────
 Total devices : 8
 Críticos      : 2
 Score médio   : 67%
 🔴 Alto risco
```

---

## 13. Bug Fix — SyntaxError `saude.js` *(sessão continuação)*

**Ficheiro:** [`views/dashboards/saude.js`](views/dashboards/saude.js)

**Causa raiz:** a edição anterior adicionou `const total = data.reduce(...)` no topo de `buildDonut()` sem remover a declaração original na mesma função — duas declarações `const` com o mesmo identificador no mesmo scope causam `SyntaxError` no parse. O script inteiro falhava silenciosamente → `loadData()` nunca era definido → spinner ficava eternamente activo.

**Fix:**
```javascript
// Linha 64 removida (duplicado após chart constructor):
- const total = data.reduce((a, b) => a + b, 0);

// Simultaneamente corrigido var CSS indefinida na legenda:
- <span style="color:var(--text-secondary);flex:1">
+ <span style="color:var(--text);flex:1">
```

**Regra reforçada:** `var(--text-secondary)` não existe no tema — usar `var(--text)` ou `var(--muted)`.

---

## 14. Fix Deploy Render — Fallback Parquet + Timeout *(sessão continuação)*

**Ficheiros:** [`src/config.py`](src/config.py) · [`poc_app.py`](poc_app.py)

**Causa raiz:** A API externa usa a porta **5900** (não-standard), bloqueada por padrão no Render e na maioria dos serviços cloud. `API_TIMEOUT = 300` agravava o problema — o thread de background bloqueava até 5 minutos em cada chamada, mantendo `_cache["ts"] = None` e a página em "Carregando" indefinidamente.

### Fixes aplicados

| Problema | Fix |
|---|---|
| Porta 5900 bloqueada no Render | Fallback automático para parquets locais |
| `API_TIMEOUT = 300` bloqueia o thread | Reduzido para `12s` — fail fast |
| Página mostra "Carregando" forever | `_cache["ts"]` inicializado com `time.time()` no startup |
| `/api/health` fazia chamada live a cada 30s | Substituído por `_cache.get("api_ok", False)` |
| Telemetria de 50+ devices × 300s timeout | Limitada aos **top 30 devices** por criticidade |

### Fallback Parquet

Quando `buscar_alarmes()` lança excepção (API inacessível), o thread carrega automaticamente:
- `dados_coletados/alarmes.parquet` → 126 alarmes com estrutura idêntica à API
- `dados_coletados/unidades.parquet` → 314 unidades

```python
# _cache["api_ok"] = False quando usando parquet
# _cache["data_ok"] = True quando há dados disponíveis (API ou parquet)
```

O dashboard usa `data_ok` para controlar o banner de erro — dados do parquet aparecem normalmente, apenas o indicador "API indisponível" no rodapé sinaliza o fallback.

---

## 15. Auto-Refresh Silencioso — Todos os Dashboards *(sessão continuação)*

**Ficheiros:** [`saude.js`](views/dashboards/saude.js) · [`alarmes_loja.js`](views/dashboards/alarmes_loja.js) · [`degelo.js`](views/dashboards/degelo.js) · [`financeiro.js`](views/dashboards/financeiro.js)

Adicionado `setInterval` nos dashboards que não tinham polling automático:

| Dashboard | Intervalo | Função |
|---|---|---|
| Saúde da Frota | 60s | `loadData()` |
| Alarmes/Loja | 60s | `loadData()` |
| Degelo | 60s | `loadData()` |
| Impacto Financeiro | 120s | `loadFinanceiro()` (mais pesado) |

Risco e Chamados já tinham `setInterval` — mantidos inalterados.

---

## 16. Exportação CSV — Mapa de Risco e Financeiro *(sessão continuação)*

**Ficheiros:** [`_base.html`](views/dashboards/_base.html) · [`risco.js`](views/dashboards/risco.js) · [`financeiro.js`](views/dashboards/financeiro.js)

### Utilitário global `exportarCSV` (`_base.html`)

```javascript
function exportarCSV(headers, rows, filename) { ... }
```

- BOM `﻿` incluído para compatibilidade com Excel (UTF-8 com acentos)
- Disponível em todos os dashboards via herança do template base

### Botão "CSV" injectado dinamicamente

Após o primeiro carregamento bem-sucedido, um botão `<i class="bi bi-download"> CSV` é injectado programaticamente junto ao badge de timestamp — sem alteração no HTML estático.

**Campos exportados:**

| Dashboard | Colunas |
|---|---|
| Mapa de Risco | Criticidade, Dispositivo, ID, Loja, Score ML, Temp Atual, Erro Temp, Volatilidade, Degelo %, Sem Tratativa |
| Impacto Financeiro | Recomendação, Dispositivo, ID, Loja, Criticidade, Score ML, R$/hora, Exposição/dia, Exposição/semana, ROI ×, Economia/dia |

---

## 17. Horizonte Temporal de Falha *(sessão continuação)*

**Ficheiro:** [`views/dashboards/risco.js`](views/dashboards/risco.js)

Função `estimarDiasFalha(deviceId)` usa **regressão linear** nos pontos do histórico `localStorage` para projectar quando o score composto atingirá o limiar de falha (0,85).

### Algoritmo

```
xs = timestamps convertidos em dias relativos a "agora" (negativos = passado)
ys = scores compostos históricos
slope, intercept = regressão linear mínimos quadrados
dias = (0.85 − intercept) / slope
```

**Condições para exibir:**
- Mínimo 3 pontos históricos
- `slope > 0.001` (tendência de agravamento)
- `0 < dias ≤ 365` (projecção realista)

**Cores do badge:**
- 🟢 Verde → > 30 dias
- 🟡 Amarelo → ≤ 30 dias
- 🔴 Vermelho → ≤ 7 dias (urgente)

> **Limitação:** o histórico é armazenado por sessão de browser (localStorage). Sessões curtas ou múltiplos utilizadores têm menos pontos e projectam com menor precisão.

---

## 18. Early Warning Patterns *(sessão continuação)*

**Ficheiros:** [`src/dashboard_service.py`](src/dashboard_service.py) · [`views/dashboards/risco.js`](views/dashboards/risco.js)

### Backend — `_early_warnings(feats)` (`dashboard_service.py`)

Detecta 4 padrões pré-falha nas features de telemetria de cada device:

| Código | Condição | Cor |
|---|---|---|
| `temp_subindo` | `temp_taxa_variacao_media > 0.08°C/leitura` | Laranja |
| `degelo_elevado` | `degelo_fracao > 30%` | Azul |
| `acima_setpoint` | `temp_erro > 5°C` **e** tendência positiva | Vermelho |
| `temp_instavel` | `temp_std > 2.5°C` | Amarelo |

Retornados como lista `alertas` em cada registo de `risco_tabela()`.

### Frontend — badges na coluna Score (`risco.js`)

Cada alerta renderiza um badge inline colorido com ícone e texto curto:
```
🌡 Temp subindo   ❄ Degelo elevado   ↑ Acima setpoint   〜 Temp instável
```

> **Dependência:** early warnings só aparecem com telemetria disponível (API acessível ou tele_features preenchidas). No deploy Render com parquet, os alertas ficam vazios — a coluna Score mantém-se limpa sem quebrar.

---

## 19. Novo Dashboard — Qualidade do Modelo *(sessão continuação)*

**Ficheiros criados:**
- [`views/dashboards/modelo.html`](views/dashboards/modelo.html)
- [`views/dashboards/modelo.js`](views/dashboards/modelo.js)

**Back-end:**
- [`poc_app.py`](poc_app.py) — rotas `/dashboards/modelo` e `/api/dashboard/modelo`

### Conteúdo

**4 KPI Cards:**
1. Modelo principal (RF ou OC-SVM)
2. Nº de estimadores do Random Forest
3. Score médio da frota actual
4. Nº de devices com score calculado

**2 Gráficos:**
1. **Feature Importance** — barras horizontais Chart.js com código de cor por relevância: vermelho ≥ 25%, laranja ≥ 15%, amarelo ≥ 8%, azul < 8%. Tooltip explica o significado de cada feature.
2. **Distribuição de Scores** — donut tricolor: verde (baixo risco <40%), amarelo (médio 40–70%), vermelho (alto >70%).

**2 Cards de Metadados:**
- **Random Forest:** `n_estimators`, `n_features_in`
- **OneClass SVM:** `kernel`, `nu`, `n_support` (vectores de suporte)

Ambos degradam graciosamente quando o modelo não está carregado, exibindo instrução `python main.py --real`.

---

## Resumo de Ficheiros

### Criados (novos)
| Ficheiro | Tipo | Descrição |
|---|---|---|
| [`views/dashboards/saude.html`](views/dashboards/saude.html) | HTML | Dashboard Saúde da Frota |
| [`views/dashboards/saude.js`](views/dashboards/saude.js) | JS | Lógica e gráficos do dashboard Saúde |
| [`views/dashboards/financeiro.html`](views/dashboards/financeiro.html) | HTML | Dashboard Impacto Financeiro |
| [`views/dashboards/financeiro.js`](views/dashboards/financeiro.js) | JS | Lógica, gráficos e tabela financeira |
| [`views/dashboards/modelo.html`](views/dashboards/modelo.html) | HTML | Dashboard Qualidade do Modelo |
| [`views/dashboards/modelo.js`](views/dashboards/modelo.js) | JS | Feature importance, distribuição de scores, metadados |

### Modificados
| Ficheiro | Alteração |
|---|---|
| [`src/config.py`](src/config.py) | `API_TIMEOUT: 300 → 12` |
| [`src/dashboard_service.py`](src/dashboard_service.py) | +`saude_frota()` +`financeiro_impacto()` + `loja_id` + top10 sort fix + `_early_warnings()` em `risco_tabela()` |
| [`poc_app.py`](poc_app.py) | +6 rotas + fallback parquet + `data_ok`/`api_ok` + telemetria top-30 + `import pandas as pd` |
| [`views/index.html`](views/index.html) | KPI cards redesenhados + nav links |
| [`views/style.css`](views/style.css) | CSS KPI cards vertical + barra de proporção |
| [`views/dashboards/_base.html`](views/dashboards/_base.html) | Modal Chamado + `exportarCSV()` global + nav links Financeiro e Modelo |
| [`views/dashboards/dashboards.css`](views/dashboards/dashboards.css) | +badges diagnóstico +sparkline +`.dash-intro` |
| [`views/dashboards/risco.html`](views/dashboards/risco.html) | Cabeçalhos com ícones/tooltips + sort prioridade + intro |
| [`views/dashboards/risco.js`](views/dashboards/risco.js) | Score composto + sparklines + chamado modal + horizonte temporal + early warning badges + CSV export |
| [`views/dashboards/saude.js`](views/dashboards/saude.js) | Tooltips + loja fix + top10 sort + SyntaxError fix + auto-refresh |
| [`views/dashboards/alarmes_loja.html`](views/dashboards/alarmes_loja.html) | Gráfico Pareto + intro |
| [`views/dashboards/alarmes_loja.js`](views/dashboards/alarmes_loja.js) | Dark theme + `buildParetoChart()` + auto-refresh |
| [`views/dashboards/degelo.js`](views/dashboards/degelo.js) | +auto-refresh |
| [`views/dashboards/financeiro.js`](views/dashboards/financeiro.js) | +auto-refresh + CSV export |
| [`views/dashboards/pressao.html`](views/dashboards/pressao.html) | Badges diagnóstico + intro |
| [`views/dashboards/pressao.js`](views/dashboards/pressao.js) | Guard null + height fix |
| [`views/dashboards/temperatura.html`](views/dashboards/temperatura.html) | +intro |
| [`views/dashboards/degelo.html`](views/dashboards/degelo.html) | +intro |
| [`views/dashboards/chamados.html`](views/dashboards/chamados.html) | +intro |

---

## Notas Técnicas

- **WhiteNoise caching:** qualquer alteração a `.js` ou `.css` exige reinício do servidor (`python poc_app.py`). Ficheiros `.html` (Jinja2) são lidos a cada request — sem reinício necessário.
- **Score financeiro zero:** com modelos não treinados, `risk_score = 0` → todas as exposições são R$0. Os dados financeiros reais aparecem após `python main.py --real`.
- **CSS vars no Chart.js:** `var(--beige)` não funciona em canvas 2D. Usar sempre o valor literal hex `'#c9b89a'`.
- **CSS vars indefinidas:** `var(--text-secondary)` não existe no tema — usar `var(--text)` (texto principal) ou `var(--muted)` (texto secundário).
- **Sparklines e localStorage:** histórico limitado a 8 pontos por device (`slice(-8)`). Limpar com `localStorage.removeItem('ef_score_history')` no console se necessário.
- **Scatter Chart.js:** usa tipo nativo `'scatter'`, datasets separados por criticidade para legenda automática; tooltip personalizado com `ctx.raw._d` para acesso ao objeto device.
- **Modal Chamado centralizado:** qualquer dashboard pode chamar `abrirChamadoModal(d)` — basta que `d` tenha `dispositivo_id`, `loja_id`, `loja_nome`, `criticidade` e `crit_label`.
- **Early warnings sem telemetria:** `alertas: []` quando `tele_features` está vazio (parquet fallback ou modelos não treinados). Frontend renderiza zero badges sem erros.
- **Horizonte temporal:** requer mínimo 3 pontos no `localStorage`. Em sessões novas ou após `localStorage.clear()`, o badge não aparece — comportamento esperado.
- **Porta 5900 bloqueada:** API externa inacessível em ambientes cloud (Render, Railway, Heroku). Solução permanente: pedir ao provedor da API um endpoint em 443/80, ou usar túnel. Parquet fallback cobre o PoC.
