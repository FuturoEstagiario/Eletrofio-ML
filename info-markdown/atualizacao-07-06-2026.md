# Atualização — 07/06/2026

## Resumo

Sessão focada em melhorias de qualidade de dados ML, pipeline automático e preparação para integração com serviço RAG/WhatsApp.

---

## 1. Expansão de Features + Avaliação com Cross-Validation

**Ficheiros:** `treinar_modelos.py`, `poc_app.py`

**Antes:** modelos treinados com 6 features hardcoded de temperatura, sem avaliação formal.

**Depois:**
- `treinar_modelos.py` auto-detecta todas as colunas numéricas do `tele_features.parquet` (~35 features)
- Filtro de variância zero remove features constantes (inúteis para o modelo)
- Avaliação por **Stratified K-Fold CV** (5-fold) com métricas: accuracy, precision, recall, F1
- Top 15 features por importância exibidas no log de treino
- `poc_app.py`: RF e OCC SVM passam a usar o mesmo `feature_cols.pkl` (fix de bug silencioso onde OCC SVM recebia zeros na inferência)

---

## 2. Pipeline Automático (`src/pipeline.py`)

**Ficheiro novo:** `src/pipeline.py`

Extrai a lógica de `coletar_tele.py` e `treinar_modelos.py` como funções importáveis por código:

| Função | Descrição |
|---|---|
| `run_collection()` | Colecta telemetria dos 30 devices prioritários, actualiza parquets |
| `run_training(use_feedback)` | Treina RF + OCC SVM com labels de alarme + feedback de técnicos |

---

## 3. Colecta Agendada (APScheduler)

**Ficheiro:** `poc_app.py`

- `BackgroundScheduler` executa `run_collection()` automaticamente a cada **6 horas**
- Após colecta, verifica se o número de devices aumentou → dispara re-treino automático
- Cache de telemetria (tele_features + tele_series) é recarregado imediatamente após colecta

**Limitação conhecida:** com Gunicorn `workers > 1`, múltiplos schedulers são criados. Configuração actual usa `workers=1` — sem impacto. Solução futura: job store externo (Redis).

---

## 4. Re-treino Automático

**Ficheiro:** `poc_app.py`

- Função `_background_train()` corre em **thread daemon** para não bloquear requests
- Usa `threading.Lock` para reload atómico dos modelos em memória
- O servidor continua a responder durante o re-treino

**Endpoints de controlo manual:**

```
POST /api/admin/coletar   → dispara colecta imediata
POST /api/admin/treinar   → dispara re-treino imediato
GET  /api/pipeline/status → estado actual (última colecta, último treino)
```

---

## 5. Feedback Loop

**Ficheiro:** `poc_app.py`

Endpoint `POST /api/feedback` permite que técnicos confirmem ou rejeitem anomalias detectadas:

```json
{
  "dispositivo_id": 12345,
  "anomalo": 1,
  "reason": "Compressor com sobreaquecimento confirmado"
}
```

- Feedback é guardado em `dados_coletados/feedback.parquet`
- No próximo re-treino, labels de feedback **sobrepõem** labels de criticidade de alarme
- Um feedback por device — novo feedback sobrescreve o anterior

---

## 6. Dependências

`apscheduler>=3.10.0` adicionado a `requirements.txt`.

---

## 7. Persistência de Chamados no PostgreSQL

**Ficheiros:** `src/db.py`, `poc_app.py`, `views/dashboards/chamados.js`, `views/dashboards/chamados.html`

Tabela `chamados` criada no PostgreSQL no startup automático:

```sql
CREATE TABLE IF NOT EXISTS chamados (
    id SERIAL PRIMARY KEY, dispositivo_id INTEGER, loja_id INTEGER,
    loja_nome TEXT, tag TEXT, motivo TEXT, tecnico_presencial BOOLEAN,
    status TEXT DEFAULT 'aberto', criado_em TIMESTAMP DEFAULT NOW(), resolvido_em TIMESTAMP
)
```

- Chamados persistidos no PostgreSQL ao criar (fallback em memória se BD cair)
- `PATCH /api/chamados/<id>/resolver` marca chamado como `fechado`
- Dashboard Chamados lê do PostgreSQL — histórico persiste entre deploys
- KPI "Resolvidos" + botão "Resolver" por linha adicionados ao frontend

---

## 8. Histórico de Scores ML + Análise de Reincidência

**Ficheiros:** `src/db.py`, `poc_app.py`

### Histórico de Scores

Tabela `scores_historico` criada no startup:

```sql
CREATE TABLE IF NOT EXISTS scores_historico (
    id SERIAL PRIMARY KEY, dispositivo_id INTEGER NOT NULL,
    risk_score FLOAT, anomaly BOOLEAN, ts TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_scores_did_ts ON scores_historico (dispositivo_id, ts DESC);
```

Função `_batch_score_devices()` corre após cada colecta agendada (6h): infere RF + OCC SVM em todos os devices do cache e grava um registo por device. Acumula tendência ao longo do tempo.

### Análise de Reincidência

Query sobre `chamados` (sem nova tabela): calcula por device o total de chamados, resolvidos, abertos e MTTR (tempo médio de resolução em horas).

### Endpoints de monitoramento

