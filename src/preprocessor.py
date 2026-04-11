"""
EletroFrio - Carregamento e Pré-processamento de Dados
=======================================================
Responsável por:
  1. Ler dados do SQLite
  2. Engenharia de features (diferenciais, razões físicas)
  3. Divisão treino/teste estratificada
  4. Balanceamento via SMOTE (para lidar com desequilíbrio de classes)
  5. Normalização (StandardScaler)
"""

import sqlite3
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE

# ── Features brutas ──────────────────────────────────────────────────────────

RAW_FEATURES = [
    "temp_succao",
    "temp_descarga",
    "temp_ambiente",
    "temp_evaporador",
    "pressao_succao",
    "pressao_descarga",
    "corrente",
    "vibracao",
    "nivel_refrigerante",
    "horas_desde_manut",
]

TARGET = "falha"


# ── Engenharia de Features ───────────────────────────────────────────────────

def engenharia_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cria features derivadas com significado físico para compressores:

    - diferencial_temp      : temp_descarga - temp_succao  (superaquecimento)
    - razao_pressao         : pressao_descarga / pressao_succao  (eficiência)
    - temp_evap_succao_diff : diferença entre evaporador e sucção
    - corrente_normalizada  : corrente / corrente esperada (proxy)
    - indice_risco_temp     : combinação ponderada de temperaturas críticas
    - manut_critica         : flag se > 720 horas sem manutenção (30 dias)
    """
    df = df.copy()

    df["diferencial_temp"] = df["temp_descarga"] - df["temp_succao"]
    df["razao_pressao"] = df["pressao_descarga"] / (df["pressao_succao"] + 1e-6)
    df["temp_evap_succao_diff"] = df["temp_evaporador"] - df["temp_succao"]
    df["corrente_por_pressao"] = df["corrente"] / (df["pressao_descarga"] + 1e-6)
    df["indice_risco_temp"] = (
        0.5 * df["temp_descarga"]
        + 0.3 * df["temp_succao"]
        - 0.2 * df["temp_evaporador"]
    )
    df["manut_critica"] = (df["horas_desde_manut"] > 720).astype(int)
    df["nivel_refrig_baixo"] = (df["nivel_refrigerante"] < 50).astype(int)
    df["vibracao_alta"] = (df["vibracao"] > 5.0).astype(int)

    return df


ENGINEERED_FEATURES = RAW_FEATURES + [
    "diferencial_temp",
    "razao_pressao",
    "temp_evap_succao_diff",
    "corrente_por_pressao",
    "indice_risco_temp",
    "manut_critica",
    "nivel_refrig_baixo",
    "vibracao_alta",
]


# ── Carregamento e Preparação ────────────────────────────────────────────────

def carregar_e_preparar(
    db_path: str,
    test_size: float = 0.2,
    aplicar_smote: bool = True,
    seed: int = 42,
) -> dict:
    """
    Pipeline completo de carregamento e pré-processamento.

    Returns:
        dict com chaves:
          X_train, X_test, y_train, y_test  → arrays numpy prontos para treino
          X_train_raw, X_test_raw            → DataFrames antes da normalização
          scaler                             → StandardScaler ajustado
          feature_names                      → lista de features usadas
          df_original                        → DataFrame original completo
    """
    print("  [1/5] Carregando dados do SQLite...")
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql("SELECT * FROM compressores_leituras", conn, index_col="id")

    print(f"        {len(df):,} registros carregados | "
          f"falhas: {df['falha'].sum():,} ({df['falha'].mean()*100:.1f}%)")

    print("  [2/5] Aplicando engenharia de features...")
    df_eng = engenharia_features(df)

    X = df_eng[ENGINEERED_FEATURES]
    y = df_eng[TARGET]

    print("  [3/5] Dividindo treino / teste (estratificado)...")
    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=seed,
        stratify=y,
    )

    print("  [4/5] Normalizando features (StandardScaler)...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_raw)
    X_test_scaled = scaler.transform(X_test_raw)

    if aplicar_smote:
        print("  [5/5] Balanceando classes com SMOTE...")
        smote = SMOTE(random_state=seed)
        X_train_scaled, y_train = smote.fit_resample(X_train_scaled, y_train)
        print(f"        Após SMOTE → normal: {(y_train==0).sum():,} | "
              f"falha: {(y_train==1).sum():,}")
    else:
        print("  [5/5] SMOTE desativado. Classes originais mantidas.")

    return {
        "X_train":       X_train_scaled,
        "X_test":        X_test_scaled,
        "y_train":       y_train.values if hasattr(y_train, "values") else y_train,
        "y_test":        y_test.values if hasattr(y_test, "values") else y_test,
        "X_train_raw":   X_train_raw,
        "X_test_raw":    X_test_raw,
        "scaler":        scaler,
        "feature_names": ENGINEERED_FEATURES,
        "df_original":   df,
    }
