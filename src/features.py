import numpy as np
import pandas as pd
from src.config import WINDOW_POINTS, STRIDE_POINTS, SERIES_MAP


def _arr(series_dict, key, fallback_keys=None):
    vals = series_dict.get(key, [])
    if vals and not all(v is None for v in vals):
        arr = np.array(vals, dtype=float)
        if not np.all(np.isnan(arr)):
            return arr
    if fallback_keys:
        for fk in fallback_keys:
            fvals = series_dict.get(fk, [])
            if fvals and not all(v is None for v in fvals):
                arr = np.array(fvals, dtype=float)
                if not np.all(np.isnan(arr)):
                    return arr
    return None


def _safe_mean(arr):
    m = np.nanmean(arr)
    return float(m) if not np.isnan(m) else 0.0


def _cycles(binary_arr):
    transicoes = np.diff(binary_arr, prepend=0)
    inicios = np.where(transicoes == 1)[0]
    fins = np.where(transicoes == -1)[0]
    ciclos = min(len(inicios), len(fins))
    duracao_media = float(np.mean([fins[i] - inicios[i] for i in range(ciclos)])) if ciclos > 0 else 0.0
    return ciclos, duracao_media


def extrair_features_janela(series_dict):
    features = {}

    temp_raw = _arr(series_dict, "temp", ["temp_succao", "temp_evap"])
    if temp_raw is None:
        return None

    temp_mean_val = _safe_mean(temp_raw)
    temp_arr = np.nan_to_num(temp_raw, nan=temp_mean_val)

    setpoint_raw = _arr(series_dict, "setpoint", ["setpoint_succao"])
    if setpoint_raw is not None:
        setpoint_arr = np.nan_to_num(setpoint_raw, nan=_safe_mean(setpoint_raw))
    else:
        setpoint_arr = np.full_like(temp_arr, temp_mean_val)

    degelo_raw = _arr(series_dict, "degelo", ["rele_degelo"])
    degelo_arr = np.nan_to_num(degelo_raw, nan=0.0) if degelo_raw is not None else np.zeros_like(temp_arr)

    onoff_raw = _arr(series_dict, "onoff")
    onoff_arr = np.nan_to_num(onoff_raw, nan=1.0) if onoff_raw is not None else np.ones_like(temp_arr)

    min_len = min(len(temp_arr), len(setpoint_arr), len(degelo_arr), len(onoff_arr))
    temp_arr = temp_arr[:min_len]
    setpoint_arr = setpoint_arr[:min_len]
    degelo_arr = degelo_arr[:min_len]
    onoff_arr = onoff_arr[:min_len]

    features["temp_mean"] = float(np.mean(temp_arr))
    features["temp_std"] = float(np.std(temp_arr))
    features["temp_min"] = float(np.min(temp_arr))
    features["temp_max"] = float(np.max(temp_arr))
    features["temp_amplitude"] = features["temp_max"] - features["temp_min"]
    features["temp_mediana"] = float(np.median(temp_arr))
    features["temp_p25"] = float(np.percentile(temp_arr, 25))
    features["temp_p75"] = float(np.percentile(temp_arr, 75))

    diff = np.diff(temp_arr)
    features["temp_taxa_variacao_media"] = float(np.mean(diff)) if len(diff) > 0 else 0.0
    features["temp_taxa_variacao_max"] = float(np.max(np.abs(diff))) if len(diff) > 0 else 0.0
    features["temp_taxa_variacao_std"] = float(np.std(diff)) if len(diff) > 0 else 0.0

    erro = temp_arr - setpoint_arr
    features["temp_erro_medio"] = float(np.mean(erro))
    features["temp_erro_std"] = float(np.std(erro))
    features["temp_acima_setpoint"] = float(np.mean(erro > 0))
    features["temp_acima_5c"] = float(np.mean(temp_arr > features["temp_mediana"] + 5))

    if min_len > 1:
        degelo_bin = (degelo_arr > 0.5).astype(int)
        ciclos_d, dur_d = _cycles(degelo_bin)
        features["degelo_num_ciclos"] = ciclos_d
        features["degelo_duracao_media"] = dur_d
        features["degelo_tempo_total"] = int(np.sum(degelo_bin))
        features["degelo_fracao"] = float(np.mean(degelo_bin))

        onoff_bin = (onoff_arr > 0.5).astype(int)
        ciclos_o, dur_o = _cycles(onoff_bin)
        features["onoff_num_ciclos"] = ciclos_o
        features["onoff_duracao_media"] = dur_o
        features["onoff_fracao_ligado"] = float(np.mean(onoff_bin))
    else:
        features.update({
            "degelo_num_ciclos": 0, "degelo_duracao_media": 0.0,
            "degelo_tempo_total": 0, "degelo_fracao": 0.0,
            "onoff_num_ciclos": 0, "onoff_duracao_media": 0.0,
            "onoff_fracao_ligado": 0.0,
        })

    ps = _arr(series_dict, "pressao_succao")
    pc = _arr(series_dict, "pressao_cond")
    if ps is not None and pc is not None:
        ps = np.nan_to_num(ps[:min_len], nan=_safe_mean(ps))
        pc = np.nan_to_num(pc[:min_len], nan=_safe_mean(pc))
        with np.errstate(divide="ignore", invalid="ignore"):
            razao = np.where(ps > 0, pc / ps, 0.0)
        features["razao_pressao_mean"] = float(np.mean(razao))
        features["razao_pressao_std"] = float(np.std(razao))
        features["pressao_succao_mean"] = float(np.mean(ps))
        features["pressao_cond_mean"] = float(np.mean(pc))

    ts = _arr(series_dict, "temp_succao")
    if ts is not None:
        ts = np.nan_to_num(ts[:min_len], nan=_safe_mean(ts))
        features["temp_succao_mean"] = float(np.mean(ts))
        features["temp_succao_std"] = float(np.std(ts))

    sup = _arr(series_dict, "superaquecimento")
    if sup is not None:
        sup = np.nan_to_num(sup[:min_len], nan=_safe_mean(sup))
        features["superaquecimento_mean"] = float(np.mean(sup))
        features["superaquecimento_std"] = float(np.std(sup))

    te = _arr(series_dict, "temp_evap")
    if te is not None:
        te = np.nan_to_num(te[:min_len], nan=_safe_mean(te))
        features["temp_evap_mean"] = float(np.mean(te))

    val = _arr(series_dict, "abertura_valvula")
    if val is not None:
        val = np.nan_to_num(val[:min_len], nan=_safe_mean(val))
        features["valvula_mean"] = float(np.mean(val))
        features["valvula_std"] = float(np.std(val))

    comp_arrays = [_arr(series_dict, k) for k in ["comp1_on", "comp2_on", "comp3_on", "comp4_on", "comp5_on"]]
    comp_valid = [np.nan_to_num(a[:min_len], nan=0.0) for a in comp_arrays if a is not None]
    if comp_valid:
        stack = np.stack(comp_valid, axis=1)
        features["comp_fracao_ativos"] = float(np.mean(stack))
        features["comp_num_max"] = int(np.max(np.sum(stack > 0.5, axis=1)))

    for k, v in features.items():
        if isinstance(v, float) and np.isnan(v):
            features[k] = 0.0

    return features


def gerar_janelas(series_dict, window=WINDOW_POINTS, stride=STRIDE_POINTS):
    lengths = [len(v) for v in series_dict.values() if isinstance(v, list) and v]
    n = max(lengths) if lengths else 0
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
    series_dict = {
        col: df_device[col].tolist()
        for col in SERIES_MAP.values()
        if col in df_device.columns
    }

    if not series_dict:
        return []

    janelas = gerar_janelas(series_dict)
    registros = []
    for inicio, fim, fatia in janelas:
        feats = extrair_features_janela(fatia)
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
