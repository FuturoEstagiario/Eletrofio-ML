# -*- coding: utf-8 -*-
import numpy as np
from src.api_preprocessor import processar_alarmes
from src.data_collector import parse_telemetria
from src.features import processar_dispositivo
from src.config import SERIES_MAP, CRITICIDADE_SCORE

CRIT_ORDER = {"C": 0, "A": 1, "M": 2, "B": 3, "I": 4}
CRIT_COLORS = {"C": "#ef4444", "A": "#f97316", "M": "#eab308", "B": "#3b82f6", "I": "#94a3b8"}
CRIT_LABELS = {"C": "Crítica", "A": "Alta", "M": "Média", "B": "Baixa", "I": "Info"}


def _last_features(feat_list: list[dict]) -> dict:
    if not feat_list:
        return {}
    return feat_list[-1]


def _early_warnings(feats: dict) -> list[str]:
    warns = []
    tendencia   = feats.get("temp_taxa_variacao_media", 0) or 0
    degelo_pct  = (feats.get("degelo_fracao", 0) or 0) * 100
    temp_erro   = feats.get("temp_erro_medio", 0) or 0
    temp_std    = feats.get("temp_std", 0) or 0

    if tendencia > 0.08:
        warns.append("temp_subindo")
    if degelo_pct > 30:
        warns.append("degelo_elevado")
    if temp_erro > 5 and tendencia > 0:
        warns.append("acima_setpoint")
    if temp_std > 2.5:
        warns.append("temp_instavel")
    return warns


def risco_tabela(alarmes_raw: list[dict], tele_features: dict, modelos: dict) -> list[dict]:
    if not alarmes_raw:
        return []

    raw_map = {a.get("dispositivoId"): a for a in alarmes_raw}
    resultado = []

    # Quando tele_features ainda não carregou, itera sobre alarmes (dados parciais sem scores)
    if tele_features:
        device_source = [(did, feat_list) for did, feat_list in tele_features.items() if raw_map.get(did)]
    else:
        device_source = [
            (raw.get("dispositivoId"), [])
            for raw in alarmes_raw
            if raw.get("dispositivoId") is not None
        ]

    for did, feat_list in device_source:
        raw = raw_map.get(did, {})
        if not raw:
            continue

        feats = _last_features(feat_list)
        crit = raw.get("criticidade", "I")

        temp_atual = feats.get("temp_mean")
        temp_erro = feats.get("temp_erro_medio")
        temp_std = feats.get("temp_std")
        degelo_fracao = feats.get("degelo_fracao") or 0.0

        risk_score = None
        if modelos.get("rf") is not None:
            try:
                feature_cols = [
                    "temp_media", "temp_maxima", "temp_minima", "temp_amplitude",
                    "temp_volatilidade", "temp_tendencia",
                ]
                mapped = {
                    "temp_media": feats.get("temp_mean", 0),
                    "temp_maxima": feats.get("temp_max", 0),
                    "temp_minima": feats.get("temp_min", 0),
                    "temp_amplitude": feats.get("temp_amplitude", 0),
                    "temp_volatilidade": feats.get("temp_std", 0),
                    "temp_tendencia": feats.get("temp_taxa_variacao_media", 0),
                }
                row_vals = [mapped[c] for c in feature_cols]
                X = np.array(row_vals).reshape(1, -1)
                risk_score = round(float(modelos["rf"].predict_proba(X)[0]), 4)
            except Exception:
                risk_score = None

        if risk_score is None and modelos.get("ocsvm") is not None:
            try:
                feat_keys = modelos["ocsvm"].feature_cols
                if feat_keys:
                    row_vals = [feats.get(c, 0.0) for c in feat_keys]
                    X = np.array(row_vals).reshape(1, -1)
                    X = np.nan_to_num(X, nan=0.0)
                    decision = modelos["ocsvm"].decision_function(X)[0]
                    risk_score = round(float(1 / (1 + np.exp(-decision))), 4)
            except Exception:
                risk_score = None

        resultado.append({
            "dispositivo_id": int(did),
            "dispositivo_nome": raw.get("dispositivoNm", ""),
            "loja_id": int(raw.get("lojaId", 0)),
            "loja_nome": raw.get("lojaNm", ""),
            "criticidade": crit,
            "crit_label": CRIT_LABELS.get(crit, "Info"),
            "crit_color": CRIT_COLORS.get(crit, "#94a3b8"),
            "alarme_desc": raw.get("alarmeDesc", ""),
            "tempo": raw.get("tempo", ""),
            "sem_tratativa": raw.get("eventoDhCad") is None,
            "temp_atual": round(float(temp_atual), 1) if temp_atual is not None else None,
            "temp_erro": round(float(temp_erro), 2) if temp_erro is not None else None,
            "temp_std": round(float(temp_std), 2) if temp_std is not None else None,
            "degelo_fracao": round(float(degelo_fracao) * 100, 1),
            "risk_score": risk_score,
            "alertas": _early_warnings(feats),
        })

    resultado.sort(key=lambda x: CRIT_ORDER.get(x["criticidade"], 99))
    return resultado


