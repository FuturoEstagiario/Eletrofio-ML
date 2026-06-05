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
  Etapa 8 → Pipeline de dados reais (OneClassSVM) via API

Uso:
    python main.py [--rapido] [--sem-busca] [--live] [--real] [--relabel]

    --rapido    : usa dataset menor (500 registros/compressor)
    --sem-busca : pula GridSearchCV (mais rápido, mas sem otimização)
    --live      : consome endpoints reais da Eletrofrio e abre chamados
    --real      : coleta dados reais da API e treina OneClassSVM
    --relabel   : usa relabel estatístico em vez de timestamps dos alarmes
"""

import os
import sys
import json
import time
import argparse
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

# ── Módulos do projeto ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from src.config import DB_PATH, MODELS_DIR, REPORTS_DIR
from src.data_generator import gerar_dataset, salvar_sqlite
from src.preprocessor import carregar_e_preparar, engenharia_features, ENGINEERED_FEATURES
from src.preprocessor import preparar_dados_janela, carregar_janelas_features
from src.models import SVMModel, RandomForestModel, OneClassSVMModel, imprimir_metricas
from src.api_client import buscar_alarmes, buscar_unidades, buscar_telemetria
from src.api_preprocessor import (
    processar_alarmes, enriquecer_com_telemetria,
    salvar_leituras_real, carregar_leituras_real,
)
from src.chamado_service import avaliar_e_abrir_chamados
from src.data_collector import coletar_tudo
from src.features import processar_todos, get_feature_columns
from src.labeling import preparar_dados_com_labels, recalcular_labels
from src.evaluator import grid_search, avaliar_modelo_salvo
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


# ═══════════════════════════════════════════════════════════════════════════════

def banner():
    sep = "=" * 65
    print("\n" + sep)
    print("  ELETROFRIO")
    print("  Previsao de Falhas em Compressores de Refrigeracao")
    print("  Machine Learning | SVM + Random Forest + OneClassSVM")
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
    parser.add_argument("--live", action="store_true",
                        help="Consome endpoints reais da Eletrofrio e abre chamados automaticos")
    parser.add_argument("--real", action="store_true",
                        help="Coleta dados reais da API e treina OneClassSVM")
    parser.add_argument("--relabel", action="store_true",
                        help="Usa relabel estatistico em vez de timestamps dos alarmes")
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
# Pipeline live (endpoints reais)
# ===============================================================

def pipeline_real(args) -> None:
    sep = "-" * 65
    print("\n" + sep)
    print("  ETAPA 8 -- Pipeline de Dados Reais (OneClassSVM)")
    print(sep)

    print("\n  [1/5] Coletando dados da API...")
    df_telemetria, df_status, unidades_df, alarmes_df = coletar_tudo()

    if df_telemetria.empty:
        print("  [ERRO] Nenhum dado de telemetria coletado. Abortando pipeline real.")
        return

    print("\n  [2/5] Extraindo features por janelas...")
    df_feat = processar_todos(df_telemetria)
    df_feat.to_parquet("dados_coletados/features.parquet", index=False)
    print(f"        {len(df_feat)} amostras, {len(df_feat.columns)} colunas")

    print("\n  [3/5] Rotulando janelas...")
    if args.relabel:
        print("    Usando relabel estatistico (80th percentile)...")
        df_normais, df_anomalos = recalcular_labels()
    else:
        print("    Usando timestamps dos alarmes...")
        df_normais, df_anomalos = preparar_dados_com_labels()

    df_feat = pd.read_parquet("dados_coletados/features.parquet")
    feature_cols = get_feature_columns(df_feat)
    print(f"    Features: {len(feature_cols)}")
    print(f"    Normais: {len(df_normais)} | Anomalos: {len(df_anomalos)}")

    print("\n  [4/5] Treinando OneClassSVM...")
    ocsvm = OneClassSVMModel()
    ocsvm.feature_cols = feature_cols
    dados_janela = preparar_dados_janela(df_feat)
    ocsvm.treinar(dados_janela["X_train"], dados_janela["y_train"], busca_hiperpar=not args.sem_busca)
    met_ocsvm = ocsvm.avaliar(dados_janela["X_test"], dados_janela["y_test"])
    imprimir_metricas("OneClassSVM", met_ocsvm)
    ocsvm.salvar(MODELS_DIR)

    print("\n  [5/5] Grid Search e avaliacao detalhada...")
    if len(df_anomalos) > 0:
        resultados_gs = grid_search(df_normais, df_anomalos, feature_cols)
        resultados_gs.to_csv(f"{MODELS_DIR}/grid_search_results.csv", index=False)
        print(f"    Resultados salvos em {MODELS_DIR}/grid_search_results.csv")

    print("\n  [FIM] Pipeline de dados reais concluido.")
    print(f"  Modelo OneClassSVM salvo em {MODELS_DIR}/")
    print(f"  Para testar: python -c 'from src.models import OneClassSVMModel;")
    print(f"    m = OneClassSVMModel.carregar(); print(m)'")


def pipeline_live(rf_model) -> None:
    sep = "-" * 65
    print("\n" + sep)
    print("  MODO LIVE -- Consumindo Endpoints Reais da Eletrofrio")
    print(sep)

    print("\n  [1/4] Buscando alarmes...")
    alarmes = buscar_alarmes()
    print(f"        {len(alarmes)} alarmes recebidos")

    print("  [2/4] Processando alarmes e enriquecendo com telemetria...")
    df_alarmes = processar_alarmes(alarmes)
    df_enriquecido = enriquecer_com_telemetria(df_alarmes, buscar_telemetria)

    print("  [3/4] Salvando leituras reais no Supabase...")
    salvar_leituras_real(df_enriquecido)

    print("  [4/4] Avaliando risco e abrindo chamados...")
    feature_cols = [
        "criticidade_score", "tempo_min", "sem_tratativa", "silenciado",
        "temp_media", "temp_maxima", "temp_amplitude",
        "temp_volatilidade", "temp_tendencia",
    ]
    try:
        ocsvm = OneClassSVMModel.carregar(MODELS_DIR)
        print("  Modelo OneClassSVM carregado para deteccao de anomalias.")
    except Exception:
        ocsvm = None
        print("  OneClassSVM nao encontrado. Usando apenas RF.")

    chamados = avaliar_e_abrir_chamados(
        df_leituras=df_enriquecido,
        modelo_predict_proba=rf_model.predict_proba,
        feature_cols=feature_cols,
        modelo_oneclass=ocsvm,
    )

    print(f"\n  [LIVE] {len(chamados)} chamado(s) aberto(s) automaticamente.")
    df_leituras = carregar_leituras_real()
    print(f"  [LIVE] {len(df_leituras)} dispositivos monitorados no banco.")


# ===============================================================
# Pipeline principal
# ===============================================================

def main():
    banner()
    args = parse_args()
    t_inicio = time.time()

    if args.real:
        pipeline_real(args)
        tempo_total = time.time() - t_inicio
        print("\n" + "=" * 65)
        print("  [CONCLUIDO] PIPELINE REAL FINALIZADO COM SUCESSO")
        print("=" * 65)
        print(f"\n  Modelo OneClassSVM salvo em {MODELS_DIR}/")
        print(f"  Para iniciar o dashboard: python poc_app.py")
        print(f"\n  Tempo total: {tempo_total:.1f}s")
        print("=" * 65 + "\n")
        return

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

    dados = carregar_e_preparar(test_size=0.2, aplicar_smote=True)
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

    # -- Etapa 9 (opcional): Pipeline live com endpoints reais ---------------
    if args.live:
        pipeline_live(rf)

    melhor = max(resultados, key=lambda k: resultados[k]["recall"])

    print("\n" + "=" * 65)
    print("  [CONCLUIDO] PIPELINE FINALIZADO COM SUCESSO")
    print("=" * 65)
    print(f"\n  Melhor modelo (Recall) : {melhor}")
    print(f"  Recall                 : {resultados[melhor]['recall']:.4f}")
    print(f"  F1-Score               : {resultados[melhor]['f1']:.4f}")
    print(f"  ROC-AUC                : {resultados[melhor]['roc_auc']:.4f}")
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
