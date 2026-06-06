# Integration Plan: SVM Project → Main Project

## Goal
Port the `svm_ref/` (formerly `eletrofrioSVM/`) project's real-data pipeline, OneClassSVM model, and richer feature engineering into the main `Eletrofio-ML/` project, replacing equivalent logic.

## Phase 1: Config, Data Pipeline & Features

### 1.1 Create `src/config.py`
Centralized configuration merging both projects:
- `API_BASE`, timeout, equipe name
- Window params: `WINDOW_POINTS=72`, `STRIDE_POINTS=5`
- `SERIES_MAP`: maps API series labels to short names
- `CRITICIDADE_MAP` and `CRITICIDADE_SCORE`
- `CRITICIDADE_FALHA = {"C", "A"}`
- Paths: `DB_PATH`, `MODELS_DIR`, `REPORTS_DIR`, `DATA_DIR`
- Model filenames for SVM, RF, OneClassSVM, scaler, feature_cols

### 1.2 Rewrite `src/api_client.py`
Keep existing interface (`buscar_alarmes`, `buscar_unidades`, `buscar_telemetria`, `abrir_chamado`) but use config from `src/config.py`. The telemetry endpoint now returns all 4 series (temp, degelo, setpoint, onoff).

### 1.3 Create `src/features.py`
Port `eletrofrioSVM/features.py`:
- `extrair_features_janela(temp, degelo, setpoint, onoff)` → 36 features
  - Temperature stats: mean, std, min, max, amplitude, median, p25, p75
  - Rate of change: mean/max/std of diffs
  - Setpoint error: mean error, error std, fraction above setpoint, fraction above +5°C
  - Defrost cycle analysis: cycle count, avg duration, total time, fraction
  - ON/OFF cycle analysis: cycle count, avg duration, fraction on
- `gerar_janelas(series_dict, window, stride)` → sliding windows
- `processar_dispositivo(df_device)` → extract windows for one device
- `processar_todos(df_telemetria)` → process all devices

### 1.4 Create `src/data_collector.py`
Port `eletrofrioSVM/collect_data.py`:
- `fetch_json(route, params)` → generic API caller
- `coletar_alarmes()` → fetch + save parquet
- `coletar_unidades()` → fetch + save parquet
- `coletar_telemetria(dispositivo_id)` → fetch raw telemetry
- `parse_telemetria(dispositivo_id, raw)` → convert to DataFrame (4 series)
- `coletar_tudo()` → orchestrate: alarmes + unidades + telemetria for all devices

## Phase 2: Labeling & Models

### 2.1 Create `src/labeling.py`
Port both labeling strategies from SVM project:
- `preparar_dados_com_labels()` — alarm-timestamp-based window labeling
  - Parse `alarmeDhCad` timestamps
  - Match alarm timestamps to window indices (±150s tolerance)
  - Label windows containing alarms as anomalous
- `recalcular_labels()` — statistical threshold labeling
  - Compute 80th percentile thresholds for `temp_erro_medio`, `temp_std`, `temp_acima_5c`
  - Label windows exceeding thresholds as anomalous

### 2.2 Extend `src/models.py`
Add `OneClassSVMModel` class alongside SVC and RF:
- Uses `sklearn.svm.OneClassSVM` with RBF kernel
- `treinar(X_normal)` — trains only on normal data
- `avaliar(X_test, y_test)` — anomaly-specific metrics (precision, recall, F1)
- `predict()` with `gerar_motivo()` explanations (ported from `predict.py`)
- GridSearch over `nu` and `gamma` via cross-validation

### 2.3 Update `src/preprocessor.py`
- Add `gerar_janelas_e_features()` combining window generation + feature extraction
- Keep existing synthetic data pipeline for backward compatibility

## Phase 3: Evaluation & Main Pipeline

### 3.1 Create `src/evaluator.py`
Port `eletrofrioSVM/evaluate.py`:
- `grid_search(df_normais, df_anomalos, feature_cols)` — OneClassSVM hyperparameter search
- `calcular_metricas(y_true, y_pred)` — VP/FP/FN/VN + precision/recall/F1
- `avaliar_modelo_salvo()` — load saved model and evaluate

### 3.2 Update `src/chamado_service.py`
- Add OneClassSVM-based risk assessment
- Generate human-readable anomaly explanations

### 3.3 Update `main.py`
- Add `--real` flag to use real data collection instead of synthetic
- Add OneClassSVM training pipeline stage
- Integrate both labeling strategies
- Add anomaly-specific evaluation

## Phase 4: Dashboard & API

### 4.1 Update `poc_app.py`
- Add telemetry detail view showing all 4 series
- Display anomaly explanations

### 4.2 Update `src/api_preprocessor.py`
- Use richer feature extraction for live mode
- Keep backward compatibility with existing feature set

## Files to Create
- `src/config.py`
- `src/features.py`
- `src/data_collector.py`
- `src/labeling.py`
- `src/evaluator.py`

## Files to Modify
- `src/api_client.py` — use config, full telemetry
- `src/models.py` — add OneClassSVMModel
- `src/preprocessor.py` — add window-based processing
- `src/api_preprocessor.py` — use richer features
- `src/chamado_service.py` — add OneClassSVM assessment
- `main.py` — add real data mode + OneClassSVM stages
- `poc_app.py` — richer telemetry display