def temperatura_series(dispositivo_id: int, tele_series: dict) -> dict | None:
    sd = tele_series.get(dispositivo_id)
    if not sd:
        return None

    labels = sd.get("labels", [])
    temp = sd.get("temp", [])
    setpoint = sd.get("setpoint", [])
    degelo = sd.get("degelo", [])

    if not temp:
        return None

    temp_arr = np.array(temp, dtype=float)
    sp_arr = np.array(setpoint, dtype=float) if setpoint else np.full_like(temp_arr, np.nan)

    temp_arr = np.nan_to_num(temp_arr, nan=0.0)
    sp_arr = np.nan_to_num(sp_arr, nan=np.nanmean(sp_arr) if np.any(~np.isnan(sp_arr)) else 0.0)

    band_upper = (sp_arr + 2).tolist()
    band_lower = (sp_arr - 2).tolist()

    anomaly_flags = [
        1 if (t > sp + 2) else 0
        for t, sp in zip(temp_arr.tolist(), sp_arr.tolist())
    ]

    pct_acima = float(np.mean(temp_arr > sp_arr)) if len(sp_arr) > 0 else 0.0

    return {
        "labels": labels,
        "temp": temp_arr.tolist(),
        "setpoint": sp_arr.tolist(),
        "degelo": [v if v is not None else 0 for v in degelo],
        "band_upper": band_upper,
        "band_lower": band_lower,
        "anomaly_flags": anomaly_flags,
        "stats": {
            "temp_mean": round(float(np.mean(temp_arr)), 1),
            "temp_max": round(float(np.max(temp_arr)), 1),
            "temp_min": round(float(np.min(temp_arr)), 1),
            "temp_std": round(float(np.std(temp_arr)), 2),
            "temp_p25": round(float(np.percentile(temp_arr, 25)), 1),
            "temp_p75": round(float(np.percentile(temp_arr, 75)), 1),
            "sp_mean": round(float(np.mean(sp_arr)), 1),
            "pct_acima_sp": round(pct_acima * 100, 1),
        },
    }


