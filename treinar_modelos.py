# -*- coding: utf-8 -*-
"""
Treina RF e OneClassSVM com os dados reais do tele_features.parquet.
Execute LOCALMENTE depois de ter corrido coletar_tele.py.

Gera:
  models/rf_eletrofrio.pkl
  models/svm_anomalia.pkl
  models/scaler.pkl
  models/feature_cols.pkl
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="[TREINO] %(message)s", stream=sys.stderr)
log = logging.getLogger()

import joblib
import numpy as np
import pandas as pd
from src.models import RandomForestModel, OneClassSVMModel
from src.config import MODELS_DIR

PARQUET_DIR = os.path.join(os.path.dirname(__file__), "dados_coletados")
CRIT_ORDER  = {"C": 4, "A": 3, "M": 2, "B": 1, "I": 0}

# Colunas usadas pelo poc_app.py na inferência — a ordem importa
FEATURE_COLS = [
    "temp_media", "temp_maxima", "temp_minima",
    "temp_amplitude", "temp_volatilidade", "temp_tendencia",
]

# Mapeamento: nome no parquet → nome esperado pelo modelo
COL_MAP = {
    "temp_mean":              "temp_media",
    "temp_max":               "temp_maxima",
    "temp_min":               "temp_minima",
    "temp_amplitude":         "temp_amplitude",
    "temp_std":               "temp_volatilidade",
    "temp_taxa_variacao_media": "temp_tendencia",
}

log.info("═" * 55)
log.info("EletroFrio ML — Treino de Modelos com Dados Reais")
log.info("═" * 55)

# ── 1. Carregar features ─────────────────────────────────────────────────────
log.info("Carregando tele_features.parquet...")
df = pd.read_parquet(os.path.join(PARQUET_DIR, "tele_features.parquet"))
log.info(f"  {len(df)} devices, {len(df.columns)} colunas")

# ── 2. Labels a partir de criticidade dos alarmes ────────────────────────────
log.info("Calculando labels a partir de alarmes.parquet...")
df_al = pd.read_parquet(os.path.join(PARQUET_DIR, "alarmes.parquet"))

# Pior criticidade por device
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
    log.warning("  Nenhum device normal encontrado — usando M como normal para treino OCC SVM")
    df.loc[df["criticidade"] == "M", "anomalo"] = 0
    n_normais = int((df["anomalo"] == 0).sum())

if n_anomalos == 0 or n_normais == 0:
    log.error("Classes desequilibradas demais — verifique os dados. Abortando.")
    sys.exit(1)

# ── 3. Matriz de features ────────────────────────────────────────────────────
log.info("Construindo matriz de features...")
df_X = df[list(COL_MAP.keys())].rename(columns=COL_MAP)
X = np.nan_to_num(df_X.values, nan=0.0).astype(float)
y = df["anomalo"].values.astype(int)
log.info(f"  X shape: {X.shape}  |  positivos: {y.sum()}  negativos: {(y==0).sum()}")

os.makedirs(MODELS_DIR, exist_ok=True)

# ── 4. Random Forest ─────────────────────────────────────────────────────────
log.info("Treinando Random Forest...")
rf = RandomForestModel()
rf.treinar(X, y, busca_hiperpar=False)
rf.salvar(os.path.join(MODELS_DIR, "rf_eletrofrio.pkl"))

log.info("  Feature Importance:")
importances = rf.model.feature_importances_
for feat, imp in sorted(zip(FEATURE_COLS, importances), key=lambda x: -x[1]):
    bar = "█" * int(imp * 40)
    log.info(f"    {feat:<22} {imp:.4f}  {bar}")

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
log.info("Próximos passos:")
log.info("  git add models/ && git commit -m 'feat: add trained RF + OCC SVM models' && git push")
log.info("═" * 55)
