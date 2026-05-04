# EletroFrio ML — Contexto do Projeto e Documentação Técnica

> [!IMPORTANT]
> **Resumo para Agentes de IA (Cheat Sheet):**
> - **Objetivo Primário:** Manutenção Preditiva (Prever Falhas antes que ocorram).
> - **Métrica Crítica:** **Recall** (é melhor um alarme falso do que uma falha não detectada). O GridSearchCV otimiza `scoring="recall"`, não F1.
> - **Motor de Dados:** `src/data_generator.py` simula as regras físicas de falha que a IA deve aprender.
> - **Técnica Indispensável:** **SMOTE** para balancear classes (falhas são raras, ~12%). **Não usar `class_weight="balanced"` junto** — é balanceamento duplo.
> - **Diferencial Técnico:** Engenharia de Features baseada em termodinâmica (Diferencial de Temp, Razão de Pressão).
> - **Workflow de IA:** Telemetria (Input) → ML Model (Processo) → Abrir Chamado (Output).
> - **Modo Live:** `--live` consome os endpoints reais e abre chamados automaticamente via `src/chamado_service.py`.

## 1. Visão Geral
O **EletroFrio ML** é uma solução de inteligência artificial voltada para a **manutenção preditiva** de compressores de refrigeração industrial. O sistema utiliza algoritmos de Machine Learning para analisar leituras de sensores em tempo real e prever falhas iminentes, permitindo intervenções antes que ocorra a quebra total do equipamento e a consequente perda de carga (produtos perecíveis).

## 2. Contexto de Negócio
A **Eletrofrio** atua no setor de refrigeração comercial e industrial (supermercados, centros de distribuição).
- **Problema:** Falhas inesperadas em compressores geram prejuízos em cascata: perda de estoque, multas sanitárias, custo elevado de manutenção corretiva e danos à imagem da marca.
- **Solução:** Um sistema que monitore o "batimento cardíaco" das máquinas e emita alertas baseados em padrões de dados que precedem uma falha.

## 3. Arquitetura do Sistema
O projeto é estruturado como um pipeline de dados modular, dividido em 7 etapas principais coordenadas pelo `main.py`, com uma 8ª etapa opcional para dados reais:

1.  **Geração de Dados (Digital Twin):** Simulação de sensores baseada em distribuições estatísticas reais.
2.  **Persistência (SQLite):** Armazenamento em banco de dados local para rastreabilidade e treinamento offline.
3.  **Processamento & Feature Engineering:** Transformação de dados brutos em indicadores de performance (KPIs).
4.  **Análise Exploratória (EDA):** Geração automática de inteligência visual sobre o comportamento dos ativos.
5.  **Treinamento de Modelos:** Aplicação de SVM e Random Forest com otimização de hiperparâmetros.
6.  **Avaliação Comparativa:** Teste rigoroso dos modelos usando dados nunca vistos (hold-out).
7.  **Exportação de Artefatos:** Salvamento de modelos binários e relatórios de performance.
8.  **Integração Live (opcional, flag `--live`):** Consumo dos endpoints reais da Eletrofrio, avaliação de risco por dispositivo e abertura automática de chamados técnicos.

## 4. Dicionário de Dados e Features

### 4.1. Dados Brutos (Sensores)
| Sensor | Unidade | Significado Técnico |
| :--- | :--- | :--- |
| `temp_succao` | °C | Temperatura do fluido ao entrar no compressor. |
| `temp_descarga` | °C | Temperatura do fluido ao sair (indica esforço térmico). |
| `temp_evaporador` | °C | Temperatura de troca térmica no ambiente frio. |
| `temp_ambiente` | °C | Temperatura do ambiente externo (fator de carga sazonal). |
| `pressao_succao` | bar | Pressão de entrada (baixa pressão). |
| `pressao_descarga` | bar | Pressão de saída (alta pressão). |
| `corrente` | A | Consumo elétrico (picos indicam sobrecarga mecânica). |
| `vibracao` | mm/s | Desgaste de rolamentos e desalinhamento. |
| `nivel_refrigerante` | % | Quantidade de gás no sistema. |
| `horas_desde_manut` | h | Horas acumuladas desde a última manutenção preventiva. Flag crítica: > 720h (30 dias). |

