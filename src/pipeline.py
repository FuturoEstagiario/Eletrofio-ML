# -*- coding: utf-8 -*-
import logging
import os
import time
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score

log = logging.getLogger("eletrofio.pipeline")

_ROOT        = os.path.join(os.path.dirname(__file__), "..")
PARQUET_DIR  = os.path.normpath(os.path.join(_ROOT, "dados_coletados"))
CRIT_ORDER   = {"C": 4, "A": 3, "M": 2, "B": 1, "I": 0}
MIN_VARIANCE = 1e-6
MAX_DEVICES  = 30
_PRIO        = {"C": 0, "A": 1, "M": 2, "B": 3, "I": 4}


def run_collection() -> dict:
    """Colecta telemetria dos devices prioritários e actualiza os parquets.

    Devolve dict com estatísticas da colecta.
    Levanta excepção se a API externa estiver inacessível.
    """
    from src.api_client import buscar_alarmes, buscar_telemetria
    from src.data_collector import parse_telemetria
    from src.features import processar_dispositivo
    from src.config import SERIES_MAP

    log.info("[COLLECTION] Buscando alarmes para priorizar devices...")
    alarmes   = buscar_alarmes()
    sorted_al = sorted(alarmes, key=lambda a: _PRIO.get(a.get("criticidade", "I"), 99))
    device_ids = list(dict.fromkeys(
        a.get("dispositivoId") for a in sorted_al if a.get("dispositivoId")
    ))[:MAX_DEVICES]
    log.info(f"[COLLECTION] {len(device_ids)} devices prioritários")

    features_rows: list = []
    series_rows:   list = []
    ok_count = err_count = 0

    for did in device_ids:
        try:
            raw     = buscar_telemetria(did)
            df_tele = parse_telemetria(did, raw)
            if df_tele is None or df_tele.empty:
                log.warning(f"[COLLECTION] Device {did}: sem dados de telemetria")
                continue

            feat_list = processar_dispositivo(df_tele)
            feats     = feat_list[-1] if isinstance(feat_list, list) and feat_list else {}
            features_rows.append({"dispositivo_id": did, **feats})

            labels = df_tele["timestamp_label"].tolist()
            for i, label in enumerate(labels):
                row_s = {"dispositivo_id": did, "label_idx": i, "label": label}
                for col_name in SERIES_MAP.values():
                    vals = df_tele[col_name].tolist() if col_name in df_tele.columns else []
                    row_s[col_name] = vals[i] if i < len(vals) else None
                series_rows.append(row_s)

            ok_count += 1
            time.sleep(0.2)
        except Exception as e:
            err_count += 1
            log.error(f"[COLLECTION] Device {did}: {type(e).__name__}: {e}")

    os.makedirs(PARQUET_DIR, exist_ok=True)

    if features_rows:
        pd.DataFrame(features_rows).to_parquet(
            os.path.join(PARQUET_DIR, "tele_features.parquet"), index=False
        )
    if series_rows:
        pd.DataFrame(series_rows).to_parquet(
            os.path.join(PARQUET_DIR, "tele_series.parquet"), index=False
        )

    result = {
        "devices_ok":     ok_count,
        "devices_error":  err_count,
        "features_saved": len(features_rows),
        "series_rows":    len(series_rows),
        "timestamp":      datetime.now().isoformat(),
    }
    log.info(f"[COLLECTION] Concluída: {result}")
    return result


