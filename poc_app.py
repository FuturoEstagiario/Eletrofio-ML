# -*- coding: utf-8 -*-
"""
EletroFrio ML — Prova de Conceito (PoC)
========================================
Dashboard web que consome os 4 endpoints da Eletrofrio:
  - ?route=alarmes           → indicadores de criticidade
  - ?route=unidades          → mapa de lojas/unidades
  - ?route=telemetria        → série temporal de temperatura (carregada via JS)
  - ?route=abrir-chamado     → abertura de chamado técnico (via botão manual)

Uso:
    python poc_app.py              # http://localhost:5000
    python poc_app.py --port 8080
"""

import argparse
import logging
import os
import sys
import time
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='[EF] %(asctime)s %(levelname)s — %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stderr,
    force=True,
)
log = logging.getLogger('eletrofio')

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request
from whitenoise import WhiteNoise
from src.api_client import buscar_alarmes, buscar_unidades, buscar_telemetria, abrir_chamado
from src.api_preprocessor import processar_alarmes, _extrair_features_telemetria
from src.data_collector import parse_telemetria
from src.features import processar_dispositivo
from src.config import SERIES_MAP
from src.dashboard_service import (
    risco_tabela, temperatura_series, alarmes_por_loja,
    degelo_analysis, pressao_devices, pressao_series,
    saude_frota, financeiro_impacto,
)

# ── Carregamento de modelos (tolerante a falhas) ──────────────────────────
_modelos = {"rf": None, "ocsvm": None}
_modelos_carregados = False

try:
    from src.models import RandomForestModel, OneClassSVMModel
    from src.config import MODELS_DIR
    _modelos["rf"] = RandomForestModel.carregar(f"{MODELS_DIR}/rf_eletrofrio.pkl")
    log.info("MODELO Random Forest carregado")
    _modelos_carregados = True
except Exception as _e:
    log.warning(f"MODELO Random Forest nao encontrado: {_e}")

try:
    if _modelos["ocsvm"] is None:
        _modelos["ocsvm"] = OneClassSVMModel.carregar(MODELS_DIR)
    log.info("MODELO OneClassSVM carregado")
    _modelos_carregados = True
except Exception as _e:
    log.warning(f"MODELO OneClassSVM nao encontrado: {_e}")


app = Flask(__name__, template_folder="views", static_folder="views")
app.wsgi_app = WhiteNoise(app.wsgi_app, root="views/", prefix="static")

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_PARQUET_DIR = os.path.join(_BASE_DIR, "dados_coletados")

log.info(f"BASE_DIR    : {_BASE_DIR}")
log.info(f"PARQUET_DIR : {_PARQUET_DIR}")
log.info(f"alarmes.parquet  existe: {os.path.exists(os.path.join(_PARQUET_DIR, 'alarmes.parquet'))}")
log.info(f"unidades.parquet existe: {os.path.exists(os.path.join(_PARQUET_DIR, 'unidades.parquet'))}")

_cache = {
    "alarmes_raw": [], "unidades": [],
    "tele_features": {},
    "tele_series": {},
    "chamados_log": [],
    "ts": time.time(), "ts_tele": None,
    "api_ok": False,
    "data_ok": False,
}
CACHE_TTL = 600


