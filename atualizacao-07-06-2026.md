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

## Estado do Projecto Após a Sessão

| Componente | Estado |
|---|---|
| Dashboard (alarmes, KPIs, unidades) | Funcional |
| Dashboards ML (Temperatura, Saúde, Risco, Degelo, Pressão, Financeiro) | Funcional |
| Dashboard Qualidade do Modelo | Funcional |
| Modelos RF + OCC SVM | Treinados com dados reais (~25 devices, ~35 features) |
| Pipeline automático | Implementado (colecta 6h, re-treino automático, feedback loop) |
| API para integração RAG/WhatsApp | Pronta (20+ endpoints JSON públicos) |
| Autenticação | Não implementada (PoC) |
| Testes | Não implementados |
