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
import math
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
from flask.json.provider import DefaultJSONProvider
from whitenoise import WhiteNoise
from src.api_client import buscar_alarmes, buscar_unidades, buscar_telemetria, abrir_chamado
from src.api_preprocessor import processar_alarmes, _extrair_features_telemetria
from src.data_collector import parse_telemetria
from src.features import processar_dispositivo
from src.config import SERIES_MAP
from src.dashboard_service import (
    risco_tabela, temperatura_series, alarmes_por_loja,
    degelo_analysis, pressao_devices, pressao_series,
    saude_frota,
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

_pipeline_lock  = threading.Lock()
_pipeline_state = {"last_collection": None, "last_training": None, "devices_at_last_train": 0}

try:
    from src.db import init_tables as _init_db_tables
    _init_db_tables()
    log.info("DB: tabela 'chamados' inicializada")
except Exception as _e:
    log.warning(f"DB: init_tables falhou (chamados guardados em memória): {_e}")

try:
    from src.db import init_scores_historico as _init_scores
    _init_scores()
    log.info("DB: tabela 'scores_historico' inicializada")
except Exception as _e:
    log.warning(f"DB: init_scores_historico falhou: {_e}")


class _NaNSafeProvider(DefaultJSONProvider):
    @staticmethod
    def _clean(obj):
        if isinstance(obj, float) and not math.isfinite(obj):
            return None
        if isinstance(obj, dict):
            return {k: _NaNSafeProvider._clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_NaNSafeProvider._clean(v) for v in obj]
        return obj

    def dumps(self, obj, **kwargs):
        return super().dumps(self._clean(obj), **kwargs)


app = Flask(__name__, template_folder="views", static_folder="views")
app.json = _NaNSafeProvider(app)
app.wsgi_app = WhiteNoise(app.wsgi_app, root="views/", prefix="static")

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_PARQUET_DIR = os.path.join(_BASE_DIR, "dados_coletados")

log.info(f"BASE_DIR    : {_BASE_DIR}")
log.info(f"PARQUET_DIR : {_PARQUET_DIR}")
log.info(f"alarmes.parquet  existe: {os.path.exists(os.path.join(_PARQUET_DIR, 'alarmes.parquet'))}")
log.info(f"unidades.parquet existe: {os.path.exists(os.path.join(_PARQUET_DIR, 'unidades.parquet'))}")
log.info(f"tele_features.parquet existe: {os.path.exists(os.path.join(_PARQUET_DIR, 'tele_features.parquet'))}")
log.info(f"tele_series.parquet   existe: {os.path.exists(os.path.join(_PARQUET_DIR, 'tele_series.parquet'))}")

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


def _parquet_load_alarmes():
    path = os.path.join(_PARQUET_DIR, "alarmes.parquet")
    df = pd.read_parquet(path)
    return df.where(pd.notnull(df), None).to_dict("records")


def _parquet_load_unidades():
    path = os.path.join(_PARQUET_DIR, "unidades.parquet")
    df = pd.read_parquet(path)
    return df.where(pd.notnull(df), None).to_dict("records")


def _parquet_load_tele_features():
    path = os.path.join(_PARQUET_DIR, "tele_features.parquet")
    df = pd.read_parquet(path)
    result = {}
    for _, row in df.iterrows():
        did = int(row["dispositivo_id"])
        feats = {k: v for k, v in row.items() if k != "dispositivo_id" and not pd.isna(v)}
        result[did] = [feats]
    return result


def _parquet_load_tele_series():
    path = os.path.join(_PARQUET_DIR, "tele_series.parquet")
    df = pd.read_parquet(path)
    serie_cols = [c for c in df.columns if c not in ("dispositivo_id", "label_idx", "label")]
    result = {}
    for did, group in df.groupby("dispositivo_id"):
        g = group.sort_values("label_idx")
        sd = {"labels": g["label"].tolist()}
        for col in serie_cols:
            sd[col] = g[col].where(pd.notnull(g[col]), other=None).tolist()
        result[int(did)] = sd
    return result


# ── Pre-load síncrono de parquet — garante data_ok=True antes do 1.º request ──
log.info("PRE-LOAD startup: carregando parquet...")
try:
    _cache["alarmes_raw"] = _parquet_load_alarmes()
    _cache["data_ok"] = True
    log.info(f"PRE-LOAD alarmes OK — {len(_cache['alarmes_raw'])} registos")
except Exception as _pe:
    log.error(f"PRE-LOAD alarmes ERRO: {type(_pe).__name__}: {_pe}", exc_info=True)

try:
    _cache["unidades"] = _parquet_load_unidades()
    log.info(f"PRE-LOAD unidades OK — {len(_cache['unidades'])} registos")
except Exception as _pe:
    log.error(f"PRE-LOAD unidades ERRO: {type(_pe).__name__}: {_pe}", exc_info=True)

_cache["ts"] = time.time()
log.info(f"PRE-LOAD concluído — data_ok={_cache['data_ok']} alarmes={len(_cache['alarmes_raw'])} unidades={len(_cache['unidades'])}")

try:
    _cache["tele_features"] = _parquet_load_tele_features()
    log.info(f"PRE-LOAD tele_features OK — {len(_cache['tele_features'])} devices")
except Exception as _pe:
    log.warning(f"PRE-LOAD tele_features sem ficheiro (normal antes do 1.º coletar_tele.py): {_pe}")

try:
    _cache["tele_series"] = _parquet_load_tele_series()
    log.info(f"PRE-LOAD tele_series OK — {len(_cache['tele_series'])} devices")
except Exception as _pe:
    log.warning(f"PRE-LOAD tele_series sem ficheiro (normal antes do 1.º coletar_tele.py): {_pe}")


def _run_cache_cycle():
    """Executa um ciclo completo de refresh do cache. Chamado pelo thread de background."""
    log.info("══ início do ciclo de cache ══")

    # Alarmes
    try:
        log.info("Buscando alarmes da API...")
        _cache["alarmes_raw"] = buscar_alarmes()
        _cache["api_ok"] = True
        _cache["data_ok"] = True
        log.info(f"API alarmes OK — {len(_cache['alarmes_raw'])} registos")
    except Exception as e:
        log.error(f"API alarmes ERRO: {type(e).__name__}: {e}", exc_info=True)
        _cache["api_ok"] = False
        try:
            _cache["alarmes_raw"] = _parquet_load_alarmes()
            _cache["data_ok"] = True
            log.info(f"Fallback parquet alarmes OK — {len(_cache['alarmes_raw'])} registos")
        except Exception as pe:
            log.error(f"Fallback parquet alarmes ERRO: {type(pe).__name__}: {pe}", exc_info=True)

    # Unidades
    try:
        log.info("Buscando unidades da API...")
        _cache["unidades"] = buscar_unidades()
        log.info(f"API unidades OK — {len(_cache['unidades'])} registos")
    except Exception as e:
        log.error(f"API unidades ERRO: {type(e).__name__}: {e}", exc_info=True)
        try:
            _cache["unidades"] = _parquet_load_unidades()
            log.info(f"Fallback parquet unidades OK — {len(_cache['unidades'])} registos")
        except Exception as pe:
            log.error(f"Fallback parquet unidades ERRO: {type(pe).__name__}: {pe}", exc_info=True)

    _cache["ts"] = time.time()
    log.info(
        f"Cache actualizado — api_ok={_cache['api_ok']} data_ok={_cache['data_ok']} "
        f"alarmes={len(_cache['alarmes_raw'])} unidades={len(_cache['unidades'])}"
    )

    # Telemetria — só tenta se a API estiver acessível
    if not _cache.get("api_ok"):
        log.info("Telemetria ignorada — API indisponível (api_ok=False)")
    else:
        try:
            _PRIO = {"C": 0, "A": 1, "M": 2, "B": 3, "I": 4}
            _sorted = sorted(_cache["alarmes_raw"], key=lambda a: _PRIO.get(a.get("criticidade", "I"), 99))
            device_ids = list(dict.fromkeys(
                a.get("dispositivoId") for a in _sorted if a.get("dispositivoId")
            ))[:30]
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
        except Exception as te:
            log.error(f"Telemetria bloco ERRO inesperado: {type(te).__name__}: {te}", exc_info=True)

    log.info(f"Próximo ciclo em {CACHE_TTL}s")


def _fetch_background():
    while True:
        try:
            _run_cache_cycle()
        except Exception as e:
            log.critical(f"THREAD CRASH — ciclo abortado: {type(e).__name__}: {e}", exc_info=True)
        time.sleep(CACHE_TTL)


_bg_lock = threading.Lock()
_bg_started = False


@app.before_request
def _ensure_bg_thread():
    global _bg_started
    if _bg_started:
        return
    with _bg_lock:
        if not _bg_started:
            _bg_started = True
            threading.Thread(target=_fetch_background, daemon=True).start()
            log.info("Background refresh iniciado no worker")


# ── Pipeline: colecta agendada + re-treino automático ────────────────────────

def _reload_models():
    from src.models import RandomForestModel, OneClassSVMModel
    from src.config import MODELS_DIR
    with _pipeline_lock:
        try:
            _modelos["rf"] = RandomForestModel.carregar(f"{MODELS_DIR}/rf_eletrofrio.pkl")
        except Exception as e:
            log.warning(f"[PIPELINE] Reload RF falhou: {e}")
        try:
            _modelos["ocsvm"] = OneClassSVMModel.carregar(MODELS_DIR)
        except Exception as e:
            log.warning(f"[PIPELINE] Reload OCC SVM falhou: {e}")
    log.info("[PIPELINE] Modelos recarregados em memória")


def _background_train():
    try:
        from src.pipeline import run_training
        metrics = run_training(use_feedback=True)
        _pipeline_state["last_training"] = metrics
        _reload_models()
    except Exception as e:
        log.error(f"[PIPELINE] Re-treino falhou: {type(e).__name__}: {e}", exc_info=True)


def _trigger_retrain_if_needed():
    feat_path = os.path.join(_PARQUET_DIR, "tele_features.parquet")
    if not os.path.exists(feat_path):
        return
    try:
        n_devices = len(pd.read_parquet(feat_path))
    except Exception:
        return
    if n_devices > _pipeline_state["devices_at_last_train"]:
        log.info(
            f"[PIPELINE] Novos devices ({_pipeline_state['devices_at_last_train']} → {n_devices})"
            " — lançando re-treino..."
        )
        _pipeline_state["devices_at_last_train"] = n_devices
        threading.Thread(target=_background_train, daemon=True).start()


def _batch_score_devices():
    """Corre inferência em todos os devices do cache e grava em scores_historico."""
    ocsvm     = _modelos.get("ocsvm")
    feat_keys = ocsvm.feature_cols if ocsvm is not None and ocsvm.feature_cols else None
    if not feat_keys or (_modelos["rf"] is None and ocsvm is None):
        log.info("[SCORES] Modelos ou feature_cols não disponíveis — batch scoring ignorado")
        return

    from src.db import inserir_score
    gravados = 0
    for did, feat_list in list(_cache.get("tele_features", {}).items()):
        try:
            feats = feat_list[-1] if isinstance(feat_list, list) and feat_list else {}
            if not feats:
                continue
            row = [feats.get(c, 0.0) for c in feat_keys]
            X   = np.nan_to_num(np.array(row, dtype=float).reshape(1, -1), nan=0.0)

            risk_score = None
            anomaly    = None
            if _modelos["rf"] is not None:
                risk_score = round(float(_modelos["rf"].predict_proba(X)[0]), 4)
            if ocsvm is not None:
                anomaly = bool(ocsvm.predict_raw(X)[0] == -1)

            inserir_score(int(did), risk_score, anomaly)
            gravados += 1
        except Exception as e:
            log.warning(f"[SCORES] Device {did}: {e}")

    log.info(f"[SCORES] {gravados} scores gravados em scores_historico")


def _scheduled_collect():
    log.info("[PIPELINE] Colecta agendada iniciada...")
    try:
        from src.pipeline import run_collection
        stats = run_collection()
        _pipeline_state["last_collection"] = stats
        try:
            _cache["tele_features"] = _parquet_load_tele_features()
            _cache["tele_series"]   = _parquet_load_tele_series()
            log.info("[PIPELINE] Cache tele actualizado após colecta")
        except Exception as ce:
            log.warning(f"[PIPELINE] Reload cache tele falhou: {ce}")
        _batch_score_devices()
        _trigger_retrain_if_needed()
    except Exception as e:
        log.error(f"[PIPELINE] Colecta agendada falhou: {type(e).__name__}: {e}", exc_info=True)


try:
    import atexit
    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(func=_scheduled_collect, trigger="interval", hours=6, id="collect_tele")
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    log.info("[PIPELINE] Scheduler iniciado — colecta a cada 6h")
    log.warning("[PIPELINE] AVISO: Gunicorn workers>1 cria múltiplos schedulers. Use workers=1 ou job store externo.")
except ImportError:
    log.warning("[PIPELINE] apscheduler não instalado — colecta agendada desactivada")


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
    log.info(
        f"GET / — data_ok={_cache.get('data_ok')} api_ok={_cache.get('api_ok')} "
        f"alarmes={len(alarmes_raw)} unidades={len(unidades)}"
    )
    erros = {} if _cache.get("data_ok") else {"status": "Carregando dados da API, aguarde e recarregue em instantes..."}
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
        dados = _cache["alarmes_raw"] or []
        return jsonify({"status": "ok", "total": len(dados), "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/health")
def api_health():
    return jsonify({
        "status":            "ok",
        "data_ok":           _cache.get("data_ok", False),
        "api":               _cache.get("api_ok", False),
        "modelos":           {"rf": _modelos["rf"] is not None, "ocsvm": _modelos["ocsvm"] is not None},
        "modelos_carregados": _modelos_carregados,
        "cache_ts":          _cache["ts"],
    })


@app.route("/api/unidades")
def api_unidades():
    try:
        dados = _cache["unidades"] or []
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
    """Retorna features e séries de telemetria a partir do cache (sem chamada live à API)."""
    feats = _cache["tele_features"].get(dispositivo_id) or _cache["tele_features"].get(str(dispositivo_id))
    series = _cache["tele_series"].get(dispositivo_id) or _cache["tele_series"].get(str(dispositivo_id))

    if not feats and not series:
        return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "features": {}, "series": {}, "labels": []})

    feat_dict = feats[-1] if isinstance(feats, list) and feats else (feats or {})
    temp = (series or {}).get("temp", [])

    return jsonify({
        "status": "ok",
        "dispositivo_id": dispositivo_id,
        "features": {
            "temp_media":          round(float(feat_dict.get("temp_mean", 0) or 0), 1),
            "temp_maxima":         round(float(feat_dict.get("temp_max", 0) or 0), 1),
            "temp_minima":         round(float(feat_dict.get("temp_min", 0) or 0), 1),
            "temp_amplitude":      round(float(feat_dict.get("temp_amplitude", 0) or 0), 1),
            "temp_tendencia":      round(float(feat_dict.get("temp_taxa_variacao_media", 0) or 0), 3),
            "temp_acima_setpoint": round(float(feat_dict.get("temp_pct_acima_sp", 0) or 0), 3),
            "degelo_fracao":       round(float(feat_dict.get("degelo_fracao", 0) or 0), 3),
            "onoff_fracao_ligado": round(float(feat_dict.get("onoff_fracao_ligado", 0) or 0), 3),
        },
        "series": {
            "temp":     temp[-96:] if len(temp) > 96 else temp,
            "degelo":   (series or {}).get("degelo", [])[-96:],
            "setpoint": (series or {}).get("setpoint", [])[-96:],
            "onoff":    (series or {}).get("onoff", [])[-96:],
        },
        "labels": (series or {}).get("labels", []),
    })


