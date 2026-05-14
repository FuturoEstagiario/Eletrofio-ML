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
import os
import sys
import time
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from flask import Flask, jsonify, render_template, request
from whitenoise import WhiteNoise
from src.api_client import buscar_alarmes, buscar_unidades, buscar_telemetria, abrir_chamado
from src.api_preprocessor import processar_alarmes

app = Flask(__name__, template_folder="views", static_folder="views")
app.wsgi_app = WhiteNoise(app.wsgi_app, root="views/", prefix="static")

_cache = {"alarmes_raw": [], "unidades": [], "ts": None}
CACHE_TTL = 600


def _fetch_background():
    while True:
        try:
            _cache["alarmes_raw"] = buscar_alarmes()
        except Exception:
            pass
        try:
            _cache["unidades"] = buscar_unidades()
        except Exception:
            pass
        _cache["ts"] = time.time()
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
    erros       = {} if _cache["ts"] else {"status": "Carregando dados, aguarde e recarregue em instantes..."}
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
        atualizado=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
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
    """Retorna features de temperatura processadas para um dispositivo."""
    try:
        raw = buscar_telemetria(dispositivo_id)
        datasets = raw.get("datasets", [])
        if not datasets:
            return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "features": {}})

        # Prefere "Temperatura Ambiente"; cai no primeiro dataset disponível
        ds = next(
            (d for d in datasets if "temperatura ambiente" in d.get("label", "").lower()),
            datasets[0],
        )
        # A API usa "values", não "data"
        valores = [v for v in ds.get("values", ds.get("data", [])) if v is not None]
        if not valores:
            return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "features": {}})

        arr = np.array(valores, dtype=float)
        tendencia = float(np.polyfit(range(len(arr)), arr, 1)[0]) if len(arr) > 1 else 0.0

        features = {
            "temp_media":     round(float(arr.mean()), 1),
            "temp_maxima":    round(float(arr.max()), 1),
            "temp_minima":    round(float(arr.min()), 1),
            "temp_amplitude": round(float(arr.max() - arr.min()), 1),
            "temp_tendencia": round(tendencia, 3),
            "labels":         raw.get("labels", []),
            "valores":        valores[-48:],  # últimas 48 leituras para o gráfico
        }
        return jsonify({"status": "ok", "dispositivo_id": dispositivo_id, "features": features})
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
        return jsonify({"status": "ok", "resposta": resposta})
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
    print(f"  Stats:      http://localhost:{args.port}/api/stats\n")
    app.run(host=args.host, port=args.port, debug=False)
