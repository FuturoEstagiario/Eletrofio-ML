# EletroFrio ML — Documentação Técnica Completa

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Contexto de Negócio](#2-contexto-de-negócio)
3. [Arquitectura do Sistema](#3-arquitectura-do-sistema)
4. [Estrutura de Ficheiros](#4-estrutura-de-ficheiros)
5. [Módulos (`src/`)](#5-módulos-src)
6. [Aplicação Web (`poc_app.py`)](#6-aplicação-web-poc_apppy)
7. [Modelos de Machine Learning](#7-modelos-de-machine-learning)
8. [Base de Dados PostgreSQL](#8-base-de-dados-postgresql)
9. [Dados em Parquet](#9-dados-em-parquet)
10. [Pipeline de Dados](#10-pipeline-de-dados)
11. [Dashboards Web](#11-dashboards-web)
12. [Configuração e Deploy](#12-configuração-e-deploy)
13. [Integração Externa (RAG / WhatsApp)](#13-integração-externa-rag--whatsapp)
14. [Scripts de Linha de Comando](#14-scripts-de-linha-de-comando)

---

## 1. Visão Geral

O **EletroFrio ML** é um sistema de **manutenção preditiva** para compressores de refrigeração industrial em supermercados. Combina:

- **Colecta automática** de telemetria via API externa (Eletrofrio)
- **Feature engineering** sobre séries temporais (30+ features por dispositivo)
- **Modelos ML** supervisionados e não supervisionados (Random Forest + OneClass SVM)
- **Dashboard web** interactivo com 10 painéis analíticos
- **Pipeline automatizado** com colecta a cada 6 horas e re-treino automático
- **Persistência** em PostgreSQL (chamados de serviço + histórico de scores)

---

## 2. Contexto de Negócio

A Eletrofrio fornece e mantém sistemas de refrigeração industrial para redes de supermercados. Falhas em compressores causam:

- Elevação de temperatura comprometendo produtos perecíveis
- Perdas financeiras diretas (mercadoria inutilizada)
- Multas sanitárias e danos à marca

O sistema detecta **precocemente** padrões de degradação antes que ocorra falha completa, priorizando chamados técnicos pelos dispositivos com maior risco.

### Níveis de Criticidade dos Alarmes

| Nível | Código | Significado |
|---|---|---|
| Crítico | `C` | Falha imediata iminente |
| Alta | `A` | Atenção urgente |
| Média | `M` | Monitorar de perto |
| Baixa | `B` | Informativo |
| Informativo | `I` | Sem impacto operacional |

---

## 3. Arquitectura do Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│  API EXTERNA (Eletrofrio)                                        │
│  credenciamento.eletrofrio.com.br:5900/galileo/api/api_hackathon │
│  ├── /alarmes          → criticidade, dispositivo, timestamp     │
│  ├── /unidades         → lojas, coordenadas                     │
│  ├── /telemetria/<id>  → 27 séries temporais                    │
│  └── /abrir_chamado    → abertura de tickets técnicos           │
└──────────────┬──────────────────────────────────────────────────┘
               │ requests (HTTP)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  COLECTA E PROCESSAMENTO (src/)                                  │
│  ├── api_client.py      → chamadas HTTP autenticadas             │
│  ├── data_collector.py  → parse + save para parquet             │
│  ├── features.py        → extracção de 30+ features por janela   │
│  ├── labeling.py        → alarmes → labels 0/1 por janela        │
│  └── pipeline.py        → orquestra colecta + treino            │
└──────────────┬──────────────────────────────────────────────────┘
               │ parquet I/O
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  DADOS EM DISCO (dados_coletados/)                               │
│  ├── tele_features.parquet   → 1 linha por dispositivo          │
│  ├── tele_series.parquet     → séries temporais por janela      │
│  ├── alarmes.parquet         → alarmes em cache                 │
│  └── unidades.parquet        → lojas em cache                   │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  TREINO (treinar_modelos.py)                                     │
│  ├── Auto-detecção de features (variância > 1e-6)               │
│  ├── Stratified K-Fold CV (5-fold, métricas: acc/prec/rec/F1)  │
│  ├── RandomForestClassifier → rf_eletrofrio.pkl                 │
│  └── OneClassSVM            → svm_anomalia.pkl                  │
└──────────────┬──────────────────────────────────────────────────┘
               │ .pkl
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  FLASK APP (poc_app.py)                                          │
│  ├── Cache em memória (parquet pre-load no startup)             │
│  ├── APScheduler: colecta a cada 6h                             │
│  ├── Inferência: RF + OCC SVM por dispositivo                   │
│  ├── /dashboards/*   → 10 páginas HTML                         │
│  └── /api/*          → 25+ endpoints JSON                       │
└──────────────┬──────────────────────────────────────────────────┘
               │ psycopg2
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  POSTGRESQL (Render managed)                                     │
│  ├── chamados          → tickets de serviço + resolução         │
│  └── scores_historico  → risk_score + anomaly por dispositivo   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Estrutura de Ficheiros

```
EletroFrio-ML/
│
├── poc_app.py              # Aplicação Flask principal (entry point web)
├── treinar_modelos.py      # Re-treino com dados reais
├── coletar_tele.py         # Colecta manual de telemetria
├── main.py                 # Pipeline ML para dados sintéticos (desenvolvimento)
├── requirements.txt
├── executar.bat            # Executor Windows
│
├── src/                    # Módulos da aplicação
│   ├── config.py           # Constantes e configurações
│   ├── api_client.py       # Cliente HTTP da API Eletrofrio
│   ├── data_collector.py   # Colecta e parse de dados
│   ├── api_preprocessor.py # Enriquecimento de alarmes com telemetria
│   ├── features.py         # Extracção de features de séries temporais
│   ├── labeling.py         # Geração de labels a partir de alarmes
│   ├── preprocessor.py     # Feature engineering + SMOTE (dados sintéticos)
│   ├── models.py           # Classes dos modelos ML
│   ├── evaluator.py        # Avaliação + grid search
│   ├── chamado_service.py  # Serviço de abertura automática de chamados
│   ├── dashboard_service.py# Agregação de dados para dashboards
│   ├── db.py               # Operações PostgreSQL
│   ├── pipeline.py         # Orquestração colecta + treino
│   └── visualizacoes.py    # Gráficos matplotlib (pipeline sintético)
│
├── models/                 # Modelos ML serializados
│   ├── rf_eletrofrio.pkl   # Random Forest (classificação de risco)
│   ├── svm_eletrofrio.pkl  # SVM classifier (legacy)
│   ├── svm_anomalia.pkl    # OneClass SVM (detecção de anomalias)
│   ├── scaler.pkl          # StandardScaler
│   └── feature_cols.pkl    # Lista de features usadas no treino
│
├── dados_coletados/        # Cache de dados em Parquet
│   ├── alarmes.parquet
│   ├── unidades.parquet
│   ├── telemetria.parquet
│   ├── features.parquet
│   ├── tele_features.parquet
│   ├── tele_series.parquet
│   ├── status_dispositivos.parquet
│   └── feedback.parquet    # Labels de feedback dos técnicos
│
└── views/                  # Frontend web
    ├── index.html          # Dashboard principal
    ├── style.css           # Estilos globais
    ├── dashboard.js        # JS core (sidebar, toasts, health check)
    └── dashboards/         # Painéis analíticos
        ├── _base.html
        ├── dashboards.css
        ├── risco.{html,js}
        ├── temperatura.{html,js}
        ├── alarmes_loja.{html,js}
        ├── degelo.{html,js}
        ├── pressao.{html,js}
        ├── saude.{html,js}
        ├── chamados.{html,js}
        ├── financeiro.{html,js}
        └── modelo.{html,js}
```

---

## 5. Módulos (`src/`)

### `config.py`

Constantes globais partilhadas por todos os módulos.

| Constante | Valor / Descrição |
|---|---|
| `API_BASE` | URL base da API Eletrofrio |
| `TEMP_RANGES` | Faixas de temperatura por tipo (congelados: -25 a -5°C, resfriados: -2 a 12°C) |
| `SERIES_MAP` | Mapeamento de 27 séries de telemetria para nomes curtos |
| `CRITICIDADE_SCORE` | Score numérico por nível (C=10, A=7, M=4, B=2, I=1) |
| `RISCO_THRESHOLD` | Limiar de risco para abertura de chamado (0.75) |

---

### `api_client.py`

Cliente HTTP para a API externa da Eletrofrio.

| Função | Retorno | Descrição |
|---|---|---|
| `buscar_alarmes()` | `list[dict]` | Todos os alarmes activos |
| `buscar_unidades()` | `list[dict]` | Lojas e coordenadas |
| `buscar_telemetria(dispositivo_id)` | `dict` | 27 séries temporais de um dispositivo |
| `abrir_chamado(loja_id, loja_nome, dispositivo_id, tag, motivo_ia, requer_tecnico)` | `dict` | Abre ticket na API externa |

---

### `data_collector.py`

Colecta dados da API e persiste em Parquet.

| Função | Descrição |
|---|---|
| `coletar_alarmes()` | Fetcha alarmes → `dados_coletados/alarmes.parquet` |
| `coletar_unidades()` | Fetcha unidades → `dados_coletados/unidades.parquet` |
| `coletar_telemetria(dispositivo_id)` | Fetcha telemetria de um device |
| `parse_telemetria(dispositivo_id, raw)` | Converte resposta da API em DataFrame (uma linha por timestamp) |
| `coletar_tudo()` | Executa colecta completa: telemetria + status + unidades + alarmes |

---

### `features.py`

Extracção de features estatísticas a partir de janelas de séries temporais.

**Janela padrão:** 72 pontos (≈24h a 20 min/ponto), stride de 5 pontos.

Features extraídas por dispositivo:

| Categoria | Features |
|---|---|
| Temperatura | mean, std, min, max, amplitude, p25, p75, taxa de variação, erro vs setpoint |
| Degelo | nº de ciclos, duração média, % tempo activo |
| On/Off | nº de ciclos, % tempo activo |
| Pressão | mean (L1), std |
| Superaquecimento | diferença temp descarga − sucção |

| Função | Descrição |
|---|---|
| `extrair_features_janela(series_dict)` | Extrai 30+ features de uma janela → `dict` ou `None` se dados insuficientes |
| `processar_dispositivo(df_tele)` | Lista de dicts de features por janela de um dispositivo |
| `processar_todos(df_telemetria)` | DataFrame agregado de todos os dispositivos |
| `get_feature_columns(df)` | Retorna colunas que não são metadados |

---

### `labeling.py`

Gera labels binárias (0=normal, 1=anómalo) associando alarmes a janelas temporais.

| Função | Descrição |
|---|---|
| `preparar_dados_com_labels()` | Associa alarme a janela se timestamp dentro de ±2.5 min |
| `recalcular_labels()` | Relabeling estatístico: anomalo=1 se feature acima do percentil 80 |

---

### `api_preprocessor.py`

Enriquecimento dos alarmes com dados de telemetria e loja.

| Função | Descrição |
|---|---|
| `processar_alarmes(alarmes)` | Normaliza e enriquece alarmes com info de loja |
| `enriquecer_com_telemetria(df_alarmes, buscar_telemetria_fn)` | Adiciona features de telemetria a cada alarme |
| `_extrair_series_telemetria(telemetria)` | Extrai séries (temp, setpoint, onoff, degelo) da resposta raw da API |
| `_extrair_features_telemetria(telemetria)` | Calcula features estatísticas da resposta raw |

---

### `preprocessor.py`

Feature engineering para o pipeline de dados sintéticos (`main.py`).

**Features brutas:** temp_succao, temp_descarga, temp_ambiente, temp_evaporador, pressao_succao, pressao_descarga, corrente, vibracao, nivel_refrigerante, horas_desde_manut

**Features engenheiradas (derivadas):**

| Feature | Fórmula |
|---|---|
| `diferencial_temp` | `temp_descarga − temp_succao` |
| `razao_pressao` | `pressao_descarga / pressao_succao` |
| `temp_evap_succao_diff` | `temp_evaporador − temp_succao` |
| `corrente_por_pressao` | `corrente / pressao_descarga` |
| `indice_risco_temp` | Combinação ponderada das temperaturas críticas |
| `manut_critica` | Flag: `horas_desde_manut > 720` |
| `nivel_refrig_baixo` | Flag: `nivel_refrigerante < 50` |
| `vibracao_alta` | Flag: `vibracao > 5` |

| Função | Descrição |
|---|---|
| `engenharia_features(df)` | Cria as 8 features derivadas acima |
| `carregar_e_preparar(test_size, aplicar_smote, seed)` | Train/test split + StandardScaler + SMOTE opcional |

---

### `models.py`

Classes dos modelos ML com interface comum.

```
BaseModel
├── SVMModel          → SVC kernel RBF, class_weight=balanced, GridSearchCV (C, γ)
├── RandomForestModel → 100-300 árvores, class_weight=balanced, GridSearchCV
└── OneClassSVMModel  → Detecção de anomalia (sem labels de treino)
```

**Interface comum:**

| Método | Descrição |
|---|---|
| `treinar(X_train, y_train)` | Treina o modelo |
| `predict(X)` | Predição de classe |
| `predict_proba(X)` | Score de probabilidade (0.0–1.0) |
| `avaliar(X_test, y_test)` | Métricas: accuracy, precision, recall, F1, ROC-AUC |
| `feature_importances()` | Importância por feature (apenas RF) |
| `salvar(path)` | Serializa com joblib |
| `carregar(path)` | Desserializa |

---

### `chamado_service.py`

Avalia risco de cada dispositivo e abre chamados automaticamente quando critérios são atingidos.

**Critérios para abertura:**

- `risk_score > 0.75` (RF)
- OU `criticidade == 'C'` E sem tratativa registada
- OU `anomaly == True` (OCC SVM)

| Função | Descrição |
|---|---|
| `avaliar_e_abrir_chamados(df_leituras, modelo_predict_proba, feature_cols, modelo_oneclass)` | Avalia todos os devices e abre chamados; retorna lista de tickets abertos |

---

### `dashboard_service.py`

Agrega dados de múltiplas fontes (cache + modelos) para servir os dashboards.

| Função | Endpoint servido | Descrição |
|---|---|---|
| `risco_tabela(alarmes_raw, tele_features, modelos)` | `/api/dashboard/risco` | Score composto por device |
| `temperatura_series(did, tele_series)` | `/api/dashboard/temperatura/<id>` | Séries temp + setpoint + eventos |
| `alarmes_por_loja(alarmes_raw)` | `/api/dashboard/alarmes-loja` | Alarmes agrupados por loja |
| `degelo_analysis(tele_features, alarmes_raw)` | `/api/dashboard/degelo` | Análise de ciclos de degelo |
| `pressao_devices(tele_features)` | `/api/dashboard/pressao` | Pressão por dispositivo |
| `saude_frota(alarmes_raw, tele_features, modelos)` | `/api/dashboard/saude` | KPIs de saúde da frota |
| `financeiro_impacto(alarmes_raw, tele_features, modelos)` | `/api/dashboard/financeiro` | Impacto financeiro estimado |

**Score composto (Risco):**
```
score = RF_score × 0.40
      + criticidade_score × 0.25
      + degelo_score × 0.20
      + temp_erro_score × 0.15
```

---

### `db.py`

Todas as operações com o PostgreSQL.

#### Conexão

```python
get_connection()
# Usa variáveis de ambiente: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
```

#### Tabela `chamados`

| Função | Descrição |
|---|---|
| `init_tables()` | `CREATE TABLE IF NOT EXISTS chamados` no startup |
| `inserir_chamado(dispositivo_id, loja_id, loja_nome, tag, motivo, tecnico_presencial)` | Insere chamado → retorna `id` |
| `listar_chamados(limit=100)` | Lista ordenada por `criado_em DESC` |
| `resolver_chamado(chamado_id)` | `UPDATE SET status='fechado', resolvido_em=NOW()` → `bool` |

#### Tabela `scores_historico`

| Função | Descrição |
|---|---|
| `init_scores_historico()` | `CREATE TABLE IF NOT EXISTS scores_historico` + índice no startup |
| `inserir_score(dispositivo_id, risk_score, anomaly)` | Insere ponto de histórico |
| `listar_scores_device(dispositivo_id, limit=50)` | Histórico de um device |
| `stats_reincidencia()` | `GROUP BY dispositivo_id`: total, resolvidos, abertos, MTTR |

---

### `pipeline.py`

Orquestra colecta e treino como funções importáveis (usadas pelo APScheduler em `poc_app.py`).

| Função | Retorno | Descrição |
|---|---|---|
| `run_collection()` | `dict` com `devices_ok`, `devices_error`, `features_saved` | Colecta os 30 devices mais críticos, salva parquets |
| `run_training(use_feedback=True)` | `dict` com `feature_count`, `cv_f1_mean`, `n_devices` | Treina RF + OCC SVM; aplica labels de `feedback.parquet` se `use_feedback=True` |

---

### `evaluator.py`

Avaliação comparativa de modelos com grid search e métricas detalhadas.

- `GridSearchCV` com `StratifiedKFold` (5-fold)
- Métricas: accuracy, precision, recall, F1, ROC-AUC
- Output: `dict` com resultados por modelo + best params

---

### `visualizacoes.py`

Gráficos gerados pelo pipeline sintético (`main.py`).

| Função | Arquivo gerado |
|---|---|
| `plot_distribuicao_classes(df)` | `01_distribuicao_classes.png` |
| `plot_correlacao(df, features)` | `02_correlacao_features.png` |
| `plot_boxplots_falha(df)` | `03_boxplots_sensores.png` |
| `plot_matrizes_confusao(resultados)` | `04_matrizes_confusao.png` |
| `plot_curvas_roc(resultados, y_test)` | `05_curvas_roc.png` |
| `plot_comparacao_metricas(resultados)` | `06_comparacao_metricas.png` |
| `plot_importancia_features(df_imp)` | `07_importancia_features.png` |
| `plot_temperatura_timeline(df)` | `08_timeline_temperatura.png` |

---

## 6. Aplicação Web (`poc_app.py`)

### Inicialização e Cache

No startup, antes de aceitar requests:

1. Carrega parquets (`alarmes`, `unidades`, `tele_features`, `tele_series`) para `_cache` em memória
2. Carrega modelos ML (`rf_eletrofrio.pkl`, `svm_anomalia.pkl`, `feature_cols.pkl`) para `_modelos`
3. Executa `init_tables()` e `init_scores_historico()` no PostgreSQL
4. Inicia `BackgroundScheduler` (APScheduler) com job de 6h

O cache tem TTL de 600s — um background thread chama a API externa e refresca. Se a API externa estiver indisponível, o parquet serve como fallback.

### Variáveis de Estado

| Variável | Tipo | Descrição |
|---|---|---|
| `_cache` | `dict` | `alarmes_raw`, `unidades`, `tele_features`, `tele_series`, `ts`, `api_ok`, `data_ok` |
| `_modelos` | `dict` | `rf`, `ocsvm`, chaves das features |
| `_modelos_carregados` | `bool` | True se ao menos um modelo está disponível |
| `_pipeline_lock` | `threading.Lock` | Protege reload atómico de modelos |
| `_pipeline_state` | `dict` | Timestamps da última colecta e último treino |

### Rotas HTML

| Rota | Ficheiro renderizado |
|---|---|
| `/` | `views/index.html` |
| `/dashboards/risco` | `views/dashboards/risco.html` |
| `/dashboards/temperatura` | `views/dashboards/temperatura.html` |
| `/dashboards/alarmes-loja` | `views/dashboards/alarmes_loja.html` |
| `/dashboards/degelo` | `views/dashboards/degelo.html` |
| `/dashboards/pressao` | `views/dashboards/pressao.html` |
| `/dashboards/saude` | `views/dashboards/saude.html` |
| `/dashboards/chamados` | `views/dashboards/chamados.html` |
| `/dashboards/financeiro` | `views/dashboards/financeiro.html` |
| `/dashboards/modelo` | `views/dashboards/modelo.html` |

### Rotas API — Dados Core

| Método | Rota | Descrição | Retorno |
|---|---|---|---|
| GET | `/api/alarmes` | Lista de alarmes (do cache) | `{status, total, dados[]}` |
| GET | `/api/unidades` | Lista de lojas (do cache) | `{status, total, dados[]}` |
| GET | `/api/stats` | KPIs agregadas | `{total, criticos, sem_tratativa, lojas}` |
| GET | `/api/health` | Estado da aplicação | `{status, data_ok, api, modelos, cache_ts}` |

### Rotas API — Telemetria e Predição

| Método | Rota | Descrição | Retorno |
|---|---|---|---|
| GET | `/api/telemetria/<id>` | Features + séries de um device | `{features{}, series{}}` |
| GET | `/api/predict/<id>` | Inferência ML em tempo real | `{risk_score, anomaly, rf_prob, ocsvm_score}` |

### Rotas API — Dashboards

| Método | Rota | Dados servidos por |
|---|---|---|
| GET | `/api/dashboard/risco` | `dashboard_service.risco_tabela()` |
| GET | `/api/dashboard/temperatura/<id>` | `dashboard_service.temperatura_series()` |
| GET | `/api/dashboard/temperatura/devices` | Lista de devices com telemetria disponível |
| GET | `/api/dashboard/alarmes-loja` | `dashboard_service.alarmes_por_loja()` |
| GET | `/api/dashboard/degelo` | `dashboard_service.degelo_analysis()` |
| GET | `/api/dashboard/pressao` | `dashboard_service.pressao_devices()` |
| GET | `/api/dashboard/saude` | `dashboard_service.saude_frota()` |
| GET | `/api/dashboard/chamados` | `db.listar_chamados()` |
| GET | `/api/dashboard/financeiro` | `dashboard_service.financeiro_impacto()` |
| GET | `/api/dashboard/modelo` | Metadados dos modelos carregados |

### Rotas API — Chamados

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/abrir-chamado` | Abre chamado na API externa + persiste no PostgreSQL |
| PATCH | `/api/chamados/<id>/resolver` | Marca chamado como fechado |

### Rotas API — Monitoramento

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/monitoramento/scores/<dispositivo_id>` | Histórico de risk_score e anomaly |
| GET | `/api/monitoramento/reincidencia` | Ranking de devices por reincidência + MTTR |

### Rotas API — Pipeline e Feedback

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/feedback` | Técnico confirma/rejeita anomalia → grava em `feedback.parquet` |
| POST | `/api/admin/coletar` | Dispara colecta manual imediata |
| POST | `/api/admin/treinar` | Dispara re-treino manual imediato |
| GET | `/api/pipeline/status` | Estado do scheduler (última colecta, último treino) |

### Pipeline Automático (APScheduler)

```
A cada 6 horas:
  1. run_collection()          → actualiza tele_features.parquet + tele_series.parquet
  2. Recarrega _cache          → novos dados disponíveis imediatamente
  3. _batch_score_devices()    → infere RF + OCC SVM em todos os devices → inserir_score()
  4. _trigger_retrain_if_needed() → se nº de devices aumentou → _background_train()
```

O re-treino corre em thread daemon para não bloquear requests durante o processo.

---

## 7. Modelos de Machine Learning

### Random Forest (`rf_eletrofrio.pkl`)

- **Algoritmo:** `RandomForestClassifier` (scikit-learn)
- **Configuração:** 200 árvores, `max_depth=20`, `class_weight='balanced'`
- **Tarefa:** Classificação binária (0=normal, 1=anomalo)
- **Output:** `predict_proba()` → `risk_score` ∈ [0.0, 1.0]
- **Avaliação:** Stratified 5-Fold CV (accuracy, precision, recall, F1)
- **Features:** Auto-detectadas do parquet (variância > 1e-6), tipicamente 25–35 features

### OneClass SVM (`svm_anomalia.pkl`)

- **Algoritmo:** `OneClassSVM` (scikit-learn), kernel RBF
- **Tarefa:** Detecção de anomalias não supervisionada (treinado apenas com amostras normais)
- **Output:** `predict()` → +1 (normal) ou -1 (anómalo)
- **Atributo extra:** `ocsvm.feature_cols` — lista das features usadas no treino
- **Uso em inferência:** usa `ocsvm.feature_cols` para extrair exactamente as features correctas do cache

### SVM Classifier (`svm_eletrofrio.pkl`)

- **Algoritmo:** `SVC`, kernel RBF, `class_weight='balanced'`, `probability=True`
- **Estado:** Legacy — mantido para compatibilidade; RF é o modelo primário

### Scaler (`scaler.pkl`)

- `StandardScaler` ajustado nos dados de treino
- Aplicado antes de qualquer inferência

### Feature Columns (`feature_cols.pkl`)

- Lista de strings com os nomes exactos das colunas na ordem usada no treino
- Partilhada por RF e OCC SVM para garantir consistência

### Feedback Loop

1. Técnico chama `POST /api/feedback` com `dispositivo_id`, `anomalo` (0/1) e `reason`
2. Label é escrita em `dados_coletados/feedback.parquet`
3. No próximo re-treino, `run_training(use_feedback=True)` sobrepõe a label do alarme pelo feedback

---

## 8. Base de Dados PostgreSQL

### Tabela `chamados`

```sql
CREATE TABLE IF NOT EXISTS chamados (
    id                 SERIAL PRIMARY KEY,
    dispositivo_id     INTEGER,
    loja_id            INTEGER,
    loja_nome          TEXT,
    tag                TEXT,
    motivo             TEXT,
    tecnico_presencial BOOLEAN DEFAULT FALSE,
    status             TEXT DEFAULT 'aberto',   -- 'aberto' | 'fechado'
    criado_em          TIMESTAMP DEFAULT NOW(),
    resolvido_em       TIMESTAMP
);
```

### Tabela `scores_historico`

```sql
CREATE TABLE IF NOT EXISTS scores_historico (
    id             SERIAL PRIMARY KEY,
    dispositivo_id INTEGER NOT NULL,
    risk_score     FLOAT,
    anomaly        BOOLEAN,
    ts             TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scores_did_ts
    ON scores_historico (dispositivo_id, ts DESC);
```

### Query de Reincidência

```sql
SELECT
    dispositivo_id,
    MAX(loja_nome)    AS loja_nome,
    MAX(tag)          AS tag,
    COUNT(*)          AS total_chamados,
    COUNT(*) FILTER (WHERE status = 'fechado') AS chamados_resolvidos,
    COUNT(*) FILTER (WHERE status = 'aberto')  AS chamados_abertos,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (resolvido_em - criado_em)) / 3600.0)::numeric, 1
    ) AS mttr_horas,
    MIN(criado_em)    AS primeiro_chamado,
    MAX(criado_em)    AS ultimo_chamado
FROM chamados
GROUP BY dispositivo_id
ORDER BY total_chamados DESC
LIMIT 50;
```

---

## 9. Dados em Parquet

| Ficheiro | Origem | Conteúdo | Colunas principais |
|---|---|---|---|
| `alarmes.parquet` | API Eletrofrio | Alarmes activos | `dispositivo_id`, `criticidade`, `tag`, `loja_id`, `ts` |
| `unidades.parquet` | API Eletrofrio | Lojas | `id`, `nome`, `lat`, `lng` |
| `telemetria.parquet` | API Eletrofrio | Séries temporais raw | `dispositivo_id`, `ts`, 27 colunas de sensores |
| `tele_features.parquet` | `pipeline.py` | Features por dispositivo (1 linha/device) | `dispositivo_id`, 30+ features estatísticas |
| `tele_series.parquet` | `pipeline.py` | Séries por janela temporal | `dispositivo_id`, `window_id`, `ts`, valores |
| `feedback.parquet` | `POST /api/feedback` | Labels manuais dos técnicos | `dispositivo_id`, `anomalo`, `reason`, `ts` |
| `status_dispositivos.parquet` | `coletar_tele.py` | Status operacional | `dispositivo_id`, `status`, `ts` |

---

## 10. Pipeline de Dados

### Fluxo Completo

```
1. COLECTA (run_collection / coletar_tele.py)
   ├── Busca top-30 devices por score de criticidade (alarmes × CRITICIDADE_SCORE)
   ├── Para cada device: buscar_telemetria(id) → raw JSON
   ├── features.extrair_features_janela() → dict de 30+ features
   └── Salva tele_features.parquet + tele_series.parquet

2. ROTULAÇÃO (labeling.py)
   ├── Carrega tele_features.parquet + alarmes.parquet
   ├── Para cada janela: anomalo=1 se alarme ±2.5 min
   └── Merge → dataset com labels

3. FEEDBACK OVERRIDE (run_training com use_feedback=True)
   ├── Carrega feedback.parquet
   └── Substitui label de alarme pelo feedback do técnico onde existir

4. TREINO (treinar_modelos.py)
   ├── Filtra features com variância < 1e-6
   ├── StratifiedKFold CV (5-fold) → métricas de avaliação
   ├── Treina RandomForestClassifier em todo o dataset
   ├── Treina OneClassSVM nos samples normais (anomalo=0)
   └── Salva: rf_eletrofrio.pkl, svm_anomalia.pkl, feature_cols.pkl

5. INFERÊNCIA (poc_app.py)
   ├── Para cada device no cache:
   │   ├── Extrai features de tele_features[dispositivo_id]
   │   ├── RF.predict_proba() → risk_score ∈ [0.0, 1.0]
   │   └── OCC SVM.predict() → anomaly ∈ {True, False}
   └── Persiste em scores_historico (PostgreSQL)
```

---

## 11. Dashboards Web

| Dashboard | Rota | Dados principais |
|---|---|---|
| **Principal** | `/` | KPIs globais (total alarmes, críticos, sem tratativa), lista por criticidade |
| **Mapa de Risco** | `/dashboards/risco` | Score composto por device, sparkline de tendência, "dias até falha" |
| **Temperatura** | `/dashboards/temperatura` | Série temp vs setpoint (24h), banda ±2°C, anomalias marcadas |
| **Alarmes por Loja** | `/dashboards/alarmes-loja` | Barras por loja × criticidade, Pareto |
| **Degelo** | `/dashboards/degelo` | % tempo em degelo por device, alerta > 30% |
| **Pressão** | `/dashboards/pressao` | Pressão sucção/condensação por device, série temporal |
| **Saúde da Frota** | `/dashboards/saude` | Doughnut por criticidade, % crítico/atenção/normal, score médio |
| **Chamados** | `/dashboards/chamados` | Lista completa, KPIs (total/hoje/abertos/resolvidos), gráfico por hora, botão Resolver |
| **Impacto Financeiro** | `/dashboards/financeiro` | Estimativa de impacto (downtime × tarifa), ranking por loja |
| **Info do Modelo** | `/dashboards/modelo` | Feature importance (RF), metadados dos modelos, distribuição de scores |

### Indicador de Saúde (dashboard.js)

O indicador no topo direito reflecte o estado real do sistema:

| Estado | Cor | Condição |
|---|---|---|
| API conectada | Verde | `data_ok=true` e `api=true` |
| Cache local | Amarelo | `data_ok=true` mas `api=false` |
| Sem dados | Vermelho | `data_ok=false` |
| A carregar… | Amarelo | Flask não respondeu (catch) |

Auto-refresh a cada 30 segundos via `setInterval`.

---

## 12. Configuração e Deploy

### Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DB_HOST` | Sim | Host PostgreSQL |
| `DB_PORT` | Sim | Porta PostgreSQL (padrão 5432) |
| `DB_NAME` | Sim | Nome da base de dados |
| `DB_USER` | Sim | Utilizador PostgreSQL |
| `DB_PASSWORD` | Sim | Senha PostgreSQL |

### Deploy no Render

O projecto está configurado para deploy no [Render](https://render.com):

- **Tipo:** Web Service (Python)
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn poc_app:app --workers 1 --bind 0.0.0.0:$PORT`
- **Workers:** `1` obrigatório — múltiplos workers criam múltiplos schedulers APScheduler
- **Base de dados:** PostgreSQL managed (Render) com credenciais nas env vars
- **Ficheiros estáticos:** servidos pelo WhiteNoise

**Cold start (Render free tier):** a app dorme após 15 min de inactividade. Recomenda-se configurar um serviço de ping externo (ex: UptimeRobot) para `GET /api/health` a cada 14 minutos.

### Dependências

```
scikit-learn>=1.3.0       # Modelos ML
pandas>=2.0.0             # DataFrames
numpy>=1.24.0             # Álgebra linear
matplotlib>=3.7.0         # Gráficos (pipeline sintético)
seaborn>=0.12.0           # Visualizações estatísticas
imbalanced-learn>=0.11.0  # SMOTE
joblib>=1.3.0             # Serialização de modelos
flask>=3.0.0              # Web framework
requests>=2.31.0          # HTTP client
gunicorn>=21.0.0          # WSGI server produção
whitenoise>=6.6.0         # Static files em produção
psycopg2-binary>=2.9.0    # PostgreSQL adapter
python-dotenv>=1.0.0      # Variáveis de ambiente
pyarrow>=14.0.0           # I/O Parquet
apscheduler>=3.10.0       # Agendamento de jobs
```

---

## 13. Integração Externa (RAG / WhatsApp)

O sistema expõe uma API JSON pública adequada para consumo por serviços externos (ex: chatbot RAG via WhatsApp).

### Endpoints mais relevantes para integração

| Endpoint | Dados retornados |
|---|---|
| `GET /api/health` | Estado geral da aplicação + modelos carregados |
| `GET /api/stats` | KPIs globais: total alarmes, críticos, sem tratativa |
| `GET /api/alarmes` | Lista completa de alarmes activos com criticidade |
| `GET /api/predict/<dispositivo_id>` | Risk score + anomaly detection em tempo real |
| `GET /api/dashboard/saude` | Saúde da frota: % crítico/atenção/normal |
| `GET /api/dashboard/risco` | Tabela de risco composto por device |
| `GET /api/monitoramento/reincidencia` | Devices com mais chamados + MTTR |
| `GET /api/monitoramento/scores/<id>` | Histórico de scores de um device específico |
| `GET /api/dashboard/financeiro` | Impacto financeiro estimado por loja |

### Exemplo de fluxo RAG

```
1. RAG chama GET /api/stats
   → {"total": 120, "criticos": 8, "sem_tratativa": 3}

2. RAG chama GET /api/dashboard/risco
   → lista de devices ordenada por risco composto

3. Para cada device crítico: GET /api/predict/<id>
   → {"risk_score": 0.87, "anomaly": true}

4. RAG gera insight e envia via WhatsApp:
   "⚠️ 8 equipamentos em nível crítico. Device XYZ tem
    risco de 87% com anomalia confirmada. Recomendamos
    visita técnica urgente."
```

---

## 14. Scripts de Linha de Comando

### `poc_app.py` (aplicação principal)

```bash
python poc_app.py
# Inicia o servidor Flask em http://localhost:5000
# Carrega modelos + parquets + inicia scheduler
```

### `treinar_modelos.py`

```bash
python treinar_modelos.py
# Lê tele_features.parquet
# Treina RF + OCC SVM com K-Fold CV
# Salva modelos em models/
```

### `coletar_tele.py`

```bash
python coletar_tele.py
# Colecta telemetria dos top-30 devices
# Salva tele_features.parquet + tele_series.parquet
```

### `main.py` (pipeline de desenvolvimento)

```bash
python main.py              # Pipeline completo com dados sintéticos
python main.py --rapido     # Dataset menor
python main.py --sem-busca  # Sem GridSearchCV
python main.py --real       # Usa dados reais (parquet) em vez de sintéticos
python main.py --live       # Consume API ao vivo + abre chamados
python main.py --relabel    # Recalcula labels estatisticamente
```

---

*Documentação gerada em 07/06/2026. Para actualizar, ver `atualizacao-07-06-2026.md`.*
