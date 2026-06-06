# -*- coding: utf-8 -*-
import re
import numpy as np
import pandas as pd
from datetime import datetime
from psycopg2.extras import execute_values
from src.db import get_connection
from src.config import CRITICIDADE_SCORE, CRITICIDADE_FALHA
from src.features import extrair_features_janela

_TEMP_LABELS = [
    "Temperatura Ambiente",
    "L1 - Temperatura da sucção",
    "L1 - Temperatura de Evaporação",
    "L1 - Temperatura de Condensação",
    "Temperatura de Saída do Glicol",
    "Temperatura do Ar Externo",
    "Temperatura de Degelo",
    "Temperatura Subresfriamento",
]

_SETPOINT_LABELS = [
    "Setpoint Ambiente",
    "L1 - Setpoint Sucção",
    "L1 - Setpoint Condensação",
]

_ONOFF_LABELS = [
    "Estado de Funcionamento ON/OFF",
    "L1 - Status Compressor 1",
    "Status Solenoide",
    "Acionamento Bomba 1",
]

_DEGELO_LABELS = [
    "Status Degelo",
    "Degelo Glicol",
]


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


def _extrair_series_telemetria(telemetria: dict) -> dict:
    datasets = telemetria.get("datasets", [])
    if not datasets:
        return {}

    found = {}
    for lbl, label_list in [
        ("temp", _TEMP_LABELS),
        ("setpoint", _SETPOINT_LABELS),
        ("onoff", _ONOFF_LABELS),
        ("degelo", _DEGELO_LABELS),
    ]:
        for candidate in label_list:
            ds = next(
                (d for d in datasets if d.get("label", "") == candidate),
                None,
            )
            if ds is not None:
                values = ds.get("values", ds.get("data", []))
                cleaned = [v for v in values if v is not None]
                if cleaned:
                    found[lbl] = cleaned
                    break

    return found


def _extrair_features_telemetria(telemetria: dict) -> dict:
    series = _extrair_series_telemetria(telemetria)
    if not series.get("temp"):
        return {}

    temp = series.get("temp", [])
    degelo = series.get("degelo", [])
    setpoint = series.get("setpoint", [])
    onoff = series.get("onoff", [])

    features = extrair_features_janela(temp, degelo, setpoint, onoff)
    if features is None:
        return {}

    arr = np.array(temp, dtype=float)
    tendencia = float(np.polyfit(range(len(arr)), arr, 1)[0]) if len(arr) > 1 else 0.0

    features["temp_tendencia"] = tendencia

    return {
        "temp_media": features.get("temp_mean", 0.0),
        "temp_maxima": features.get("temp_max", 0.0),
        "temp_minima": features.get("temp_min", 0.0),
        "temp_amplitude": features.get("temp_amplitude", 0.0),
        "temp_volatilidade": features.get("temp_std", 0.0),
        "temp_tendencia": tendencia,
        "temp_acima_setpoint": features.get("temp_acima_setpoint", 0.0),
        "degelo_fracao": features.get("degelo_fracao", 0.0),
        "onoff_fracao_ligado": features.get("onoff_fracao_ligado", 0.0),
        "degelo_num_ciclos": features.get("degelo_num_ciclos", 0),
        "onoff_num_ciclos": features.get("onoff_num_ciclos", 0),
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