def alarmes_por_loja(alarmes_raw: list[dict]) -> dict:
    if not alarmes_raw:
        return {
            "top_lojas": [],
            "matrix": {},
            "totais_por_crit": {},
            "sem_tratativa": 0,
        }

    loja_map: dict[str, dict] = {}
    sem_tratativa_total = 0

    for a in alarmes_raw:
        loja = a.get("lojaNm", "")
        crit = a.get("criticidade", "I")
        sem_trat = a.get("eventoDhCad") is None

        if loja not in loja_map:
            loja_map[loja] = {"nome": loja, "total": 0, "sem_trat": 0,
                              "C": 0, "A": 0, "M": 0, "B": 0, "I": 0}
        loja_map[loja]["total"] += 1
        loja_map[loja][crit] = loja_map[loja].get(crit, 0) + 1
        if sem_trat:
            loja_map[loja]["sem_trat"] += 1
            sem_tratativa_total += 1

    sorted_lojas = sorted(loja_map.values(), key=lambda x: x["total"], reverse=True)[:15]

    totais_por_crit = {"C": 0, "A": 0, "M": 0, "B": 0, "I": 0}
    for a in alarmes_raw:
        crit = a.get("criticidade", "I")
        totais_por_crit[crit] = totais_por_crit.get(crit, 0) + 1

    matrix = {loja["nome"]: {k: loja.get(k, 0) for k in ["C", "A", "M", "B", "I"]}
              for loja in sorted_lojas}

    return {
        "top_lojas": sorted_lojas,
        "matrix": matrix,
        "totais_por_crit": totais_por_crit,
        "sem_tratativa": sem_tratativa_total,
    }


def degelo_analysis(tele_features: dict, alarmes_raw: list[dict]) -> list[dict]:
    raw_map = {a.get("dispositivoId"): a for a in alarmes_raw}
    resultado = []

    for did, feat_list in tele_features.items():
        if not feat_list:
            continue

        feats = _last_features(feat_list)
        fracao = feats.get("degelo_fracao", 0.0)
        ciclos = feats.get("degelo_num_ciclos", 0)
        duracao_media = feats.get("degelo_duracao_media", 0.0)

        raw = raw_map.get(did, {})

        resultado.append({
            "dispositivo_id": int(did),
            "dispositivo_nome": raw.get("dispositivoNm", f"Device {did}"),
            "loja_nome": raw.get("lojaNm", ""),
            "criticidade": raw.get("criticidade", "I"),
            "crit_label": CRIT_LABELS.get(raw.get("criticidade", "I"), "Info"),
            "crit_color": CRIT_COLORS.get(raw.get("criticidade", "I"), "#94a3b8"),
            "degelo_fracao": round(float(fracao) * 100, 1),
            "ciclos_max": int(ciclos),
            "duracao_media_min": round(float(duracao_media) * 5, 1),
            "alerta": float(fracao) > 0.3,
        })

    resultado.sort(key=lambda x: x["degelo_fracao"], reverse=True)
    return resultado


def pressao_devices(tele_features: dict) -> list[dict]:
    resultado = []

    for did, feat_list in tele_features.items():
        if not feat_list:
            continue
        feats = _last_features(feat_list)

        ps = feats.get("pressao_succao_mean")
        if ps is None:
            continue

        pc = feats.get("pressao_cond_mean")
        sup = feats.get("superaquecimento_mean")
        razao = round(float(pc) / float(ps), 2) if pc and ps and float(ps) != 0 else None

        resultado.append({
            "dispositivo_id": int(did),
            "pressao_succao": round(float(ps), 2),
            "pressao_cond": round(float(pc), 2) if pc is not None else None,
            "razao_pressao": razao,
            "superaquecimento": round(float(sup), 1) if sup is not None else None,
        })

    return resultado