def _fetch_background():
    while True:
        log.info("══ início do ciclo de cache ══")
        try:
            log.info("Buscando alarmes da API...")
            _cache["alarmes_raw"] = buscar_alarmes()
            _cache["api_ok"] = True
            _cache["data_ok"] = True
            log.info(f"API alarmes OK — {len(_cache['alarmes_raw'])} registos")
        except Exception as e:
            log.error(f"API alarmes ERRO: {type(e).__name__}: {e}")
            _cache["api_ok"] = False
            parquet_path = os.path.join(_PARQUET_DIR, "alarmes.parquet")
            log.info(f"Tentando fallback parquet: {parquet_path}")
            try:
                df = pd.read_parquet(parquet_path)
                _cache["alarmes_raw"] = df.where(pd.notnull(df), None).to_dict("records")
                _cache["data_ok"] = True
                log.info(f"Parquet alarmes OK — {len(_cache['alarmes_raw'])} registos")
            except Exception as pe:
                log.error(f"Parquet alarmes ERRO: {type(pe).__name__}: {pe}")
                _cache["data_ok"] = False

        try:
            log.info("Buscando unidades da API...")
            _cache["unidades"] = buscar_unidades()
            log.info(f"API unidades OK — {len(_cache['unidades'])} registos")
        except Exception as e:
            log.error(f"API unidades ERRO: {type(e).__name__}: {e}")
            parquet_path = os.path.join(_PARQUET_DIR, "unidades.parquet")
            log.info(f"Tentando fallback parquet: {parquet_path}")
            try:
                df = pd.read_parquet(parquet_path)
                _cache["unidades"] = df.where(pd.notnull(df), None).to_dict("records")
                log.info(f"Parquet unidades OK — {len(_cache['unidades'])} registos")
            except Exception as pe:
                log.error(f"Parquet unidades ERRO: {type(pe).__name__}: {pe}")

        _cache["ts"] = time.time()
        log.info(
            f"Cache actualizado — api_ok={_cache['api_ok']} data_ok={_cache['data_ok']} "
            f"alarmes={len(_cache['alarmes_raw'])} unidades={len(_cache['unidades'])}"
        )

        _PRIO = {"C": 0, "A": 1, "M": 2, "B": 3, "I": 4}
        _sorted = sorted(_cache["alarmes_raw"], key=lambda a: _PRIO.get(a.get("criticidade", "I"), 99))
        device_ids = list(dict.fromkeys(a.get("dispositivoId") for a in _sorted if a.get("dispositivoId")))[:30]
        log.info(f"Telemetria: {len(device_ids)} devices a buscar")
        for did in device_ids:
            try:
                raw = buscar_telemetria(did)
                df_tele = parse_telemetria(did, raw)
                if df_tele is not None:
                    sd = {"labels": df_tele["timestamp_label"].tolist()}
                    for col in SERIES_MAP.values():
                        if col in df_tele.columns:
                            sd[col] = df_tele[col].tolist()
                    _cache["tele_series"][did] = sd
                    _cache["tele_features"][did] = processar_dispositivo(df_tele)
            except Exception as te:
                log.warning(f"Telemetria device {did} ERRO: {type(te).__name__}: {te}")
            time.sleep(0.15)
        _cache["ts_tele"] = time.time()
        log.info(f"Telemetria concluída — {len(_cache['tele_features'])} devices com features")
        log.info(f"Próximo ciclo em {CACHE_TTL}s")

        time.sleep(CACHE_TTL)


_bg = threading.Thread(target=_fetch_background, daemon=True)
_bg.start()

# ── Configuração de criticidade ───────────────────────────────────────────────