@app.route("/api/stats")
def api_stats():
    try:
        df = processar_alarmes(_cache["alarmes_raw"]) if _cache["alarmes_raw"] else pd.DataFrame()
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
                _ocsvm = _modelos.get("ocsvm")
                feat_keys = _ocsvm.feature_cols if _ocsvm is not None and _ocsvm.feature_cols else None
                if feat_keys:
                    row = [raw_features.get(c, 0.0) for c in feat_keys]
                    X = np.nan_to_num(np.array(row, dtype=float).reshape(1, -1), nan=0.0)
                    proba = float(_modelos["rf"].predict_proba(X)[0])
                    result["risk_score"] = round(proba, 4)
                else:
                    result["risk_score"] = None
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
    entry = {
        "ts": datetime.now().isoformat(),
        "dispositivo_id": body["dispositivo_id"],
        "loja_nome": body["loja_nome"],
        "tag": body["tag"],
        "motivo": body["motivo_ia"],
        "status": "aberto",
        "origem": "api",
    }

    # Persistir no PostgreSQL independente de a API externa estar disponível
    try:
        from src.db import inserir_chamado
        entry["id"] = inserir_chamado(
            dispositivo_id=int(body["dispositivo_id"]),
            loja_id=int(body["loja_id"]),
            loja_nome=str(body["loja_nome"]),
            tag=str(body["tag"]),
            motivo=str(body["motivo_ia"]),
            tecnico_presencial=bool(body.get("requer_tecnico", True)),
        )
        log.info(f"Chamado id={entry['id']} persistido no PostgreSQL — device {body['dispositivo_id']}")
    except Exception as db_e:
        log.warning(f"DB inserir_chamado falhou: {db_e}")

    try:
        resposta = abrir_chamado(
            loja_id=int(body["loja_id"]),
            loja_nome=str(body["loja_nome"]),
            dispositivo_id=int(body["dispositivo_id"]),
            tag=str(body["tag"]),
            motivo_ia=str(body["motivo_ia"]),
            requer_tecnico=bool(body.get("requer_tecnico", True)),
        )
        log.info(f"Chamado aberto via API — device {body['dispositivo_id']} loja {body['loja_nome']}")
        _cache["chamados_log"].append(entry)
        return jsonify({"status": "ok", "resposta": resposta, "origem": "api"})
    except Exception as e:
        log.warning(f"API chamado indisponível ({type(e).__name__}), guardando localmente — device {body['dispositivo_id']}")
        entry["origem"] = "local"
        _cache["chamados_log"].append(entry)
        return jsonify({
            "status": "ok",
            "origem": "local",
            "mensagem": "API de chamados indisponível. Chamado registado localmente nesta sessão.",
        })


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
        from src.db import listar_chamados
        rows = listar_chamados()
        dados = [
            {
                "id":                 r["id"],
                "ts":                 r["criado_em"].isoformat() if r["criado_em"] else None,
                "dispositivo_id":     r["dispositivo_id"],
                "loja_nome":          r["loja_nome"],
                "tag":                r["tag"],
                "motivo":             r["motivo"],
                "status":             r["status"],
                "tecnico_presencial": r["tecnico_presencial"],
                "resolvido_em":       r["resolvido_em"].isoformat() if r["resolvido_em"] else None,
            }
            for r in rows
        ]
        return jsonify({"status": "ok", "dados": dados})
    except Exception as e:
        log.warning(f"DB listar_chamados falhou: {e} — usando cache em memória")
        dados = list(reversed(_cache["chamados_log"]))[:100]
        return jsonify({"status": "ok", "dados": dados})


