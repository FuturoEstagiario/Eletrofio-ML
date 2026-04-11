# -*- coding: utf-8 -*-
"""
EletroFrio - Entry Point Principal
====================================
Orquestra todo o pipeline de ML:

  Etapa 1 → Geração de dados sintéticos e salvamento em SQLite
  Etapa 2 → Carregamento, engenharia de features e pré-processamento
  Etapa 3 → Análise exploratória (EDA) com visualizações
  Etapa 4 → Treino do SVM (com GridSearchCV)
  Etapa 5 → Treino do Random Forest (com GridSearchCV)
  Etapa 6 → Avaliação comparativa dos modelos
  Etapa 7 → Geração de relatório final e salvamento dos modelos

Uso:
    python main.py [--rapido] [--sem-busca]

    --rapido    : usa dataset menor (500 registros/compressor)
    --sem-busca : pula GridSearchCV (mais rápido, mas sem otimização)
"""

import os
import sys
import json
import time
import argparse
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

# ── Módulos do projeto ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from src.data_generator import gerar_dataset, salvar_sqlite
from src.preprocessor import carregar_e_preparar, engenharia_features, ENGINEERED_FEATURES
from src.models import SVMModel, RandomForestModel, imprimir_metricas
from src.visualizacoes import (
    plot_distribuicao_classes,
    plot_correlacao,
    plot_boxplots_falha,
    plot_matrizes_confusao,
    plot_curvas_roc,
    plot_comparacao_metricas,
    plot_importancia_features,
    plot_temperatura_timeline,
)

# ── Caminhos ─────────────────────────────────────────────────────────────────
DB_PATH      = os.path.join("data", "eletrofrio.db")
MODELS_DIR   = "models"
REPORTS_DIR  = "reports"


# ═══════════════════════════════════════════════════════════════════════════════

def banner():
    sep = "=" * 65
    print("\n" + sep)
    print("  ELETROFRIO")
    print("  Previsao de Falhas em Compressores de Refrigeracao")
    print("  Machine Learning | SVM + Random Forest")
    print("  Sistemas de Resfriamento para Supermercados")
    print(sep + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="EletroFrio ML Pipeline")
    parser.add_argument("--rapido", action="store_true",
                        help="Usa dataset menor (500 registros/compressor)")
    parser.add_argument("--sem-busca", action="store_true",
                        help="Pula GridSearchCV para treino mais rapido")
    parser.add_argument("--forcar-geracao", action="store_true",
                        help="Regenera o banco SQLite mesmo se ja existir")
    return parser.parse_args()