CRIT_CONFIG = {
    "C": {"label": "Crítica",  "color": "#dc3545"},
    "A": {"label": "Alta",     "color": "#fd7e14"},
    "M": {"label": "Média",    "color": "#ffc107"},
    "B": {"label": "Baixa",    "color": "#0d6efd"},
    "I": {"label": "Info",     "color": "#6c757d"},
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _computar_stats(df):
    por_crit = {
        k: {
            "count": int((df["criticidade"] == k).sum()) if not df.empty else 0,
            "label": cfg["label"],
            "color": cfg["color"],
        }
        for k, cfg in CRIT_CONFIG.items()
    }

    top_lojas = []
    if not df.empty and "loja_nome" in df.columns:
        grp = df.groupby("loja_nome")
        resumo = grp.size().rename("total").reset_index()
        resumo["criticos"] = grp["criticidade"].apply(lambda s: int((s == "C").sum())).values
        resumo["sem_trat"] = grp["sem_tratativa"].sum().astype(int).values
        resumo = resumo.sort_values("total", ascending=False).head(8)
        top_lojas = [
            {
                "nome":     row["loja_nome"],
                "total":    int(row["total"]),
                "criticos": int(row["criticos"]),
                "sem_trat": int(row["sem_trat"]),
            }
            for _, row in resumo.iterrows()
        ]

    return {
        "total":         len(df),
        "por_crit":      por_crit,
        "sem_tratativa": int(df["sem_tratativa"].sum()) if not df.empty else 0,
        "top_lojas":     top_lojas,
    }


def _preparar_linhas(df, alarmes_raw):
    ordem = {"C": 0, "A": 1, "M": 2, "B": 3, "I": 4}
    raw_map = {a.get("dispositivoId"): a for a in alarmes_raw}
    linhas = []
    for _, row in df.iterrows():
        crit = row.get("criticidade", "I")
        raw  = raw_map.get(row.get("dispositivo_id"), {})
        linhas.append({
            "dispositivo_id": int(row.get("dispositivo_id", 0)),
            "loja_id":        int(row.get("loja_id", 0)),
            "criticidade":    crit,
            "crit_label":     CRIT_CONFIG.get(crit, CRIT_CONFIG["I"])["label"],
            "loja_nome":      row.get("loja_nome", ""),
            "tag":            row.get("tag", ""),
            "alarme_desc":    row.get("alarme_desc", ""),
            "tempo":          raw.get("tempo", ""),
            "sem_tratativa":  bool(row.get("sem_tratativa", 0)),
        })
    linhas.sort(key=lambda x: ordem.get(x["criticidade"], 99))
    return linhas


# ── Rotas — Dashboard ─────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    import pandas as pd
    alarmes_raw = _cache["alarmes_raw"]
    unidades    = _cache["unidades"]
    erros       = {} if _cache.get("data_ok") else {"status": "Carregando dados da API, aguarde e recarregue em instantes..."}
    df = processar_alarmes(alarmes_raw) if alarmes_raw else pd.DataFrame()

    stats        = _computar_stats(df)
    linhas       = _preparar_linhas(df, alarmes_raw)
    chart_labels = [CRIT_CONFIG[k]["label"] for k in CRIT_CONFIG]
    chart_data   = [stats["por_crit"][k]["count"] for k in CRIT_CONFIG]
    chart_colors = [CRIT_CONFIG[k]["color"] for k in CRIT_CONFIG]

    return render_template(
        "index.html",
        stats=stats,
        alarmes=linhas,
        unidades=unidades,
        total_unidades=len(unidades),
        chart_labels=chart_labels,
        chart_data=chart_data,
        chart_colors=chart_colors,
        atualizado=datetime.fromtimestamp(_cache["ts"]).strftime("%d/%m/%Y %H:%M:%S") if _cache["ts"] else "—",
        erros=erros,
    )


# ── Rotas — API JSON ──────────────────────────────────────────────────────────

@app.route("/api/alarmes")
def api_alarmes():
    try:
        dados = buscar_alarmes()
        return jsonify({"status": "ok", "total": len(dados), "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/health")
def api_health():
    """Verifica se a API da Eletrofrio está acessível e se os modelos estão carregados."""
    return jsonify({
        "status": "ok",
        "api": _cache.get("api_ok", False),
        "modelos": {
            "rf": _modelos["rf"] is not None,
            "ocsvm": _modelos["ocsvm"] is not None,
        },
        "modelos_carregados": _modelos_carregados,
        "cache_ts": _cache["ts"],
    })


@app.route("/api/unidades")
def api_unidades():
    try:
        dados = buscar_unidades()
        return jsonify({"status": "ok", "total": len(dados), "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/unidades/<int:loja_id>")
def api_unidade_detalhe(loja_id):
    try:
        dados = buscar_unidades()
        loja = next((u for u in dados if u.get("lojaId") == loja_id), None)
        if loja is None:
            return jsonify({"status": "erro", "mensagem": f"Loja {loja_id} não encontrada"}), 404
        return jsonify({"status": "ok", "dados": loja})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/telemetria/<int:dispositivo_id>")
def api_telemetria(dispositivo_id):
    """Retorna features de temperatura e series completas (temp, degelo, setpoint, onoff)."""
    try:
        raw = buscar_telemetria(dispositivo_id)
        datasets = raw.get("datasets", [])
        if not datasets:
            return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "features": {}})

        from src.api_preprocessor import _extrair_features_telemetria, _extrair_series_telemetria

        features = _extrair_features_telemetria(raw)
        if not features:
            return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "features": {}})

        series = _extrair_series_telemetria(raw)

        temp = series.get("temp", [])
        arr = np.array(temp, dtype=float) if temp else np.array([])

        return jsonify({
            "status": "ok",
            "dispositivo_id": dispositivo_id,
            "features": {
                "temp_media":         round(float(features.get("temp_media", 0)), 1),
                "temp_maxima":        round(float(features.get("temp_maxima", 0)), 1),
                "temp_minima":        round(float(features.get("temp_minima", 0)), 1),
                "temp_amplitude":     round(float(features.get("temp_amplitude", 0)), 1),
                "temp_tendencia":     round(float(features.get("temp_tendencia", 0)), 3),
                "temp_acima_setpoint": round(float(features.get("temp_acima_setpoint", 0)), 3),
                "degelo_fracao":      round(float(features.get("degelo_fracao", 0)), 3),
                "onoff_fracao_ligado": round(float(features.get("onoff_fracao_ligado", 0)), 3),
            },
            "series": {
                "temp":     temp[-96:] if len(temp) > 96 else temp,
                "degelo":   series.get("degelo", [])[-96:],
                "setpoint": series.get("setpoint", [])[-96:],
                "onoff":    series.get("onoff", [])[-96:],
            },
            "labels": raw.get("labels", []),
        })
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/stats")
def api_stats():
    try:
        alarmes_raw = buscar_alarmes()
        df = processar_alarmes(alarmes_raw)
        stats = _computar_stats(df)
        stats["atualizado"] = datetime.now().isoformat()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/predict/<int:dispositivo_id>")