@app.route("/api/chamados/<int:chamado_id>/resolver", methods=["PATCH"])
def api_resolver_chamado(chamado_id):
    try:
        from src.db import resolver_chamado
        ok = resolver_chamado(chamado_id)
        if ok:
            return jsonify({"status": "ok", "chamado_id": chamado_id})
        return jsonify({"status": "erro", "mensagem": "Chamado não encontrado ou já fechado"}), 404
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
                clf = rf.model if hasattr(rf, "model") else rf
                importances = clf.feature_importances_.tolist()
                _ocsvm_local = _modelos.get("ocsvm")
                feature_cols = (
                    _ocsvm_local.feature_cols
                    if _ocsvm_local is not None and _ocsvm_local.feature_cols
                    else [f"feat_{i}" for i in range(len(importances))]
                )
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
                clf_svm = ocsvm.model if hasattr(ocsvm, "model") else ocsvm
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


@app.route("/api/monitoramento/scores/<int:dispositivo_id>")
def api_monitoramento_scores(dispositivo_id):
    """Histórico de risk_score e anomaly para um device específico."""
    try:
        from src.db import listar_scores_device
        rows = listar_scores_device(dispositivo_id)
        dados = [
            {
                "ts":         r["ts"].isoformat() if r["ts"] else None,
                "risk_score": r["risk_score"],
                "anomaly":    r["anomaly"],
            }
            for r in rows
        ]
        return jsonify({
            "status":         "ok",
            "dispositivo_id": dispositivo_id,
            "n_registos":     len(dados),
            "dados":          dados,
        })
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/monitoramento/reincidencia")
def api_monitoramento_reincidencia():
    """Ranking de devices por número de chamados + MTTR."""
    try:
        from src.db import stats_reincidencia
        rows = stats_reincidencia()
        dados = [
            {
                "dispositivo_id":     r["dispositivo_id"],
                "loja_nome":          r["loja_nome"],
                "tag":                r["tag"],
                "total_chamados":     r["total_chamados"],
                "chamados_resolvidos": r["chamados_resolvidos"],
                "chamados_abertos":   r["chamados_abertos"],
                "mttr_horas":         float(r["mttr_horas"]) if r["mttr_horas"] is not None else None,
                "primeiro_chamado":   r["primeiro_chamado"].isoformat() if r["primeiro_chamado"] else None,
                "ultimo_chamado":     r["ultimo_chamado"].isoformat() if r["ultimo_chamado"] else None,
            }
            for r in rows
        ]
        return jsonify({
            "status":      "ok",
            "n_devices":   len(dados),
            "dados":       dados,
        })
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """Registra feedback de técnico sobre anomalia de um device.

    Body JSON: { "dispositivo_id": int, "anomalo": 0|1, "reason": str }
    O feedback sobrepõe o label automático de criticidade no próximo re-treino.
    """
    try:
        data   = request.get_json(force=True) or {}
        did    = data.get("dispositivo_id")
        label  = data.get("anomalo")
        reason = str(data.get("reason", ""))

        if did is None or label not in (0, 1):
            return jsonify({"status": "erro", "mensagem": "dispositivo_id e anomalo (0|1) são obrigatórios"}), 400

        feedback_path = os.path.join(_PARQUET_DIR, "feedback.parquet")
        new_row = pd.DataFrame([{
            "dispositivo_id": int(did),
            "anomalo":        int(label),
            "reason":         reason,
            "timestamp":      datetime.now().isoformat(),
        }])

        if os.path.exists(feedback_path):
            df_fb = pd.read_parquet(feedback_path)
            df_fb = df_fb[df_fb["dispositivo_id"] != int(did)]
            df_fb = pd.concat([df_fb, new_row], ignore_index=True)
        else:
            df_fb = new_row

        df_fb.to_parquet(feedback_path, index=False)
        log.info(f"[FEEDBACK] Device {did} → anomalo={label} reason='{reason}'")
        return jsonify({"status": "ok", "dispositivo_id": did, "anomalo": label})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route("/api/admin/coletar", methods=["POST"])
def api_admin_coletar():
    """Dispara colecta manual de telemetria em background thread."""
    threading.Thread(target=_scheduled_collect, daemon=True).start()
    return jsonify({"status": "ok", "mensagem": "Colecta iniciada em background"})


@app.route("/api/admin/treinar", methods=["POST"])
def api_admin_treinar():
    """Dispara re-treino manual dos modelos em background thread."""
    threading.Thread(target=_background_train, daemon=True).start()
    return jsonify({"status": "ok", "mensagem": "Re-treino iniciado em background"})


@app.route("/api/keepalive")
def api_keepalive():
    from src.db import ping
    ok = ping()
    return jsonify({"status": "ok" if ok else "erro", "db": ok})


@app.route("/api/pipeline/status")
def api_pipeline_status():
    """Estado do pipeline: última colecta, último treino, devices."""
    return jsonify({
        "status":                "ok",
        "last_collection":       _pipeline_state.get("last_collection"),
        "last_training":         _pipeline_state.get("last_training"),
        "devices_at_last_train": _pipeline_state.get("devices_at_last_train"),
    })


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
