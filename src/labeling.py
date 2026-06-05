import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from src.config import DATA_DIR


def is_alarm_in_window(alarm_dt, window_start_dt, window_end_dt):
    if alarm_dt.tzinfo is not None:
        alarm_dt = alarm_dt.replace(tzinfo=None)
    return window_start_dt <= alarm_dt <= window_end_dt


def build_timestamps(labels, reference_date=None):
    if reference_date is None:
        reference_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not labels:
        return []

    first_label = labels[0]
    parts = first_label.split(":")
    first_h, first_m = int(parts[0]), int(parts[1])

    base = reference_date.replace(hour=first_h, minute=first_m, second=0)
    if base > datetime.now():
        base -= timedelta(days=1)

    timestamps = [base + timedelta(minutes=5 * i) for i in range(len(labels))]
    return timestamps


def preparar_dados_com_labels():
    df_feat = pd.read_parquet(f"{DATA_DIR}/features.parquet")
    df_tele = pd.read_parquet(f"{DATA_DIR}/telemetria.parquet")
    df_alarmes = pd.read_parquet(f"{DATA_DIR}/alarmes.parquet")

    df_alarmes["alarmeDhCad"] = pd.to_datetime(df_alarmes["alarmeDhCad"], utc=True, format="mixed")

    df_tele_agrupado = df_tele.groupby("dispositivoId")["timestamp_label"].apply(list).to_dict()

    anom_dict = {}

    for did in df_feat["dispositivoId"].unique():
        alarmes_dev = df_alarmes[df_alarmes["dispositivoId"] == did]
        if alarmes_dev.empty:
            anom_dict[did] = set()
            continue

        labels = df_tele_agrupado.get(did, [])
        if not labels:
            anom_dict[did] = set()
            continue

        timestamps = build_timestamps(labels)
        alarm_dts = [ts.replace(tzinfo=None) for ts in alarmes_dev["alarmeDhCad"].tolist()]

        alarm_indices = set()
        for alarm_dt in alarm_dts:
            for i, ts in enumerate(timestamps):
                if abs((alarm_dt - ts).total_seconds()) <= 150:
                    alarm_indices.add(i)
                    break

        anom_dict[did] = alarm_indices

    df_feat["anomalo"] = False
    for _, row in df_feat.iterrows():
        did = row["dispositivoId"]
        ini = int(row["janela_inicio"])
        fim = int(row["janela_fim"])
        alarm_indices = anom_dict.get(did, set())
        if any(ini <= idx < fim for idx in alarm_indices):
            df_feat.at[_, "anomalo"] = True

    df_feat.to_parquet(f"{DATA_DIR}/features.parquet", index=False)

    df_normais = df_feat[~df_feat["anomalo"]].copy()
    df_anomalos = df_feat[df_feat["anomalo"]].copy()

    print(f"Janelas normais: {len(df_normais)}")
    print(f"Janelas anomalas: {len(df_anomalos)}")

    return df_normais, df_anomalos


def recalcular_labels():
    df_feat = pd.read_parquet(f"{DATA_DIR}/features.parquet")

    temp_erro_medio = df_feat["temp_erro_medio"].abs()
    temp_std = df_feat["temp_std"]
    temp_acima_5c = df_feat["temp_acima_5c"]
    degelo_fracao = df_feat["degelo_fracao"]

    threshold_erro = temp_erro_medio.quantile(0.80)
    threshold_std = temp_std.quantile(0.80)
    threshold_acima_5c = temp_acima_5c.quantile(0.80)

    print(f"Threshold erro medio absoluto: {threshold_erro:.2f}C (80th percentile)")
    print(f"Threshold std: {threshold_std:.2f}C (80th percentile)")
    print(f"Threshold temp_acima_5c: {threshold_acima_5c:.4f} (80th percentile)")

    df_feat["anomalo"] = (
        (temp_erro_medio.abs() > threshold_erro)
        & (temp_std > threshold_std)
    ) | (temp_acima_5c > threshold_acima_5c)

    df_normais = df_feat[~df_feat["anomalo"]].copy()
    df_anomalos = df_feat[df_feat["anomalo"]].copy()

    print(f"\nJanelas normais: {len(df_normais)} ({len(df_normais)/len(df_feat):.1%})")
    print(f"Janelas anomalas: {len(df_anomalos)} ({len(df_anomalos)/len(df_feat):.1%})")

    norm_mean = df_normais["temp_mean"].mean()
    anom_mean = df_anomalos["temp_mean"].mean()
    norm_std = df_normais["temp_std"].mean()
    anom_std = df_anomalos["temp_std"].mean()

    print(f"\nTemp media - normal: {norm_mean:.2f}C, anomalo: {anom_mean:.2f}C")
    print(f"Temp std   - normal: {norm_std:.2f}C, anomalo: {anom_std:.2f}C")

    df_feat.to_parquet(f"{DATA_DIR}/features.parquet", index=False)
    print("\nLabels salvas em dados_coletados/features.parquet")

    return df_normais, df_anomalos