```
GET /api/monitoramento/scores/<dispositivo_id>
    → histórico de risk_score e anomaly para um device específico

GET /api/monitoramento/reincidencia
    → ranking de devices por reincidência + MTTR médio
```

---

## 9. Fix de Performance — Dashboards Lentos e Indicador "API Offline"

**Ficheiros:** `poc_app.py`, `views/dashboard.js`

**Problema:** `/api/alarmes` e `/api/unidades` chamavam a API externa do EletroFrio a cada request HTTP, bloqueando o carregamento do dashboard enquanto a API externa estava lenta ou inativa. O indicador de saúde ficava sempre vermelho porque verificava `api_ok` (API externa online) em vez de `data_ok` (dados disponíveis em cache).

**Fix em `poc_app.py`:**
- `/api/alarmes` passa a servir `_cache["alarmes_raw"]` — dados carregados do parquet no startup
- `/api/unidades` passa a servir `_cache["unidades"]` — idem
- `/api/health` adiciona campo `data_ok: bool` (True quando parquet carregado com sucesso), separado de `api: bool` (API externa online)

**Fix em `views/dashboard.js`:**

| Estado | Antes | Depois |
|---|---|---|
| Dados disponíveis + API externa online | Verde | Verde "API conectada" |
| Dados em cache + API externa offline | Vermelho | Amarelo "Cache local" |
| Flask não responde | Vermelho | Vermelho "Sem dados" |
| A carregar (catch) | Vermelho | Amarelo "A carregar…" |

- `setInterval(verificarSaude, 30000)` adicionado — indicador atualiza automaticamente a cada 30s

**Impacto:** tempo de resposta de `/api/alarmes` e `/api/unidades` passa de variável (dependia da latência da API externa, potencialmente >5 s) para constante (~2 ms desde memória).

---

## Estado do Projecto Após a Sessão

| Componente | Estado |
|---|---|
| Dashboard (alarmes, KPIs, unidades) | Funcional |
| Dashboards ML (Temperatura, Saúde, Risco, Degelo, Pressão, Financeiro) | Funcional |
| Dashboard Qualidade do Modelo | Funcional |
| Modelos RF + OCC SVM | Treinados com dados reais (~25 devices, ~35 features) |
| Pipeline automático | Colecta 6h, re-treino automático, feedback loop, batch scoring |
| Chamados | Persistidos no PostgreSQL, endpoint resolver, KPI resolvidos |
| Histórico de scores | Gravado a cada colecta em `scores_historico` (PostgreSQL) |
| Análise de reincidência | Disponível via `/api/monitoramento/reincidencia` |
| Performance dashboards | `/api/alarmes` e `/api/unidades` servem do cache (~2 ms) |
| Indicador de saúde | 3 estados: verde/amarelo/vermelho com auto-refresh 30s |
| API para integração RAG/WhatsApp | Pronta (25+ endpoints JSON públicos) |
| Autenticação | Não implementada (PoC) |
| Testes | Não implementados |

---

## 10. Melhorias de Legibilidade dos Dashboards

**Ficheiros:** `views/dashboards/dashboards.css`, `views/dashboards/_base.html`, `financeiro.html/.js`, `risco.html/.js`, `saude.html/.js`

Três camadas de melhoria aplicadas nos dashboards Financeiro, Risco e Saúde:

### Card "O que fazer agora" (`exec-summary`)

Cada dashboard gera dinamicamente um card de ação após carregar os dados.
Função `renderExecSummary(containerId, items)` partilhada via `_base.html`.
Lógica específica por dashboard:

| Dashboard | Condições avaliadas |
|---|---|
| Financeiro | devices_urgentes > 0, economia_potencial > 0, roi_medio ≥ 10 |
| Risco | alarmes sem tratativa, % críticos > 30% ou > 10%, score médio > 60% |
| Saúde | n_critico > 0, pct_normal < 50%, avg_score > 60% |

Itens coloridos: `exec-item-danger` (vermelho), `exec-item-warning` (amarelo), `exec-item-ok` (verde). Fallback verde quando nada crítico.

### Tooltips Bootstrap nos KPI cards

`data-bs-toggle="tooltip"` adicionado em todos os metric-cards dos 3 dashboards.
Hover revela de onde vem cada número (fórmula, fonte de dados, limiar de alerta).
Init partilhado via `initTooltips()` em `_base.html` — roda no `DOMContentLoaded`
e re-roda após cada `renderExecSummary()` para cobrir elementos injectados dinamicamente.

### Sub-labels contextuais (`.metric-context`)

Cada KPI value passa a usar `.innerHTML` em vez de `.textContent`,
injectando uma linha extra com classificação qualitativa colorida:

| Classe | Cor | Exemplo de texto |
|---|---|---|
| `ctx-danger` | `#f87171` | "exposição elevada", "ação imediata necessária" |
| `ctx-warning` | `#facc15` | "atenção recomendada", "monitorar de perto" |
| `ctx-ok` | `#4ade80` | "exposição controlada", "frota saudável" |
| `ctx-muted` | muted | "custo total de visitas" |

Os limiares são calculados em runtime a partir dos dados reais
(não hardcoded no HTML), garantindo que a classificação reflecte o estado actual da frota.