### 4.2. Features Engenheiradas (Calculadas)
O modelo utiliza lógica de termodinâmica para criar novas variáveis:
- **Diferencial de Temperatura:** `temp_descarga - temp_succao`.
- **Razão de Pressão:** `pressao_descarga / pressao_succao` (indica desgaste de válvulas).
- **Índice de Risco:** Combinação ponderada de calor e vibração.
- **Flags de Limite:** Identificação binária de níveis críticos de manutenção e fluido.

## 5. Estratégia de Machine Learning

### 5.1. Tratamento de Dados Imprecisos/Desbalanceados
O sistema utiliza o **SMOTE (Synthetic Minority Over-sampling Technique)**. Em ambientes reais, compressores falham raramente (~12% dos registros). Sem o SMOTE, o modelo tenderia a sempre dizer que "está tudo bem", ignorando as falhas. O SMOTE cria exemplos sintéticos da classe minoritária (falha) para equilibrar o aprendizado.

**Importante:** O SMOTE é a única técnica de balanceamento aplicada. O parâmetro `class_weight="balanced"` foi removido dos modelos pois combiná-lo com SMOTE causa balanceamento duplo, penalizando artificialmente a classe majoritária e distorcendo as probabilidades de saída.

### 5.2. Algoritmos
- **SVM (Support Vector Machine):** Utiliza kernel RBF para mapear padrões não lineares complexos. Ótimo para detecção de anomalias em espaços de alta dimensão.
- **Random Forest:** Um conjunto de árvores de decisão. É utilizado principalmente para fornecer **explicabilidade**, mostrando ao técnico qual sensor foi o responsável pelo alerta de falha.

### 5.3. Otimização
Ambos os modelos passam por um **GridSearchCV** com validação cruzada estratificada (5-Fold), usando `scoring="recall"` como critério de seleção. Isso garante que o hiperparâmetro escolhido seja o que maximiza a detecção de falhas reais, não apenas a acurácia geral. O modelo final exportado é o que obteve **maior Recall no conjunto de teste hold-out**.

## 6. Métricas de Sucesso
O projeto prioriza o **Recall** acima da Acurácia simples.
- **Por que o Recall?** É preferível ter um "Alarme Falso" (Baixa Precisão) do que uma "Falha Não Detectada" (Baixo Recall). Uma falha não detectada significa perda total da mercadoria no supermercado.

## 7. Estrutura de Pastas
```
EletroFrio-ML/
├── main.py                    # Orquestrador central (flags: --rapido, --sem-busca, --forcar-geracao, --live)
├── PLAN.md                    # Documentação técnica detalhada das implementações
├── src/
│   ├── data_generator.py      # Simulação de sensores e persistência SQLite
│   ├── preprocessor.py        # Limpeza, Feature Engineering e SMOTE
│   ├── models.py              # Implementação SVM/RF, GridSearchCV e métricas
│   ├── visualizacoes.py       # Motor gráfico (Matplotlib/Seaborn) — 8 gráficos
│   ├── api_client.py          # Cliente HTTP para os 4 endpoints da Eletrofrio
│   ├── api_preprocessor.py    # Transforma dados reais da API em features para o modelo
│   └── chamado_service.py     # Avalia risco e dispara POST /abrir-chamado automaticamente
├── data/
│   └── eletrofrio.db          # SQLite com tabelas: compressores_leituras, compressores_info, falhas_registradas, leituras_real
├── models/
│   ├── svm_eletrofrio.pkl     # Modelo SVM serializado
│   └── rf_eletrofrio.pkl      # Modelo Random Forest serializado
└── reports/
    ├── relatorio_modelos.json # Métricas completas de ambos os modelos
    └── figures/               # 8 gráficos PNG gerados automaticamente
```