def saude_frota(alarmes_raw: list[dict], tele_features: dict, modelos: dict) -> dict:
    devices = risco_tabela(alarmes_raw, tele_features, modelos)
    total = len(devices)

    if total == 0:
        return {"total": 0, "n_critico": 0, "n_atencao": 0, "n_normal": 0,
                "pct_critico": 0, "pct_atencao": 0, "pct_normal": 0,
                "avg_score": None, "por_crit": {}, "por_loja": [], "top10": []}

    por_crit: dict[str, int] = {}
    for d in devices:
        c = d.get("criticidade", "I")
        por_crit[c] = por_crit.get(c, 0) + 1

    n_critico = por_crit.get("C", 0)
    n_atencao = por_crit.get("A", 0) + por_crit.get("M", 0)
    n_normal  = por_crit.get("B", 0) + por_crit.get("I", 0)

    scores = [d["risk_score"] for d in devices if d.get("risk_score") is not None]
    avg_score = round(sum(scores) / len(scores) * 100, 1) if scores else None

    loja_map: dict[str, dict] = {}
    for d in devices:
        loja = d.get("loja_nome") or "—"
        if loja not in loja_map:
            loja_map[loja] = {"nome": loja, "total": 0, "criticos": 0, "scores": []}
        loja_map[loja]["total"] += 1
        if d.get("criticidade") == "C":
            loja_map[loja]["criticos"] += 1
        if d.get("risk_score") is not None:
            loja_map[loja]["scores"].append(d["risk_score"])

    por_loja = []
    for info in sorted(loja_map.values(), key=lambda x: -x["criticos"]):
        s = info["scores"]
        por_loja.append({
            "nome": info["nome"],
            "total": info["total"],
            "criticos": info["criticos"],
            "score_medio": round(sum(s) / len(s) * 100, 1) if s else 0,
        })

    top10 = sorted(
        devices,
        key=lambda d: (CRIT_ORDER.get(d["criticidade"], 99), -(d["risk_score"] or 0))
    )[:10]

    return {
        "total":       total,
        "n_critico":   n_critico,
        "n_atencao":   n_atencao,
        "n_normal":    n_normal,
        "pct_critico": round(n_critico / total * 100, 1),
        "pct_atencao": round(n_atencao / total * 100, 1),
        "pct_normal":  round(n_normal  / total * 100, 1),
        "avg_score":   avg_score,
        "por_crit":    por_crit,
        "por_loja":    por_loja[:20],
        "top10":       top10,
    }


CUSTO_HORA = {"C": 3_500, "A": 1_500, "M": 800, "B": 300, "I": 80}
CUSTO_INTERVENCAO = 450