def salvar_relatorio(resultados: dict, tempo_total: float, args) -> str:
    """Gera um relatorio JSON com todas as metricas."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    relatorio = {
        "projeto": "EletroFrio - Previsao de Falhas em Compressores",
        "data_execucao": pd.Timestamp.now().isoformat(),
        "configuracao": {
            "modo_rapido": args.rapido,
            "sem_busca_hiperpar": args.sem_busca,
        },
        "tempo_total_segundos": round(tempo_total, 2),
        "modelos": {},
    }

    for nome, met in resultados.items():
        relatorio["modelos"][nome] = {
            "acuracia":  round(met["acuracia"], 4),
            "precisao":  round(met["precisao"], 4),
            "recall":    round(met["recall"], 4),
            "f1_score":  round(met["f1"], 4),
            "roc_auc":   round(met["roc_auc"], 4),
            "conf_matrix": met["conf_matrix"].tolist(),
        }

    path = os.path.join(REPORTS_DIR, "relatorio_modelos.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
    print(f"\n  [OK] Relatorio JSON salvo em: {path}")
    return path


# ===============================================================
# Pipeline principal
# ===============================================================

def main():
    banner()
    args = parse_args()
    t_inicio = time.time()

    registros = 500 if args.rapido else 2000
    busca = not args.sem_busca

    sep = "-" * 65

    # -- Etapa 1: Geracao de dados -------------------------------------------
    print(sep)
    print("  ETAPA 1 -- Geracao de Dados Sinteticos de Compressores")
    print(sep)

    if os.path.exists(DB_PATH) and not args.forcar_geracao:
        print(f"  -> Banco SQLite ja existe: {DB_PATH}  (use --forcar-geracao para regenerar)")
    else:
        df = gerar_dataset(registros_por_compressor=registros)
        salvar_sqlite(df, DB_PATH)

    # -- Etapa 2: Pre-processamento ------------------------------------------
    print("\n" + sep)
    print("  ETAPA 2 -- Carregamento e Pre-processamento")
    print(sep)

    dados = carregar_e_preparar(DB_PATH, test_size=0.2, aplicar_smote=True)
    X_train = dados["X_train"]
    X_test  = dados["X_test"]
    y_train = dados["y_train"]
    y_test  = dados["y_test"]
    df_orig = dados["df_original"]

    print(f"\n  Conjunto de treino : {X_train.shape[0]:,} amostras x {X_train.shape[1]} features")
    print(f"  Conjunto de teste  : {X_test.shape[0]:,} amostras x {X_test.shape[1]} features")

    # -- Etapa 3: EDA --------------------------------------------------------
    print("\n" + sep)
    print("  ETAPA 3 -- Analise Exploratoria (EDA)")
    print(sep)

    df_eng = engenharia_features(df_orig)
    plot_distribuicao_classes(df_orig)
    plot_correlacao(df_eng, ENGINEERED_FEATURES)
    plot_boxplots_falha(df_orig)
    plot_temperatura_timeline(df_orig)

    # -- Etapa 4: SVM --------------------------------------------------------
    print("\n" + sep)
    print("  ETAPA 4 -- Treinamento do SVM")
    print(sep)

    svm = SVMModel()
    svm.treinar(X_train, y_train, busca_hiperpar=busca)
    met_svm = svm.avaliar(X_test, y_test)
    imprimir_metricas("SVM", met_svm)
    svm.salvar(os.path.join(MODELS_DIR, "svm_eletrofrio.pkl"))

    # -- Etapa 5: Random Forest ----------------------------------------------
    print("\n" + sep)
    print("  ETAPA 5 -- Treinamento do Random Forest")
    print(sep)

    rf = RandomForestModel()
    rf.treinar(X_train, y_train, busca_hiperpar=busca)
    met_rf = rf.avaliar(X_test, y_test)
    imprimir_metricas("Random Forest", met_rf)
    rf.salvar(os.path.join(MODELS_DIR, "rf_eletrofrio.pkl"))

    # -- Etapa 6: Comparacao e Visualizacoes ---------------------------------
    print("\n" + sep)
    print("  ETAPA 6 -- Avaliacao Comparativa e Visualizacoes")
    print(sep)

    resultados = {"SVM": met_svm, "Random Forest": met_rf}

    plot_matrizes_confusao(resultados)
    plot_curvas_roc(resultados, y_test)
    plot_comparacao_metricas(resultados)
    df_imp = rf.feature_importances(dados["feature_names"])
    plot_importancia_features(df_imp)

    # -- Etapa 7: Relatorio final --------------------------------------------
    print("\n" + sep)
    print("  ETAPA 7 -- Relatorio Final")
    print(sep)

    tempo_total = time.time() - t_inicio
    salvar_relatorio(resultados, tempo_total, args)

    melhor = max(resultados, key=lambda k: resultados[k]["f1"])

    print("\n" + "=" * 65)
    print("  [CONCLUIDO] PIPELINE FINALIZADO COM SUCESSO")
    print("=" * 65)
    print(f"\n  Melhor modelo (F1) : {melhor}")
    print(f"  F1-Score           : {resultados[melhor]['f1']:.4f}")
    print(f"  ROC-AUC            : {resultados[melhor]['roc_auc']:.4f}")
    print(f"  Recall             : {resultados[melhor]['recall']:.4f}")
    print(f"\n  Artefatos gerados:")
    print(f"    Banco de dados  : {DB_PATH}")
    print(f"    Modelos         : {MODELS_DIR}/")
    print(f"    Figuras         : reports/figures/")
    print(f"    Relatorio JSON  : reports/relatorio_modelos.json")
    print(f"\n  Tempo total: {tempo_total:.1f}s")
    print("=" * 65 + "\n")

    print("  Top 10 Features mais importantes (Random Forest):")
    print(df_imp.head(10).to_string(index=False))
    print()


if __name__ == "__main__":
    main()