def api_predict(dispositivo_id):
    """Retorna predicao de falha (RF) + deteccao de anomalia (OneClassSVM)."""
    try:
        if not _modelos_carregados or (_modelos["rf"] is None and _modelos["ocsvm"] is None):
            return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "modelos": False})

        raw = buscar_telemetria(dispositivo_id)

        from src.features import extrair_features_janela
        from src.api_preprocessor import _extrair_series_telemetria

        series = _extrair_series_telemetria(raw)
        if not series.get("temp"):
            return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "features": False})

        temp = series.get("temp", [])
        degelo = series.get("degelo", [])
        setpoint = series.get("setpoint", [])
        onoff = series.get("onoff", [])

        raw_features = extrair_features_janela(temp, degelo, setpoint, onoff)
        if raw_features is None:
            return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "features": False})

        temp_arr = np.array(temp, dtype=float)
        raw_features["temp_tendencia"] = (
            float(np.polyfit(range(len(temp_arr)), temp_arr, 1)[0])
            if len(temp_arr) > 1 else 0.0
        )

        result = {"dispositivo_id": dispositivo_id}

        if _modelos["rf"] is not None:
            try:
                feature_cols = [
                    "temp_media", "temp_maxima", "temp_minima", "temp_amplitude",
                    "temp_volatilidade", "temp_tendencia",
                ]
                mapped = {
                    "temp_media": raw_features.get("temp_mean", 0),
                    "temp_maxima": raw_features.get("temp_max", 0),
                    "temp_minima": raw_features.get("temp_min", 0),
                    "temp_amplitude": raw_features.get("temp_amplitude", 0),
                    "temp_volatilidade": raw_features.get("temp_std", 0),
                    "temp_tendencia": raw_features.get("temp_tendencia", 0),
                }
                row = [mapped[c] for c in feature_cols]
                X = np.array(row).reshape(1, -1)
                proba = float(_modelos["rf"].predict_proba(X)[0])
                result["risk_score"] = round(proba, 4)
            except Exception:
                result["risk_score"] = None
        else:
            # Fallback: risk score via OneClassSVM decision function (sigmoid-normalized)
            if _modelos["ocsvm"] is not None:
                try:
                    feat_keys = _modelos["ocsvm"].feature_cols
                    if feat_keys:
                        row = [raw_features.get(c, 0.0) for c in feat_keys]
                        X = np.array(row).reshape(1, -1)
                        X = np.nan_to_num(X, nan=0.0)
                        decision = _modelos["ocsvm"].decision_function(X)[0]
                        proba = 1 / (1 + np.exp(-decision))
                        result["risk_score"] = round(float(proba), 4)
                    else:
                        result["risk_score"] = None
                except Exception:
                    result["risk_score"] = None
            else:
                result["risk_score"] = None

        if _modelos["ocsvm"] is not None:
            feat_keys = _modelos["ocsvm"].feature_cols
            if feat_keys:
                row = [raw_features.get(c, 0.0) for c in feat_keys]
                X = np.array(row).reshape(1, -1)
                X = np.nan_to_num(X, nan=0.0)
                pred_raw = _modelos["ocsvm"].predict_raw(X)[0]
                result["anomaly"] = bool(pred_raw == -1)
                result["anomaly_reason"] = _modelos["ocsvm"].gerar_motivo(raw_features, 0 if pred_raw == 1 else 1)
            else:
                result["anomaly"] = False
                result["anomaly_reason"] = None
        else:
            result["anomaly"] = False
            result["anomaly_reason"] = None

        return jsonify({"status": "ok", **result})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/abrir-chamado", methods=["POST"])