def financeiro_impacto(alarmes_raw: list[dict], tele_features: dict, modelos: dict) -> dict:
    devices = risco_tabela(alarmes_raw, tele_features, modelos)

    if not devices:
        return {
            "total_exposicao_diaria": 0, "total_exposicao_semanal": 0,
            "devices_urgentes": 0, "devices_recomendados": 0,
            "economia_potencial_diaria": 0, "custo_total_intervencao": 0,
            "roi_medio": 0, "por_recomendacao": {}, "por_loja": [],
            "assumpcoes": {"custo_hora": CUSTO_HORA, "custo_intervencao": CUSTO_INTERVENCAO},
            "devices": [],
        }

    resultado = []
    por_loja_map: dict[str, dict] = {}
    rec_counts: dict[str, int] = {"Urgente": 0, "Recomendado": 0, "Monitorar": 0, "Normal": 0}

    for d in devices:
        crit = d.get("criticidade", "I")
        score = d.get("risk_score") or 0.0

        custo_h = CUSTO_HORA.get(crit, 80)
        exp_h = round(custo_h * score, 2)
        exp_d = round(exp_h * 24, 2)
        exp_w = round(exp_d * 7, 2)
        roi = round(exp_d / CUSTO_INTERVENCAO, 1) if exp_d > 0 else 0.0
        eco_d = round(exp_d - CUSTO_INTERVENCAO, 2)

        if roi >= 50:
            rec = "Urgente"
        elif roi >= 10:
            rec = "Recomendado"
        elif roi >= 2:
            rec = "Monitorar"
        else:
            rec = "Normal"

        rec_counts[rec] += 1

        loja = d.get("loja_nome") or "—"
        if loja not in por_loja_map:
            por_loja_map[loja] = {"nome": loja, "total_exposicao_diaria": 0.0, "devices_urgentes": 0, "devices": 0}
        por_loja_map[loja]["total_exposicao_diaria"] += exp_d
        por_loja_map[loja]["devices"] += 1
        if rec == "Urgente":
            por_loja_map[loja]["devices_urgentes"] += 1

        resultado.append({
            "dispositivo_id": d["dispositivo_id"],
            "dispositivo_nome": d.get("dispositivo_nome", ""),
            "loja_nome": loja,
            "criticidade": crit,
            "crit_label": d.get("crit_label", ""),
            "crit_color": d.get("crit_color", "#94a3b8"),
            "risk_score": score,
            "exposicao_hora": exp_h,
            "exposicao_diaria": exp_d,
            "exposicao_semanal": exp_w,
            "custo_intervencao": CUSTO_INTERVENCAO,
            "roi": roi,
            "economia_diaria": eco_d,
            "recomendacao": rec,
        })

    resultado.sort(key=lambda x: -x["exposicao_diaria"])

    total_exp_d = sum(d["exposicao_diaria"] for d in resultado)
    recomendados = [d for d in resultado if d["recomendacao"] in ("Urgente", "Recomendado")]
    eco_pot = sum(d["economia_diaria"] for d in recomendados if d["economia_diaria"] > 0)
    custo_tot = len(recomendados) * CUSTO_INTERVENCAO
    rois = [d["roi"] for d in resultado if d["roi"] > 0]
    roi_medio = round(sum(rois) / len(rois), 1) if rois else 0.0

    por_loja = sorted(
        [
            {
                "nome": v["nome"],
                "total_exposicao_diaria": round(v["total_exposicao_diaria"], 2),
                "devices_urgentes": v["devices_urgentes"],
                "devices": v["devices"],
            }
            for v in por_loja_map.values()
        ],
        key=lambda x: -x["total_exposicao_diaria"],
    )

    return {
        "total_exposicao_diaria": round(total_exp_d, 2),
        "total_exposicao_semanal": round(total_exp_d * 7, 2),
        "devices_urgentes": rec_counts["Urgente"],
        "devices_recomendados": rec_counts["Urgente"] + rec_counts["Recomendado"],
        "economia_potencial_diaria": round(eco_pot, 2),
        "custo_total_intervencao": round(custo_tot, 2),
        "roi_medio": roi_medio,
        "por_recomendacao": rec_counts,
        "por_loja": por_loja[:15],
        "assumpcoes": {
            "custo_hora": CUSTO_HORA,
            "custo_intervencao": CUSTO_INTERVENCAO,
        },
        "devices": resultado,
    }


def pressao_series(dispositivo_id: int, tele_series: dict) -> dict | None:
    sd = tele_series.get(dispositivo_id)
    if not sd:
        return None

    ps_raw = sd.get("pressao_succao", [])
    pc_raw = sd.get("pressao_cond", [])
    sup_raw = sd.get("superaquecimento", [])
    labels = sd.get("labels", [])

    if not ps_raw:
        return None

    ps_arr = np.array(ps_raw, dtype=float)
    pc_arr = np.array(pc_raw, dtype=float) if pc_raw else np.full_like(ps_arr, np.nan)
    sup_arr = np.array(sup_raw, dtype=float) if sup_raw else np.full_like(ps_arr, np.nan)

    ps_arr = np.nan_to_num(ps_arr, nan=0.0)

    razao = np.where(ps_arr != 0, pc_arr / ps_arr, np.nan)

    def safe_mean(arr):
        valid = arr[~np.isnan(arr)]
        return round(float(np.mean(valid)), 2) if len(valid) > 0 else None

    def safe_list(arr):
        return [None if np.isnan(v) else round(float(v), 3) for v in arr]

    return {
        "labels": labels,
        "pressao_succao": safe_list(ps_arr),
        "pressao_cond": safe_list(pc_arr),
        "razao_pressao": safe_list(razao),
        "superaquecimento": safe_list(sup_arr),
        "stats": {
            "ps_mean": safe_mean(ps_arr),
            "pc_mean": safe_mean(pc_arr),
            "razao_mean": safe_mean(razao),
            "sup_mean": safe_mean(sup_arr),
        },
    }