## 8. Como este projeto deve ser mantido
- Sempre que um novo sensor for adicionado à máquina real, ele deve ser incluído no `NORMAL` e `FAILURE` do `data_generator.py` para re-treinamento.
- O modelo deve ser reavaliado trimestralmente para ajustar a deriva de dados (data drift) causada pelo desgaste natural dos equipamentos ao longo das estações do ano.

## 9. Integração com APIs e Dados Reais

A integração com os endpoints reais da Eletrofrio está implementada e é ativada com a flag `--live`. Os módulos responsáveis são `src/api_client.py`, `src/api_preprocessor.py` e `src/chamado_service.py`.

### 9.1. Relação com os Endpoints

| Endpoint | Papel no Sistema | Módulo Responsável |
| :--- | :--- | :--- |
| `?route=alarmes` | **Ground Truth.** Fornece criticidade (C/A/M/B/I) e tempo sem tratativa. Criticidade C ou A é mapeada para `falha=1`. | `api_preprocessor.py` |
| `?route=telemetria&dispositivoId=ID` | **Features de temperatura.** Retorna série temporal de 24h em formato Chart.js, que é pivotada para extrair: média, máxima, amplitude, volatilidade e tendência (slope linear). | `api_preprocessor.py` |
| `?route=unidades` | **Contexto geográfico e contratual.** Disponível via `buscar_unidades()` para enriquecimento futuro (tipo de contrato, região). | `api_client.py` |
| `?route=abrir-chamado` (POST) | **Ponto de ação.** Disparado automaticamente quando `proba_falha >= 75%` ou criticidade C sem tratativa. O payload inclui loja, dispositivo, tag e o `motivoIA` gerado pelo modelo. | `chamado_service.py` |

### 9.2. Gap de Features: Modo Sintético vs. Modo Live

O modelo treinado usa 18 features (10 brutas de sensores + 8 engineered). A API real entrega **apenas temperatura**. No modo `--live`, o `chamado_service.py` usa apenas as 9 features disponíveis (scores de criticidade, tempo, flags de tratativa e as 5 features de temperatura). O modelo infere com as colunas presentes — a probabilidade resultante é conservadora, mas compensada pela regra de negócio: **criticidade C sem tratativa abre chamado independentemente do score do modelo**.

### 9.3. Fluxo de Valor (Modo Live)

```
/alarmes  →  processar_alarmes()  →  label (falha=0/1) + criticidade_score + tempo_min
    ↓
/telemetria (por dispositivoId)  →  _extrair_features_telemetria()  →  temp_media, temp_maxima, temp_tendencia...
    ↓
Random Forest  →  predict_proba()  →  probabilidade de falha (0.0 a 1.0)
    ↓
chamado_service  →  proba >= 0.75 ou (criticidade=C e sem tratativa)
    ↓
/abrir-chamado (POST)  →  ordem de serviço preventiva criada automaticamente
```

## 10. Como Executar

```bash
# Pipeline completo com dados sintéticos (treino + avaliação + gráficos)
python main.py

# Versão rápida para desenvolvimento (dataset menor, sem GridSearchCV)
python main.py --rapido --sem-busca

# Forçar regeneração do banco SQLite mesmo se já existir
python main.py --forcar-geracao

# Treinar e depois consumir endpoints reais + abrir chamados automaticamente
python main.py --rapido --sem-busca --live
```

Os artefatos gerados ficam em:
- `data/eletrofrio.db` — banco SQLite com todos os dados
- `models/` — modelos `.pkl` prontos para inferência
- `reports/relatorio_modelos.json` — métricas detalhadas (Recall, F1, ROC-AUC, matriz de confusão)
- `reports/figures/` — 8 gráficos PNG (distribuição de classes, correlação, boxplots, ROC, importância de features, etc.)

