# -*- coding: utf-8 -*-
"""
Colecta telemetria dos devices prioritários e guarda em parquet.
Execute LOCALMENTE (onde a porta 5900 está acessível).

Gera:
  dados_coletados/tele_features.parquet
  dados_coletados/tele_series.parquet
"""

import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="[COLETOR] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger()

import pandas as pd
from src.api_client import buscar_alarmes, buscar_telemetria
from src.data_collector import parse_telemetria
from src.features import processar_dispositivo
from src.config import SERIES_MAP

PARQUET_DIR = os.path.join(os.path.dirname(__file__), "dados_coletados")
MAX_DEVICES = 30
PRIO = {"C": 0, "A": 1, "M": 2, "B": 3, "I": 4}

log.info("Buscando lista de alarmes...")
alarmes = buscar_alarmes()
log.info(f"{len(alarmes)} alarmes recebidos")

sorted_al = sorted(alarmes, key=lambda a: PRIO.get(a.get("criticidade", "I"), 99))
device_ids = list(dict.fromkeys(
    a.get("dispositivoId") for a in sorted_al if a.get("dispositivoId")
))[:MAX_DEVICES]

log.info(f"Coletando telemetria de {len(device_ids)} devices (prioridade: C > A > M > B > I)...")

features_rows = []
series_rows = []

for did in device_ids:
    try:
        raw = buscar_telemetria(did)
        df_tele = parse_telemetria(did, raw)
        if df_tele is None or df_tele.empty:
            log.warning(f"Device {did}: sem dados de telemetria — ignorado")
            continue

        feat_list = processar_dispositivo(df_tele)
        feats = feat_list[-1] if isinstance(feat_list, list) and feat_list else {}
        row_feat = {"dispositivo_id": did}
        row_feat.update(feats)
        features_rows.append(row_feat)

        sd = {"labels": df_tele["timestamp_label"].tolist()}
        for col in SERIES_MAP.values():
            if col in df_tele.columns:
                sd[col] = df_tele[col].tolist()

        labels = sd.get("labels", [])
        n = len(labels)
        for i in range(n):
            row_s = {"dispositivo_id": did, "label_idx": i, "label": labels[i]}
            for col_name in SERIES_MAP.values():
                vals = sd.get(col_name, [])
                row_s[col_name] = vals[i] if i < len(vals) else None
            series_rows.append(row_s)

        log.info(f"Device {did}: OK — {n} pontos, {len(feats)} features")
        time.sleep(0.2)

    except Exception as e:
        log.error(f"Device {did}: ERRO {type(e).__name__}: {e}")

if features_rows:
    df_feat = pd.DataFrame(features_rows)
    path_feat = os.path.join(PARQUET_DIR, "tele_features.parquet")
    df_feat.to_parquet(path_feat, index=False)
    log.info(f"Salvo: tele_features.parquet — {len(features_rows)} devices, {df_feat.shape[1]} colunas")
else:
    log.warning("Nenhuma feature coletada — tele_features.parquet NÃO foi gerado")

if series_rows:
    df_ser = pd.DataFrame(series_rows)
    path_ser = os.path.join(PARQUET_DIR, "tele_series.parquet")
    df_ser.to_parquet(path_ser, index=False)
    log.info(f"Salvo: tele_series.parquet — {len(series_rows)} linhas, {len(device_ids)} devices")
else:
    log.warning("Nenhuma série coletada — tele_series.parquet NÃO foi gerado")

log.info("Concluído.")
