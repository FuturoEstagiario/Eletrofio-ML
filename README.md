# EletroFrio ML — Previsão de Falhas em Compressores de Refrigeração

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.3+-orange)](https://scikit-learn.org/)

---

## 🏭 Contexto

A **Eletrofrio** fornece e mantém sistemas de refrigeração industrial para supermercados.  
Falhas em **compressores** podem causar elevação de temperatura e comprometer produtos perecíveis — gerando perdas financeiras, multas sanitárias e danos à marca.

Este projeto implementa um sistema de **detecção precoce de falhas** baseado em leituras de sensores dos compressores, utilizando **Machine Learning supervisionado**.

---

## 🗂️ Estrutura do Projeto

```
EletroFrio-ML/
├── main.py                    # Pipeline principal (entry point)
├── requirements.txt
├── src/
│   ├── data_generator.py      # Geração de dados sintéticos → SQLite
│   ├── preprocessor.py        # Carregamento, feature engineering, SMOTE
│   ├── models.py              # SVM + Random Forest (GridSearchCV)
│   └── visualizacoes.py       # Todos os gráficos e visualizações
├── data/
│   └── eletrofrio.db          # SQLite (gerado na execução)
├── models/
│   ├── svm_eletrofrio.pkl     # Modelo SVM salvo
│   └── rf_eletrofrio.pkl      # Modelo Random Forest salvo
└── reports/
    ├── figures/               # 8 gráficos PNG gerados
    └── relatorio_modelos.json # Métricas em JSON
```

---

## 🔬 Features dos Sensores

| Feature                 | Unidade | Descrição                                 |
|-------------------------|---------|-------------------------------------------|
| `temp_succao`           | °C      | Temperatura na linha de sucção            |
| `temp_descarga`         | °C      | Temperatura na linha de descarga          |
| `temp_ambiente`         | °C      | Temperatura ambiente do local             |
| `temp_evaporador`       | °C      | Temperatura do evaporador                 |
| `pressao_succao`        | bar     | Pressão de sucção do compressor           |
| `pressao_descarga`      | bar     | Pressão de descarga do compressor         |
| `corrente`              | A       | Corrente elétrica consumida               |
| `vibracao`              | mm/s    | Vibração mecânica                         |
| `nivel_refrigerante`    | %       | Nível de gás refrigerante                 |
| `horas_desde_manut`     | h       | Horas desde a última manutenção preventiva|

### Features Engenheiradas (derivadas)

| Feature                 | Fórmula / Lógica                                   |
|-------------------------|----------------------------------------------------|
| `diferencial_temp`      | `temp_descarga - temp_succao` (superaquecimento)   |
| `razao_pressao`         | `pressao_descarga / pressao_succao` (eficiência)   |
| `temp_evap_succao_diff` | `temp_evaporador - temp_succao`                    |
| `corrente_por_pressao`  | `corrente / pressao_descarga`                      |
| `indice_risco_temp`     | Combinação ponderada das temperaturas críticas     |
| `manut_critica`         | Flag: `horas_desde_manut > 720` (30 dias)          |
| `nivel_refrig_baixo`    | Flag: `nivel_refrigerante < 50%`                   |
| `vibracao_alta`         | Flag: `vibracao > 5 mm/s`                          |

---

## 🤖 Modelos Implementados

### 1. SVM — Support Vector Machine
- Kernel: **RBF** (Radial Basis Function)
- `class_weight="balanced"` para lidar com desbalanceamento
- `probability=True` para scores de probabilidade
- **GridSearchCV** (5-fold estratificado): otimiza `C` e `gamma`

### 2. Random Forest
- 100–300 estimadores (árvores de decisão)
- `class_weight="balanced"`
- **GridSearchCV** (5-fold estratificado): otimiza `n_estimators`, `max_depth`, `min_samples_split/leaf`
- Fornece **importância de features** (Gini impurity)

### Tratamento de Desbalanceamento
- Taxa de falha ~12% (realista para operação de compressores)
- **SMOTE** (Synthetic Minority Oversampling Technique) aplicado somente no treino

---

## ⚙️ Como Executar

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Executar pipeline completo

```bash
python main.py
```

### 3. Modo rápido (dataset menor, sem GridSearchCV)

```bash
python main.py --rapido --sem-busca
```

### 4. Apenas gerar os dados

```bash
python -m src.data_generator
```

---

## 📊 Visualizações Geradas

| Arquivo                          | Conteúdo                                          |
|----------------------------------|---------------------------------------------------|
| `01_distribuicao_classes.png`    | Pizza + barras: proporção Normal vs Falha         |
| `02_correlacao_features.png`     | Heatmap de correlação entre todas as features     |
| `03_boxplots_sensores.png`       | Boxplots dos sensores por classe                  |
| `04_matrizes_confusao.png`       | Matrizes de confusão: SVM e RF                    |
| `05_curvas_roc.png`              | Curvas ROC com área sob a curva (AUC)             |
| `06_comparacao_metricas.png`     | Barras agrupadas: acurácia, F1, recall, AUC       |
| `07_importancia_features.png`    | Top 15 features mais importantes (Random Forest)  |
| `08_timeline_temperatura.png`    | Série temporal de temperatura com falhas marcadas |

---

## 🗄️ Banco de Dados (SQLite)

O arquivo `data/eletrofrio.db` contém três tabelas:

| Tabela                    | Conteúdo                                          |
|---------------------------|---------------------------------------------------|
| `compressores_leituras`   | Todas as leituras dos sensores (tabela principal) |
| `compressores_info`       | Metadados dos compressores (modelo, capacidade)   |
| `falhas_registradas`      | Subconjunto apenas com registros de falha         |

---

## 📈 Métricas de Avaliação

O projeto avalia os modelos com:
- **Acurácia** — percentual geral de acertos
- **Precisão** — dos alertas emitidos, quantos eram falhas reais
- **Recall** — das falhas reais, quantas foram detectadas *(mais crítico para este domínio)*
- **F1-Score** — média harmônica entre precisão e recall
- **ROC-AUC** — capacidade discriminativa do modelo

> ⚠️ **Recall** é a métrica mais importante neste contexto: uma falha não detectada (falso negativo) pode comprometer produtos e causar prejuízos significativos.

---

## 📦 Dependências

```
scikit-learn>=1.3.0
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
seaborn>=0.12.0
imbalanced-learn>=0.11.0
joblib>=1.3.0
```
