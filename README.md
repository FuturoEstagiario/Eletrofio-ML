# EletroFrio ML — Manutenção Preditiva para Compressores de Refrigeração

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.3+-orange)](https://scikit-learn.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-lightgrey)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-managed-blue)](https://www.postgresql.org/)

---

## Contexto

A **Eletrofrio** fornece e mantém sistemas de refrigeração industrial para supermercados. Falhas em **compressores** causam elevação de temperatura, comprometendo produtos perecíveis e gerando perdas financeiras e multas sanitárias.

Este projecto implementa um sistema de **detecção precoce de falhas** baseado em leituras de sensores reais, combinando Machine Learning com um dashboard web interactivo e pipeline de dados automático.

---

## Funcionalidades Principais

- **Dashboard web** com 10 painéis analíticos (risco, temperatura, saúde da frota, chamados, financeiro, etc.)
- **Modelos ML** — Random Forest (risco 0–1) + OneClass SVM (anomalia)
- **Colecta automática** de telemetria via API Eletrofrio a cada 6 horas (APScheduler)
- **Re-treino automático** quando novos dispositivos são detectados
- **Feedback loop** — técnico confirma/rejeita anomalia → vira label de treino
- **Chamados persistidos** no PostgreSQL com histórico e MTTR
- **API JSON** com 25+ endpoints para integração com serviços externos (RAG / WhatsApp)

---

## Arquitectura

```
API Eletrofrio → Colecta (pipeline.py) → Parquet → Treino (treinar_modelos.py)
                                                          ↓
                                                     .pkl (modelos)
                                                          ↓
                                             Flask App (poc_app.py)
                                          ┌──────────┴──────────┐
                                     Dashboards             API JSON
                                     (10 páginas)        (25+ endpoints)
                                                               ↓
                                                         PostgreSQL
                                                    (chamados + scores)
```

---

## Estrutura do Projecto

```
EletroFrio-ML/
├── poc_app.py              # Aplicação Flask (entry point)
├── treinar_modelos.py      # Re-treino com dados reais
├── coletar_tele.py         # Colecta manual de telemetria
├── main.py                 # Pipeline ML para dados sintéticos
├── requirements.txt
│
├── src/
│   ├── config.py           # Constantes e configurações
│   ├── api_client.py       # Cliente HTTP da API Eletrofrio
│   ├── features.py         # Extracção de 30+ features de telemetria
│   ├── labeling.py         # Alarmes → labels 0/1
│   ├── models.py           # Classes dos modelos ML
│   ├── chamado_service.py  # Abertura automática de chamados
│   ├── dashboard_service.py# Agregação de dados para dashboards
│   ├── db.py               # Operações PostgreSQL
│   └── pipeline.py         # Orquestração colecta + treino
│
├── models/                 # Modelos serializados (.pkl)
├── dados_coletados/        # Cache de dados em Parquet
└── views/                  # Frontend (HTML + JS + CSS)
    ├── index.html
    ├── dashboard.js
    └── dashboards/         # 10 painéis analíticos
```

---

## Modelos de Machine Learning

### Random Forest (`rf_eletrofrio.pkl`)
- Classificação binária: normal (0) / anómalo (1)
- Output: `risk_score` ∈ [0.0, 1.0]
- Avaliação: Stratified 5-Fold CV (accuracy, precision, recall, F1)
- Features: auto-detectadas do parquet (variância > 1e-6), tipicamente 25–35 features

### OneClass SVM (`svm_anomalia.pkl`)
- Detecção de anomalia não supervisionada
- Treinado apenas com amostras normais
- Output: normal (+1) / anómalo (-1)

### Score Composto de Risco (dashboard)
```
score = RF_score × 0.40 + criticidade × 0.25 + degelo × 0.20 + temp_erro × 0.15
```

---

## Features Extraídas da Telemetria

Features calculadas sobre janelas de 72 pontos (≈ 24h a 20 min/ponto):

| Categoria | Exemplos |
|---|---|
| Temperatura | mean, std, min, max, amplitude, p25, p75, erro vs setpoint |
| Degelo | nº ciclos, duração média, % tempo activo |
| On/Off | nº ciclos, % tempo activo |
| Pressão | mean, std (L1) |
| Superaquecimento | diferença temp descarga − sucção |

---

## Base de Dados PostgreSQL

```sql
-- Chamados de serviço
chamados (id, dispositivo_id, loja_id, loja_nome, tag, motivo,
          tecnico_presencial, status, criado_em, resolvido_em)

-- Histórico de scores ML por dispositivo
scores_historico (id, dispositivo_id, risk_score, anomaly, ts)
```

---

## Como Executar

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
DB_HOST=...
DB_PORT=5432
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
```

### 3. Iniciar a aplicação web

```bash
python poc_app.py
# http://localhost:5000
```

### 4. Colectar telemetria manualmente

```bash
python coletar_tele.py
```

### 5. Re-treinar modelos

```bash
python treinar_modelos.py
```

### 6. Pipeline de desenvolvimento (dados sintéticos)

```bash
python main.py              # Completo
python main.py --rapido     # Dataset menor
python main.py --sem-busca  # Sem GridSearchCV
```

---

## Dashboards Web

| Painel | Rota | O que mostra |
|---|---|---|
| Principal | `/` | KPIs globais, alarmes por criticidade |
| Mapa de Risco | `/dashboards/risco` | Score composto, sparkline, dias até falha |
| Temperatura | `/dashboards/temperatura` | Temp vs setpoint, anomalias |
| Alarmes por Loja | `/dashboards/alarmes-loja` | Barras criticidade, Pareto |
| Degelo | `/dashboards/degelo` | % tempo em degelo, alerta > 30% |
| Pressão | `/dashboards/pressao` | Pressão sucção/condensação |
| Saúde da Frota | `/dashboards/saude` | Doughnut criticidade, score médio |
| Chamados | `/dashboards/chamados` | Lista, KPIs, gráfico por hora, resolver |
| Impacto Financeiro | `/dashboards/financeiro` | Estimativa downtime × tarifa |
| Info do Modelo | `/dashboards/modelo` | Feature importance, metadados |

---

## API JSON — Endpoints Principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/health` | Estado da aplicação + modelos |
| GET | `/api/stats` | KPIs globais |
| GET | `/api/alarmes` | Lista de alarmes activos |
| GET | `/api/predict/<id>` | Risk score + anomaly em tempo real |
| GET | `/api/dashboard/saude` | Saúde da frota |
| GET | `/api/dashboard/risco` | Tabela de risco composto |
| GET | `/api/monitoramento/reincidencia` | Ranking por reincidência + MTTR |
| POST | `/api/feedback` | Feedback de técnico → label de treino |
| POST | `/api/admin/coletar` | Colecta manual imediata |
| POST | `/api/admin/treinar` | Re-treino manual imediato |
| GET | `/api/pipeline/status` | Estado do scheduler |

Documentação completa de todos os endpoints: [DOCUMENTACAO.md](DOCUMENTACAO.md)

---

## Deploy (Render)

- **Start command:** `gunicorn poc_app:app --workers 1 --bind 0.0.0.0:$PORT`
- **Workers:** `1` obrigatório (APScheduler não é multi-processo)
- **Banco de dados:** PostgreSQL managed (Render)
- **Static files:** WhiteNoise

> **Cold start:** o Render free tier dorme após 15 min de inactividade. Recomenda-se UptimeRobot a pingar `/api/health` a cada 14 minutos.

---

## Dependências

```
scikit-learn>=1.3.0    pandas>=2.0.0         numpy>=1.24.0
matplotlib>=3.7.0      seaborn>=0.12.0       imbalanced-learn>=0.11.0
joblib>=1.3.0          flask>=3.0.0          requests>=2.31.0
gunicorn>=21.0.0       whitenoise>=6.6.0     psycopg2-binary>=2.9.0
python-dotenv>=1.0.0   pyarrow>=14.0.0       apscheduler>=3.10.0
```
