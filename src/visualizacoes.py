"""
EletroFrio - Visualizacoes e Relatorios
========================================
Gera todos os gráficos de análise exploratória e avaliação dos modelos.
Os arquivos PNG são salvos em reports/figures/.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # backend nao-interativo (sem Tkinter) para rodar em qualquer ambiente
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from sklearn.metrics import roc_curve, auc, ConfusionMatrixDisplay

# ── Tema global ───────────────────────────────────────────────────────────────

PALETA = {
    "normal":  "#2ECC71",
    "falha":   "#E74C3C",
    "svm":     "#3498DB",
    "rf":      "#9B59B6",
    "fundo":   "#1A1A2E",
    "painel":  "#16213E",
    "texto":   "#EAEAEA",
    "grade":   "#2D3561",
}

def _estilo():
    plt.rcParams.update({
        "figure.facecolor":  PALETA["fundo"],
        "axes.facecolor":    PALETA["painel"],
        "axes.edgecolor":    PALETA["grade"],
        "axes.labelcolor":   PALETA["texto"],
        "xtick.color":       PALETA["texto"],
        "ytick.color":       PALETA["texto"],
        "text.color":        PALETA["texto"],
        "grid.color":        PALETA["grade"],
        "grid.linestyle":    "--",
        "grid.alpha":        0.5,
        "font.family":       "DejaVu Sans",
        "font.size":         11,
        "axes.titlesize":    13,
        "axes.titleweight":  "bold",
        "figure.dpi":        120,
    })

SAIDA = os.path.join("reports", "figures")


def _salvar(fig, nome: str) -> str:
    os.makedirs(SAIDA, exist_ok=True)
    caminho = os.path.join(SAIDA, nome)
    fig.savefig(caminho, bbox_inches="tight", facecolor=PALETA["fundo"])
    plt.close(fig)
    print(f"  ✓ Figura salva: {caminho}")
    return caminho


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Análise Exploratória (EDA)
# ═══════════════════════════════════════════════════════════════════════════════

def plot_distribuicao_classes(df: pd.DataFrame) -> str:
    """Gráfico de pizza e barras com distribuição normal vs falha."""
    _estilo()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Distribuição de Classes — Leituras de Compressores",
                 fontsize=15, fontweight="bold", color=PALETA["texto"], y=1.02)

    counts = df["falha"].value_counts()
    labels = ["Normal", "Falha"]
    cores = [PALETA["normal"], PALETA["falha"]]

    # Pizza
    ax = axes[0]
    wedges, texts, autotexts = ax.pie(
        counts, labels=labels, colors=cores,
        autopct="%1.1f%%", startangle=90,
        textprops={"color": PALETA["texto"], "fontsize": 12},
        wedgeprops={"edgecolor": PALETA["fundo"], "linewidth": 2},
    )
    for at in autotexts:
        at.set_fontsize(13)
        at.set_fontweight("bold")
    ax.set_title("Proporção de Classes")

    # Barras
    ax = axes[1]
    bars = ax.bar(labels, counts.values, color=cores, width=0.5,
                  edgecolor=PALETA["fundo"], linewidth=1.5)
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 80,
                f"{val:,}", ha="center", va="bottom",
                fontweight="bold", color=PALETA["texto"])
    ax.set_ylabel("Quantidade de Leituras")
    ax.set_title("Contagem por Classe")
    ax.grid(axis="y")

    plt.tight_layout()
    return _salvar(fig, "01_distribuicao_classes.png")


def plot_correlacao(df: pd.DataFrame, feature_names: list) -> str:
    """Heatmap de correlação entre features numéricas."""
    _estilo()
    colunas = [c for c in feature_names if c in df.columns]
    corr = df[colunas + ["falha"]].corr()

    fig, ax = plt.subplots(figsize=(14, 12))
    mask = np.zeros_like(corr, dtype=bool)
    mask[np.triu_indices_from(mask)] = True

    sns.heatmap(
        corr, mask=mask, ax=ax,
        cmap="coolwarm", center=0, vmin=-1, vmax=1,
        annot=True, fmt=".2f", annot_kws={"size": 8},
        linewidths=0.5, linecolor=PALETA["fundo"],
        cbar_kws={"shrink": 0.8},
    )
    ax.set_title("Matriz de Correlação — Features do Compressor", pad=15)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    return _salvar(fig, "02_correlacao_features.png")


def plot_boxplots_falha(df: pd.DataFrame) -> str:
    """Boxplots de features-chave segmentadas por classe (normal/falha)."""
    _estilo()
    features = [
        "temp_succao", "temp_descarga", "pressao_succao",
        "pressao_descarga", "corrente", "vibracao",
        "nivel_refrigerante", "horas_desde_manut",
    ]
    labels_feat = [
        "Temp. Sucção (°C)", "Temp. Descarga (°C)", "Pressão Sucção (bar)",
        "Pressão Descarga (bar)", "Corrente (A)", "Vibração (mm/s)",
        "Nível Refrigerante (%)", "Horas s/ Manutenção",
    ]

    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    fig.suptitle("Distribuição de Sensores — Normal vs Falha",
                 fontsize=15, fontweight="bold", color=PALETA["texto"])
    axes = axes.flatten()

    for i, (feat, label) in enumerate(zip(features, labels_feat)):
        ax = axes[i]
        grupos = [
            df.loc[df["falha"] == 0, feat].dropna().values,
            df.loc[df["falha"] == 1, feat].dropna().values,
        ]
        bp = ax.boxplot(
            grupos, patch_artist=True, notch=True,
            medianprops={"color": "white", "linewidth": 2},
        )
        for patch, cor in zip(bp["boxes"], [PALETA["normal"], PALETA["falha"]]):
            patch.set_facecolor(cor)
            patch.set_alpha(0.75)
        for whisker in bp["whiskers"]:
            whisker.set_color(PALETA["texto"])
        for cap in bp["caps"]:
            cap.set_color(PALETA["texto"])

        ax.set_xticklabels(["Normal", "Falha"])
        ax.set_title(label, pad=8)
        ax.grid(axis="y")

    plt.tight_layout()
    return _salvar(fig, "03_boxplots_sensores.png")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Avaliação dos Modelos
# ═══════════════════════════════════════════════════════════════════════════════

def plot_matrizes_confusao(resultados: dict) -> str:
    """Matrizes de confusão lado a lado para SVM e RF."""
    _estilo()
    fig, axes = plt.subplots(1, len(resultados), figsize=(7 * len(resultados), 6))
    if len(resultados) == 1:
        axes = [axes]

    fig.suptitle("Matrizes de Confusão — Conjunto de Teste",
                 fontsize=15, fontweight="bold", color=PALETA["texto"])

    cores_modelo = {"SVM": PALETA["svm"], "Random Forest": PALETA["rf"]}

    for ax, (nome, met) in zip(axes, resultados.items()):
        cm = met["conf_matrix"]
        cor = cores_modelo.get(nome, "#AAA")
        im = ax.imshow(cm, cmap="Blues")
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(["Normal", "Falha"])
        ax.set_yticklabels(["Normal", "Falha"])
        ax.set_xlabel("Previsto")
        ax.set_ylabel("Real")

        thresh = cm.max() / 2
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f"{cm[i, j]:,}", ha="center", va="center",
                        fontsize=16, fontweight="bold",
                        color="white" if cm[i, j] > thresh else "black")

        ax.set_title(nome, color=cor, fontsize=14, fontweight="bold")

        # Labels de TN/FP/FN/TP
        for (xi, yi), lbl in zip([(0, 0), (1, 0), (0, 1), (1, 1)],
                                  ["TN", "FP", "FN", "TP"]):
            ax.text(xi, yi + 0.35, lbl, ha="center", va="center",
                    fontsize=9, color=PALETA["texto"], alpha=0.7)

    plt.tight_layout()
    return _salvar(fig, "04_matrizes_confusao.png")


def plot_curvas_roc(resultados: dict, y_test: np.ndarray) -> str:
    """Curvas ROC para todos os modelos."""
    _estilo()
    fig, ax = plt.subplots(figsize=(8, 7))

    cores = {"SVM": PALETA["svm"], "Random Forest": PALETA["rf"]}

    for nome, met in resultados.items():
        fpr, tpr, _ = roc_curve(y_test, met["y_prob"])
        roc_auc = auc(fpr, tpr)
        cor = cores.get(nome, "#AAA")
        ax.plot(fpr, tpr, color=cor, lw=2.5,
                label=f"{nome}  (AUC = {roc_auc:.4f})")
        ax.fill_between(fpr, tpr, alpha=0.07, color=cor)

    ax.plot([0, 1], [0, 1], "k--", lw=1.5, alpha=0.6, label="Aleatório (AUC = 0.5)")
    ax.set_xlabel("Taxa de Falsos Positivos (FPR)")
    ax.set_ylabel("Taxa de Verdadeiros Positivos (TPR)")
    ax.set_title("Curvas ROC — Detecção de Falhas em Compressores")
    ax.legend(fontsize=11, facecolor=PALETA["painel"], edgecolor=PALETA["grade"])
    ax.grid(True)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.05])
    plt.tight_layout()
    return _salvar(fig, "05_curvas_roc.png")


def plot_comparacao_metricas(resultados: dict) -> str:
    """Gráfico de barras agrupadas comparando métricas dos modelos."""
    _estilo()
    metricas_plot = ["acuracia", "precisao", "recall", "f1", "roc_auc"]
    labels_met = ["Acurácia", "Precisão", "Recall", "F1-Score", "ROC-AUC"]

    modelos = list(resultados.keys())
    x = np.arange(len(metricas_plot))
    width = 0.35
    cores = [PALETA["svm"], PALETA["rf"]]

    fig, ax = plt.subplots(figsize=(13, 6))
    fig.suptitle("Comparação de Desempenho — SVM vs Random Forest",
                 fontsize=15, fontweight="bold", color=PALETA["texto"])

    for i, (nome, cor) in enumerate(zip(modelos, cores)):
        vals = [resultados[nome][m] for m in metricas_plot]
        offset = (i - (len(modelos) - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width, label=nome, color=cor,
                      edgecolor=PALETA["fundo"], linewidth=1.2, alpha=0.88)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.005,
                    f"{v:.3f}", ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color=PALETA["texto"])

    ax.set_xticks(x)
    ax.set_xticklabels(labels_met)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Score")
    ax.legend(fontsize=12, facecolor=PALETA["painel"], edgecolor=PALETA["grade"])
    ax.axhline(1.0, color=PALETA["texto"], lw=0.8, alpha=0.3)
    ax.grid(axis="y")
    plt.tight_layout()
    return _salvar(fig, "06_comparacao_metricas.png")


def plot_importancia_features(df_imp: pd.DataFrame, top_n: int = 15) -> str:
    """Barras horizontais com importância de features do Random Forest."""
    _estilo()
    df_top = df_imp.head(top_n)

    fig, ax = plt.subplots(figsize=(10, 7))
    cores_bar = [PALETA["rf"] if i < 5 else "#7D3C98"
                 for i in range(len(df_top))]
    bars = ax.barh(df_top["feature"][::-1], df_top["importancia"][::-1],
                   color=cores_bar[::-1], edgecolor=PALETA["fundo"], linewidth=0.8)
    for bar, v in zip(bars, df_top["importancia"][::-1]):
        ax.text(v + 0.003, bar.get_y() + bar.get_height() / 2,
                f"{v:.4f}", va="center", fontsize=9, color=PALETA["texto"])

    ax.set_xlabel("Importância (Gini Impurity)")
    ax.set_title(f"Top {top_n} Features — Random Forest\n(Importância para Previsão de Falhas)")
    ax.grid(axis="x")
    plt.tight_layout()
    return _salvar(fig, "07_importancia_features.png")


def plot_temperatura_timeline(df: pd.DataFrame, compressor_id: str = "COMP-001") -> str:
    """Série temporal de temperatura de descarga com falhas marcadas."""
    _estilo()
    df_comp = df[df["compressor_id"] == compressor_id].copy()
    df_comp["ts_idx"] = range(len(df_comp))

    fig, ax = plt.subplots(figsize=(16, 5))

    mask_norm = df_comp["falha"] == 0
    mask_falha = df_comp["falha"] == 1

    ax.plot(df_comp.loc[mask_norm, "ts_idx"],
            df_comp.loc[mask_norm, "temp_descarga"],
            color=PALETA["normal"], lw=1.2, alpha=0.8, label="Normal")

    ax.scatter(df_comp.loc[mask_falha, "ts_idx"],
               df_comp.loc[mask_falha, "temp_descarga"],
               color=PALETA["falha"], s=18, zorder=5, alpha=0.9, label="Falha detectada")

    ax.axhline(90, color=PALETA["falha"], lw=1, ls="--", alpha=0.5,
               label="Limite crítico (90°C)")
    ax.set_xlabel("Leitura (índice cronológico)")
    ax.set_ylabel("Temperatura de Descarga (°C)")
    ax.set_title(f"Série Temporal — Temperatura de Descarga | {compressor_id}")
    ax.legend(fontsize=11, facecolor=PALETA["painel"], edgecolor=PALETA["grade"])
    ax.grid(True)
    plt.tight_layout()
    return _salvar(fig, "08_timeline_temperatura.png")
