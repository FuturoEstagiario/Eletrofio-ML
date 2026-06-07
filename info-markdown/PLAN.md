# PLAN.md — EletroFrio ML

## Checklist Técnica

- [x] Corrigir `scoring="recall"` no GridSearchCV de SVM e Random Forest
- [x] Remover `class_weight="balanced"` (redundante com SMOTE)
- [x] Remover `import classification_report` não utilizado em `models.py`
- [x] Remover `import numpy` não utilizado em `main.py`
- [x] Trocar critério de "melhor modelo" de F1 para Recall em `main.py`
- [x] Remover `carregar_sqlite()` duplicada de `data_generator.py`
- [x] Criar `src/api_client.py` — cliente HTTP para os endpoints reais
- [x] Criar `src/api_preprocessor.py` — transformação de dados reais
- [x] Criar `src/chamado_service.py` — abertura automática de chamados
- [x] Adicionar flag `--live` ao `main.py`
- [x] Criar `src/db.py` — conexão centralizada com Supabase (psycopg2)
- [x] Migrar `preprocessor.py` para ler `compressores_leituras` do Supabase
- [x] Migrar `api_preprocessor.py` para ler/escrever `leituras_real` no Supabase
- [x] Atualizar `main.py` — `carregar_e_preparar()` sem `db_path`; `pipeline_live()` sem `db_path`

---

## 💡 Conceito Chave

O pipeline opera em dois modos. No modo padrão, dados sintéticos de 10 compressores são gerados por `data_generator.py`, processados com feature engineering termodinâmica e usados para treinar SVM e Random Forest com SMOTE para balancear as classes minoritárias (falha ~12%). No modo `--live`, após o treino, o modelo RF treinado é aplicado sobre dados reais coletados dos endpoints da Eletrofrio: alarmes alimentam o label e a criticidade, enquanto a telemetria por dispositivo fornece features de temperatura (média, máxima, amplitude, tendência, volatilidade). Dispositivos com risco ≥ 75% ou criticidade C sem tratativa disparam automaticamente um POST para `/abrir-chamado`.

---

## 📚 Dicionário de Implementação

| Símbolo | Onde | Significado |
|---|---|---|
| `THRESHOLD_RISCO = 0.75` | `chamado_service.py` | Probabilidade mínima do RF para abrir chamado automaticamente |
| `CRITICIDADE_FALHA = {"C", "A"}` | `api_preprocessor.py` | Criticidades que mapeiam para `falha=1` no label de treino |
| `temp_tendencia` | `api_preprocessor.py` | Coeficiente angular da regressão linear sobre a série de temperatura — valores positivos indicam aquecimento progressivo |
| `sem_tratativa` | `api_preprocessor.py` | Flag 1 quando `eventoDhCad` é nulo (alarme sem resposta registrada) |
| `_parse_tempo_minutos()` | `api_preprocessor.py` | Converte strings como "6d 22h 41m" para minutos totais via regex |
| `enriquecer_com_telemetria()` | `api_preprocessor.py` | Itera sobre dispositivos e faz GET `/telemetria` para cada um, extraindo features de temperatura |
| `pipeline_live()` | `main.py` | Etapa 8 opcional: consome API real, salva em Supabase (`leituras_real`), avalia risco e abre chamados |
| `get_connection()` | `src/db.py` | Retorna conexão psycopg2 para o Supabase usando keyword args (evita quebra de URL por `@` na senha) |
| `urllib3.disable_warnings()` | `api_client.py` | Suprime avisos de SSL do certificado auto-assinado do endpoint da Eletrofrio |

---

## Gap de Features — Modo Live vs Modo Sintético

O modelo treinado com dados sintéticos usa 18 features (10 brutas + 8 engineered). A API real entrega apenas temperatura. O `chamado_service.py` instrui o modelo a usar apenas as colunas disponíveis em `feature_cols`, que são as 9 features extraíveis de alarmes + telemetria. O modelo faz inferência parcial — a probabilidade resultante é uma estimativa conservadora, compensada pela regra de negócio (criticidade C sem tratativa abre chamado independentemente do score).

---

## 🧪 Como Testar

**Modo sintético (pipeline completo):**
```bash
python main.py --sem-busca --rapido
```

**Modo live (após treino, consome API real):**
```bash
python main.py --sem-busca --rapido --live
```

**Apenas o cliente de API (verificar conectividade):**
```python
from src.api_client import buscar_alarmes
alarmes = buscar_alarmes()
print(len(alarmes))
```