def run_training(use_feedback: bool = True) -> dict:
    """Treina RF + OCC SVM com dados do parquet.

    Se use_feedback=True e feedback.parquet existir, os labels de técnicos
    sobrepõem as labels derivadas de criticidade de alarme.
    Devolve dict com métricas do treino.
    """
    from src.models import RandomForestModel, OneClassSVMModel
    from src.config import MODELS_DIR

    log.info("[TRAINING] Iniciando pipeline de treino...")

    feat_path = os.path.join(PARQUET_DIR, "tele_features.parquet")
    if not os.path.exists(feat_path):
        raise FileNotFoundError(f"tele_features.parquet não encontrado em {PARQUET_DIR}")

    df    = pd.read_parquet(feat_path)
    df_al = pd.read_parquet(os.path.join(PARQUET_DIR, "alarmes.parquet"))

    crit_por_device = (
        df_al.groupby("dispositivoId")["criticidade"]
        .apply(lambda s: max(s.dropna(), key=lambda c: CRIT_ORDER.get(c, 0), default="I"))
    )

    def _get_crit(did):
        if did in crit_por_device.index:
            return crit_por_device[did]
        if str(did) in crit_por_device.index:
            return crit_por_device[str(did)]
        return "I"

    df["criticidade"] = df["dispositivo_id"].map(_get_crit)
    df["anomalo"]     = df["criticidade"].map(lambda c: 1 if c in ("C", "A") else 0)

    # Labels de técnicos sobrepõem criticidade automática
    feedback_path = os.path.join(PARQUET_DIR, "feedback.parquet")
    n_feedback = 0
    if use_feedback and os.path.exists(feedback_path):
        df_fb = pd.read_parquet(feedback_path)
        for _, fb_row in df_fb.iterrows():
            mask = df["dispositivo_id"] == fb_row["dispositivo_id"]
            if mask.any():
                df.loc[mask, "anomalo"] = int(fb_row["anomalo"])
                n_feedback += 1
        log.info(f"[TRAINING] Feedback aplicado: {n_feedback} labels sobrescritos")

    n_anomalos = int(df["anomalo"].sum())
    n_normais  = int((df["anomalo"] == 0).sum())
    log.info(f"[TRAINING] Labels: {n_anomalos} anomalos | {n_normais} normais")

    if n_anomalos == 0 or n_normais == 0:
        raise ValueError("Classes insuficientes para treino — precisa de pelo menos 1 anomalo e 1 normal.")

    meta_cols    = {"dispositivo_id", "criticidade", "anomalo"}
    num_cols     = [c for c in df.columns if c not in meta_cols and pd.api.types.is_numeric_dtype(df[c])]
    variances    = df[num_cols].var()
    feature_cols = variances[variances > MIN_VARIANCE].index.tolist()
    log.info(f"[TRAINING] Features: {len(feature_cols)} úteis de {len(num_cols)} totais")

    X = np.nan_to_num(df[feature_cols].values, nan=0.0).astype(float)
    y = df["anomalo"].values.astype(int)

    os.makedirs(MODELS_DIR, exist_ok=True)

    rf = RandomForestModel()
    rf.treinar(X, y, busca_hiperpar=False)
    rf.salvar(os.path.join(MODELS_DIR, "rf_eletrofrio.pkl"))

    n_splits = min(5, n_normais, n_anomalos)
    cv       = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    f1s      = []
    for tr, te in cv.split(X, y):
        m = RandomForestClassifier(n_estimators=200, max_depth=20, random_state=42, n_jobs=-1)
        m.fit(X[tr], y[tr])
        f1s.append(f1_score(y[te], m.predict(X[te]), zero_division=0))
    cv_f1_mean = float(np.mean(f1s)) if f1s else None
    log.info(f"[TRAINING] CV F1: {cv_f1_mean:.4f}" if cv_f1_mean is not None else "[TRAINING] CV F1: N/A")

    ocsvm = OneClassSVMModel()
    ocsvm.feature_cols = feature_cols
    ocsvm.treinar(X, y, busca_hiperpar=False)
    ocsvm.salvar(MODELS_DIR)

    joblib.dump(feature_cols, os.path.join(MODELS_DIR, "feature_cols.pkl"))

    result = {
        "feature_count": len(feature_cols),
        "n_devices":     len(df),
        "n_anomalos":    n_anomalos,
        "n_normais":     n_normais,
        "n_feedback":    n_feedback,
        "cv_f1_mean":    cv_f1_mean,
        "timestamp":     datetime.now().isoformat(),
    }
    log.info(f"[TRAINING] Concluído: {result}")
    return result
