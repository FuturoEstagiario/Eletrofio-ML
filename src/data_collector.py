import requests
import pandas as pd
import os
import time
from src.config import API_BASE, DATA_DIR, SERIES_MAP

os.makedirs(DATA_DIR, exist_ok=True)


def fetch_json(route, params=None):
    url = f"{API_BASE}?route={route}"
    if params:
        for k, v in params.items():
            url += f"&{k}={v}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def coletar_alarmes():
    print("Coletando alarmes...")
    dados = fetch_json("alarmes")
    df = pd.DataFrame(dados)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_parquet(f"{DATA_DIR}/alarmes.parquet", index=False)
    print(f"  Alarmes coletados: {len(df)} registros")
    return df


def coletar_unidades():
    print("Coletando unidades...")
    dados = fetch_json("unidades")
    df = pd.DataFrame(dados)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_parquet(f"{DATA_DIR}/unidades.parquet", index=False)
    print(f"  Unidades coletadas: {len(df)} lojas")
    return df


def coletar_telemetria(dispositivo_id):
    dados = fetch_json("telemetria", {"dispositivoId": dispositivo_id})
    return dados


def parse_telemetria(dispositivo_id, raw):
    if not raw.get("datasets"):
        return None
    labels = raw.get("labels", [])
    series_data = {}
    for ds in raw["datasets"]:
        label = ds.get("label", "")
        serie = ds.get("values", [])
        series_data[label] = serie
    n = len(labels)
    registros = []
    for i in range(n):
        row = {"dispositivoId": dispositivo_id, "timestamp_label": labels[i], "indice": i}
        for serie_label, serie_key in SERIES_MAP.items():
            val = series_data.get(serie_label, [None] * n)[i]
            row[serie_key] = val
        registros.append(row)
    return pd.DataFrame(registros)


def coletar_tudo():
    alarmes_df = coletar_alarmes()
    unidades_df = coletar_unidades()

    device_ids = sorted(alarmes_df["dispositivoId"].unique())
    print(f"Dispositivos unicos encontrados nos alarmes: {len(device_ids)}")

    device_com_alarme = set(alarmes_df["dispositivoId"].unique())
    alarmes_por_device = (
        alarmes_df.groupby("dispositivoId")
        .agg(
            num_alarmes=("alarmeId", "count"),
            criticidade_max=("criticidade", lambda x: ",".join(sorted(set(x)))),
            alarmes_lista=("alarmeDesc", lambda x: list(x)),
        )
        .reset_index()
    )

    dfs_telemetria = []
    device_ids_validos = []

    for did in device_ids:
        try:
            raw = coletar_telemetria(did)
            df_tele = parse_telemetria(did, raw)
            if df_tele is not None:
                dfs_telemetria.append(df_tele)
                device_ids_validos.append(did)
                print(f"  Device {did}: OK ({len(df_tele)} pontos)")
            else:
                print(f"  Device {did}: datasets vazio (offline)")
            time.sleep(0.3)
        except Exception as e:
            print(f"  Device {did}: erro - {e}")

    if dfs_telemetria:
        df_telemetria = pd.concat(dfs_telemetria, ignore_index=True)
        df_telemetria.to_parquet(f"{DATA_DIR}/telemetria.parquet", index=False)
        print(f"\nTelemetria total: {len(df_telemetria)} linhas, {len(device_ids_validos)} dispositivos")
    else:
        print("\nNenhum dado de telemetria coletado!")
        df_telemetria = pd.DataFrame()

    status = []
    for did in device_ids_validos:
        tem_alarme = did in device_com_alarme
        status.append({"dispositivoId": did, "tem_alarme": tem_alarme})

    df_status = pd.DataFrame(status)
    df_status = df_status.merge(alarmes_por_device, on="dispositivoId", how="left")
    df_status.to_parquet(f"{DATA_DIR}/status_dispositivos.parquet", index=False)
    print(f"Status salvo para {len(df_status)} dispositivos")

    return df_telemetria, df_status, unidades_df, alarmes_df
