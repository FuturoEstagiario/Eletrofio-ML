# -*- coding: utf-8 -*-
import re
import numpy as np
import pandas as pd
from datetime import datetime
from psycopg2.extras import execute_values
from src.db import get_connection

CRITICIDADE_SCORE = {"C": 4, "A": 3, "M": 2, "B": 1, "I": 0}

# Criticidade C ou A → falha confirmada para fins de label
CRITICIDADE_FALHA = {"C", "A"}


def _parse_tempo_minutos(tempo_str: str | None) -> int:
    if not tempo_str:
        return 0
    dias = re.search(r"(\d+)d", tempo_str)
    horas = re.search(r"(\d+)h", tempo_str)
    minutos = re.search(r"(\d+)m", tempo_str)
    total = 0
    if dias:
        total += int(dias.group(1)) * 1440
    if horas:
        total += int(horas.group(1)) * 60
    if minutos:
        total += int(minutos.group(1))
    return total


def _extrair_features_telemetria(telemetria: dict) -> dict:
    datasets = telemetria.get("datasets", [])
    if not datasets:
        return {}

    # A API usa "values"; prefere "Temperatura Ambiente"
    ds = next(
        (d for d in datasets if "temperatura ambiente" in d.get("label", "").lower()),
        datasets[0],
    )
    valores = [v for v in ds.get("values", ds.get("data", [])) if v is not None]
    if not valores:
        return {}

    arr = np.array(valores, dtype=float)
    tendencia = float(np.polyfit(range(len(arr)), arr, 1)[0]) if len(arr) > 1 else 0.0

    return {
        "temp_media": float(arr.mean()),
        "temp_maxima": float(arr.max()),
        "temp_minima": float(arr.min()),
        "temp_amplitude": float(arr.max() - arr.min()),
        "temp_volatilidade": float(arr.std()),
        "temp_tendencia": tendencia,
    }


def processar_alarmes(alarmes: list[dict]) -> pd.DataFrame:
    registros = []
    for a in alarmes:
        crit = a.get("criticidade", "I")
        registros.append({
            "dispositivo_id":     a.get("dispositivoId"),
            "loja_id":            a.get("lojaId"),
            "loja_nome":          a.get("lojaNm", ""),
            "tag":                a.get("dispositivoNm", ""),
            "alarme_desc":        a.get("alarmeDesc", ""),
            "criticidade":        crit,
            "criticidade_score":  CRITICIDADE_SCORE.get(crit, 0),
            "tempo_min":          _parse_tempo_minutos(a.get("tempo")),
            "sem_tratativa":      int(a.get("eventoDhCad") is None),
            "silenciado":         int(a.get("silenciarAte") is not None),
            "falha":              int(crit in CRITICIDADE_FALHA),
        })
    return pd.DataFrame(registros)


def enriquecer_com_telemetria(
    df_alarmes: pd.DataFrame,
    buscar_telemetria_fn,
) -> pd.DataFrame:
    features_list = []

    for _, row in df_alarmes.iterrows():
        disp_id = row["dispositivo_id"]
        try:
            telemetria = buscar_telemetria_fn(disp_id)
            feats = _extrair_features_telemetria(telemetria)
        except Exception:
            feats = {}

        feats["dispositivo_id"] = disp_id
        features_list.append(feats)

    df_feats = pd.DataFrame(features_list)
    return df_alarmes.merge(df_feats, on="dispositivo_id", how="left")


def salvar_leituras_real(df: pd.DataFrame) -> None:
    df = df.copy()
    df["chamado_aberto"] = False
    df["timestamp"] = datetime.now().isoformat()

    colunas = [
        "dispositivo_id", "loja_id", "loja_nome", "tag",
        "criticidade", "alarme_desc", "chamado_aberto", "timestamp",
    ]
    cols_presentes = [c for c in colunas if c in df.columns]
    valores = [tuple(row[c] for c in cols_presentes) for _, row in df.iterrows()]

    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                f"INSERT INTO leituras_real ({', '.join(cols_presentes)}) VALUES %s",
                valores,
            )
        conn.commit()

    print(f"  [OK] {len(df)} leituras reais salvas em leituras_real (Supabase)")


def carregar_leituras_real() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql("SELECT * FROM leituras_real", conn)
