# -*- coding: utf-8 -*-
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="[TREINO] %(message)s", stream=sys.stderr)
log = logging.getLogger()

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from src.models import RandomForestModel, OneClassSVMModel
from src.config import MODELS_DIR

PARQUET_DIR  = os.path.join(os.path.dirname(__file__), "dados_coletados")
CRIT_ORDER   = {"C": 4, "A": 3, "M": 2, "B": 1, "I": 0}
MIN_VARIANCE = 1e-6

log.info("═" * 55)
log.info("EletroFrio ML — Treino de Modelos com Dados Reais")
log.info("═" * 55)

# ── 1. Carregar features ─────────────────────────────────────────────────────
log.info("Carregando tele_features.parquet...")
df = pd.read_parquet(os.path.join(PARQUET_DIR, "tele_features.parquet"))
log.info(f"  {len(df)} devices, {len(df.columns)} colunas brutas")

# ── 2. Labels a partir de criticidade dos alarmes ────────────────────────────
log.info("Calculando labels a partir de alarmes.parquet...")
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

n_anomalos = int(df["anomalo"].sum())
n_normais  = int((df["anomalo"] == 0).sum())
log.info(f"  Labels: {n_anomalos} anomalos (C/A) | {n_normais} normais (M/B/I)")

if n_normais == 0:
    log.warning("  Nenhum device normal — usando M como normal")
    df.loc[df["criticidade"] == "M", "anomalo"] = 0
    n_normais = int((df["anomalo"] == 0).sum())

if n_anomalos == 0 or n_normais == 0:
    log.error("Classes desequilibradas demais. Abortando.")
    sys.exit(1)

# ── 3. Auto-detectar features e filtrar variância zero ───────────────────────
log.info("Detectando features úteis...")
meta_cols = {"dispositivo_id", "criticidade", "anomalo"}
num_cols  = [c for c in df.columns if c not in meta_cols and pd.api.types.is_numeric_dtype(df[c])]

variances     = df[num_cols].var()
FEATURE_COLS  = variances[variances > MIN_VARIANCE].index.tolist()
dropped       = sorted(set(num_cols) - set(FEATURE_COLS))

if dropped:
    log.info(f"  Removidas {len(dropped)} cols variância≈0: {dropped}")
log.info(f"  Features finais: {len(FEATURE_COLS)} colunas")

X = np.nan_to_num(df[FEATURE_COLS].values, nan=0.0).astype(float)
y = df["anomalo"].values.astype(int)
log.info(f"  X shape: {X.shape}  |  positivos: {y.sum()}  negativos: {(y==0).sum()}")

os.makedirs(MODELS_DIR, exist_ok=True)

# ── 4. Random Forest ─────────────────────────────────────────────────────────
log.info("Treinando Random Forest...")
rf = RandomForestModel()
rf.treinar(X, y, busca_hiperpar=False)
rf.salvar(os.path.join(MODELS_DIR, "rf_eletrofrio.pkl"))

n_splits = min(5, n_normais, n_anomalos)
log.info(f"  Avaliando com Stratified {n_splits}-Fold CV...")
cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
acc, prec, rec, f1s = [], [], [], []
for tr_idx, te_idx in cv.split(X, y):
    m = RandomForestClassifier(n_estimators=200, max_depth=20, random_state=42, n_jobs=-1)
    m.fit(X[tr_idx], y[tr_idx])
    yp = m.predict(X[te_idx])
    acc.append(accuracy_score(y[te_idx], yp))
    prec.append(precision_score(y[te_idx], yp, zero_division=0))
    rec.append(recall_score(y[te_idx], yp, zero_division=0))
    f1s.append(f1_score(y[te_idx], yp, zero_division=0))

log.info("  ── CV Results (mean ± std) ───────────────────────────")
for name, scores in [("accuracy", acc), ("precision", prec), ("recall", rec), ("f1", f1s)]:
    log.info(f"    {name:<12}: {np.mean(scores):.4f} ± {np.std(scores):.4f}  folds={[round(s,3) for s in scores]}")

log.info("  ── Feature Importance Top 15 ─────────────────────────")
pairs = sorted(zip(FEATURE_COLS, rf.model.feature_importances_), key=lambda x: -x[1])
for feat, imp in pairs[:15]:
    bar = "█" * int(imp * 40)
    log.info(f"    {feat:<30} {imp:.4f}  {bar}")

# ── 5. OneClass SVM ──────────────────────────────────────────────────────────
log.info("Treinando OneClassSVM (somente dados normais)...")
ocsvm = OneClassSVMModel()
ocsvm.feature_cols = FEATURE_COLS
ocsvm.treinar(X, y, busca_hiperpar=False)
ocsvm.salvar(MODELS_DIR)

joblib.dump(FEATURE_COLS, os.path.join(MODELS_DIR, "feature_cols.pkl"))
log.info(f"  feature_cols.pkl salvo com {len(FEATURE_COLS)} features")

log.info("═" * 55)
log.info(f"Modelos salvos em {MODELS_DIR}/")
log.info("  git add -f models/ && git commit && git push")
log.info("═" * 55)