def api_abrir_chamado():
    """Abre chamado técnico para um dispositivo específico (ação manual)."""
    body = request.get_json(force=True)
    required = ["loja_id", "loja_nome", "dispositivo_id", "tag", "motivo_ia"]
    for campo in required:
        if campo not in body:
            return jsonify({"status": "erro", "mensagem": f"Campo obrigatório ausente: {campo}"}), 400
    try:
        resposta = abrir_chamado(
            loja_id=int(body["loja_id"]),
            loja_nome=str(body["loja_nome"]),
            dispositivo_id=int(body["dispositivo_id"]),
            tag=str(body["tag"]),
            motivo_ia=str(body["motivo_ia"]),
            requer_tecnico=bool(body.get("requer_tecnico", True)),
        )
        _cache["chamados_log"].append({
            "ts": datetime.now().isoformat(),
            "dispositivo_id": body["dispositivo_id"],
            "loja_nome": body["loja_nome"],
            "tag": body["tag"],
            "motivo": body["motivo_ia"],
            "status": "aberto",
        })
        return jsonify({"status": "ok", "resposta": resposta})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


# ── Rotas — Dashboards HTML ───────────────────────────────────────────────────

@app.route("/dashboards/risco")
def dashboard_risco():
    return render_template("dashboards/risco.html", active_page="risco")


@app.route("/dashboards/temperatura")
def dashboard_temperatura():
    return render_template("dashboards/temperatura.html", active_page="temperatura")


@app.route("/dashboards/alarmes-loja")
def dashboard_alarmes_loja():
    return render_template("dashboards/alarmes_loja.html", active_page="alarmes-loja")


@app.route("/dashboards/degelo")
def dashboard_degelo():
    return render_template("dashboards/degelo.html", active_page="degelo")


@app.route("/dashboards/pressao")
def dashboard_pressao():
    return render_template("dashboards/pressao.html", active_page="pressao")


@app.route("/dashboards/saude")
def dashboard_saude():
    return render_template("dashboards/saude.html", active_page="saude")


@app.route("/dashboards/chamados")
def dashboard_chamados():
    return render_template("dashboards/chamados.html", active_page="chamados")


# ── Rotas — API JSON Dashboards ───────────────────────────────────────────────

@app.route("/api/dashboard/risco")
def api_dashboard_risco():
    try:
        dados = risco_tabela(_cache["alarmes_raw"], _cache["tele_features"], _modelos)
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/dashboard/temperatura/devices")
def api_dashboard_temperatura_devices():
    try:
        raw_map = {a.get("dispositivoId"): a for a in _cache["alarmes_raw"]}
        devices = []
        for did in _cache["tele_series"]:
            raw = raw_map.get(did, {})
            devices.append({
                "did": did,
                "nome": raw.get("dispositivoNm", f"Device {did}"),
                "loja": raw.get("lojaNm", ""),
                "criticidade": raw.get("criticidade", "I"),
            })
        return jsonify({"status": "ok", "dados": devices})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/dashboard/temperatura/<int:did>")
def api_dashboard_temperatura_series(did):
    try:
        dados = temperatura_series(did, _cache["tele_series"])
        if dados is None:
            return jsonify({"status": "erro", "mensagem": "Sem dados de telemetria para este dispositivo"}), 404
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/dashboard/alarmes-loja")
def api_dashboard_alarmes_loja():
    try:
        dados = alarmes_por_loja(_cache["alarmes_raw"])
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/dashboard/degelo")
def api_dashboard_degelo():
    try:
        dados = degelo_analysis(_cache["tele_features"], _cache["alarmes_raw"])
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/dashboard/pressao/devices")
def api_dashboard_pressao_devices():
    try:
        dados = pressao_devices(_cache["tele_features"])
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/dashboard/pressao/<int:did>")
def api_dashboard_pressao_series(did):
    try:
        dados = pressao_series(did, _cache["tele_series"])
        if dados is None:
            return jsonify({"status": "erro", "mensagem": "Sem dados de pressão para este dispositivo"}), 404
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/dashboard/saude")
def api_dashboard_saude():
    try:
        dados = saude_frota(_cache["alarmes_raw"], _cache["tele_features"], _modelos)
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/dashboard/chamados")
def api_dashboard_chamados():
    try:
        dados = list(reversed(_cache["chamados_log"]))[:100]
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/dashboards/financeiro")
def dashboard_financeiro():
    return render_template("dashboards/financeiro.html", active_page="financeiro")


