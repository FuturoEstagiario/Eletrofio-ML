import numpy as np
import pandas as pd
from src.config import WINDOW_POINTS, STRIDE_POINTS


def extrair_features_janela(temp, degelo, setpoint, onoff):
    features = {}

    if not temp or all(v is None for v in temp):
        return None

    temp_arr = np.array(temp, dtype=float)
    temp_arr = np.nan_to_num(temp_arr, nan=np.nanmean(temp_arr))

    setpoint_arr = np.array(setpoint, dtype=float) if setpoint else np.full_like(temp_arr, np.nan)
    if len(setpoint_arr) > 0:
        setpoint_arr = np.nan_to_num(setpoint_arr, nan=np.nanmean(setpoint_arr))

    degelo_arr = np.array(degelo, dtype=float) if degelo else np.zeros_like(temp_arr)
    onoff_arr = np.array(onoff, dtype=float) if onoff else np.ones_like(temp_arr)

    min_len = min(len(temp_arr), len(setpoint_arr), len(degelo_arr), len(onoff_arr))
    if min_len > 0:
        temp_arr = temp_arr[:min_len]
        setpoint_arr = setpoint_arr[:min_len]
        degelo_arr = degelo_arr[:min_len]
        onoff_arr = onoff_arr[:min_len]

    features["temp_mean"] = np.mean(temp_arr)
    features["temp_std"] = np.std(temp_arr)
    features["temp_min"] = np.min(temp_arr)
    features["temp_max"] = np.max(temp_arr)
    features["temp_amplitude"] = features["temp_max"] - features["temp_min"]
    features["temp_mediana"] = np.median(temp_arr)
    features["temp_p25"] = np.percentile(temp_arr, 25)
    features["temp_p75"] = np.percentile(temp_arr, 75)

    diff = np.diff(temp_arr)
    features["temp_taxa_variacao_media"] = np.mean(diff) if len(diff) > 0 else 0.0
    features["temp_taxa_variacao_max"] = np.max(np.abs(diff)) if len(diff) > 0 else 0.0
    features["temp_taxa_variacao_std"] = np.std(diff) if len(diff) > 0 else 0.0

    erro = temp_arr - setpoint_arr
    features["temp_erro_medio"] = np.mean(erro)
    features["temp_erro_std"] = np.std(erro)
    features["temp_acima_setpoint"] = np.mean(erro > 0)
    features["temp_acima_5c"] = np.mean(temp_arr > features["temp_mediana"] + 5)

    n = len(degelo_arr)
    if n > 1:
        degelo_binary = (degelo_arr > 0.5).astype(int)
        transicoes = np.diff(degelo_binary, prepend=0)
        inicios = np.where(transicoes == 1)[0]
        fins = np.where(transicoes == -1)[0]
        ciclos_degelo = min(len(inicios), len(fins))
        features["degelo_num_ciclos"] = ciclos_degelo
        if ciclos_degelo > 0:
            duracoes = []
            for idx in range(ciclos_degelo):
                duracoes.append(fins[idx] - inicios[idx])
            features["degelo_duracao_media"] = np.mean(duracoes)
        else:
            features["degelo_duracao_media"] = 0.0
        features["degelo_tempo_total"] = np.sum(degelo_binary)
        features["degelo_fracao"] = np.mean(degelo_binary)
    else:
        features["degelo_num_ciclos"] = 0
        features["degelo_duracao_media"] = 0.0
        features["degelo_tempo_total"] = 0
        features["degelo_fracao"] = 0.0

    if n > 1:
        onoff_binary = (onoff_arr > 0.5).astype(int)
        transicoes = np.diff(onoff_binary, prepend=0)
        inicios = np.where(transicoes == 1)[0]
        fins = np.where(transicoes == -1)[0]
        ciclos_onoff = min(len(inicios), len(fins))
        features["onoff_num_ciclos"] = ciclos_onoff
        if ciclos_onoff > 0:
            duracoes_on = []
            for idx in range(ciclos_onoff):
                duracoes_on.append(fins[idx] - inicios[idx])
            features["onoff_duracao_media"] = np.mean(duracoes_on)
        else:
            features["onoff_duracao_media"] = 0.0
        features["onoff_fracao_ligado"] = np.mean(onoff_binary)
    else:
        features["onoff_num_ciclos"] = 0
        features["onoff_duracao_media"] = 0.0
        features["onoff_fracao_ligado"] = 0.0

    for k, v in features.items():
        if isinstance(v, float) and np.isnan(v):
            features[k] = 0.0

    return features


def gerar_janelas(series_dict, window=WINDOW_POINTS, stride=STRIDE_POINTS):
    n = len(series_dict.get("temp", []))
    if n < window:
        return []
    janelas = []
    for inicio in range(0, n - window + 1, stride):
        fim = inicio + window
        fatia = {
            k: v[inicio:fim] if isinstance(v, list) else v
            for k, v in series_dict.items()
        }
        janelas.append((inicio, fim, fatia))
    return janelas


def processar_dispositivo(df_device):
    temp = df_device["temp"].tolist()
    degelo = df_device["degelo"].tolist()
    setpoint = df_device["setpoint"].tolist()
    onoff = df_device["onoff"].tolist()

    series_dict = {"temp": temp, "degelo": degelo, "setpoint": setpoint, "onoff": onoff}
    janelas = gerar_janelas(series_dict)

    registros = []
    for inicio, fim, fatia in janelas:
        feats = extrair_features_janela(
            fatia["temp"], fatia["degelo"], fatia["setpoint"], fatia["onoff"]
        )
        if feats is not None:
            feats["dispositivoId"] = df_device["dispositivoId"].iloc[0]
            feats["janela_inicio"] = inicio
            feats["janela_fim"] = fim
            registros.append(feats)
    return registros


def processar_todos(df_telemetria):
    df_telemetria = df_telemetria.sort_values(["dispositivoId", "indice"])
    todos_registros = []

    for did, grp in df_telemetria.groupby("dispositivoId"):
        grp = grp.sort_values("indice")
        registros = processar_dispositivo(grp)
        todos_registros.extend(registros)

    if not todos_registros:
        return pd.DataFrame()

    df_features = pd.DataFrame(todos_registros)
    return df_features


def get_feature_columns(df):
    exclude = {"dispositivoId", "janela_inicio", "janela_fim", "anomalo", "tem_alarme", "num_alarmes"}
    return [c for c in df.columns if c not in exclude]