@app.route("/api/dashboard/financeiro")
def api_dashboard_financeiro():
    try:
        dados = financeiro_impacto(_cache["alarmes_raw"], _cache["tele_features"], _modelos)
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/dashboards/modelo")
def dashboard_modelo():
    return render_template("dashboards/modelo.html", active_page="modelo")


@app.route("/api/dashboard/modelo")
def api_dashboard_modelo():
    try:
        rf = _modelos.get("rf")
        ocsvm = _modelos.get("ocsvm")

        feature_importance = []
        modelo_info = {}

        if rf is not None:
            try:
                clf = rf.modelo if hasattr(rf, "modelo") else rf
                importances = clf.feature_importances_.tolist()
                feature_cols = [
                    "temp_media", "temp_maxima", "temp_minima",
                    "temp_amplitude", "temp_volatilidade", "temp_tendencia",
                ]
                feature_importance = sorted(
                    [{"feature": f, "importancia": round(v, 4)} for f, v in zip(feature_cols, importances)],
                    key=lambda x: -x["importancia"],
                )
                modelo_info["rf"] = {
                    "tipo": "Random Forest",
                    "n_estimators": int(getattr(clf, "n_estimators", 0)),
                    "n_features": int(getattr(clf, "n_features_in_", len(feature_cols))),
                    "carregado": True,
                }
            except Exception:
                modelo_info["rf"] = {"tipo": "Random Forest", "carregado": True, "erro": "Não foi possível extrair metadados"}

        if ocsvm is not None:
            try:
                clf_svm = ocsvm.modelo if hasattr(ocsvm, "modelo") else ocsvm
                modelo_info["ocsvm"] = {
                    "tipo": "OneClass SVM",
                    "kernel": str(getattr(clf_svm, "kernel", "rbf")),
                    "nu": float(getattr(clf_svm, "nu", 0)),
                    "n_support": int(getattr(clf_svm, "n_support_", [0])[0]) if hasattr(clf_svm, "n_support_") else 0,
                    "carregado": True,
                }
            except Exception:
                modelo_info["ocsvm"] = {"tipo": "OneClass SVM", "carregado": True, "erro": "Não foi possível extrair metadados"}

        scores = [d.get("risk_score") for d in _cache.get("tele_features", {}).values() if isinstance(d, dict) and d.get("risk_score") is not None]
        if not scores and _cache.get("alarmes_raw"):
            from src.dashboard_service import risco_tabela as _rt
            tabela = _rt(_cache["alarmes_raw"], _cache["tele_features"], _modelos)
            scores = [d["risk_score"] for d in tabela if d.get("risk_score") is not None]

        distribuicao = {"baixo": 0, "medio": 0, "alto": 0}
        for s in scores:
            if s < 0.4:
                distribuicao["baixo"] += 1
            elif s < 0.7:
                distribuicao["medio"] += 1
            else:
                distribuicao["alto"] += 1

        return jsonify({
            "status": "ok",
            "dados": {
                "feature_importance": feature_importance,
                "modelo_info": modelo_info,
                "score_distribuicao": distribuicao,
                "n_devices_scored": len(scores),
                "score_medio": round(float(np.mean(scores)), 4) if scores else None,
                "modelos_carregados": _modelos_carregados,
            },
        })
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"\n  EletroFrio ML — PoC Dashboard")
    print(f"  Acesse:     http://localhost:{args.port}")
    print(f"  Alarmes:    http://localhost:{args.port}/api/alarmes")
    print(f"  Unidades:   http://localhost:{args.port}/api/unidades")
    print(f"  Telemetria: http://localhost:{args.port}/api/telemetria/<id>")
    print(f"  Predicao:   http://localhost:{args.port}/api/predict/<id>")
    print(f"  Health:     http://localhost:{args.port}/api/health")
    print(f"  Stats:      http://localhost:{args.port}/api/stats\n")
    app.run(host=args.host, port=args.port, debug=False)
