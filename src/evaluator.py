import numpy as np
import pandas as pd
import joblib
import itertools
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from src.config import MODELS_DIR, DATA_DIR
from src.features import get_feature_columns


def calcular_metricas(y_true, y_pred):
    vp = np.sum((y_pred == -1) & (y_true == -1))
    fp = np.sum((y_pred == -1) & (y_true == 1))
    fn = np.sum((y_pred == 1) & (y_true == -1))
    vn = np.sum((y_pred == 1) & (y_true == 1))

    precisao = vp / (vp + fp) if (vp + fp) > 0 else 0.0
    recall = vp / (vp + fn) if (vp + fn) > 0 else 0.0
    f1 = 2 * precisao * recall / (precisao + recall) if (precisao + recall) > 0 else 0.0

    return {
        "vp": int(vp), "fp": int(fp), "fn": int(fn), "vn": int(vn),
        "precisao": round(precisao, 4), "recall": round(recall, 4), "f1": round(f1, 4),
    }


def grid_search(df_normais, df_anomalos, feature_cols):
    X_norm = np.nan_to_num(df_normais[feature_cols].values, nan=0.0)
    X_anom = np.nan_to_num(df_anomalos[feature_cols].values, nan=0.0)

    if len(X_norm) > 1000:
        idx = np.random.RandomState(42).choice(len(X_norm), 1000, replace=False)
        X_norm = X_norm[idx]

    X = np.vstack([X_norm, X_anom])
    y = np.hstack([np.ones(len(X_norm)), -np.ones(len(X_anom))])

    nu_values = [0.01, 0.05, 0.1, 0.2]
    gamma_values = ["scale", "auto", 0.1, 0.01, 0.001]

    resultados = []

    for nu, gamma in itertools.product(nu_values, gamma_values):
        skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        f1_scores = []

        for train_idx, test_idx in skf.split(X, y):
            X_t, X_te = X[train_idx], X[test_idx]
            y_t, y_te = y[train_idx], y[test_idx]

            only_normal = y_t == 1
            X_train_normal = X_t[only_normal]

            scaler = StandardScaler()
            X_tr_scaled = scaler.fit_transform(X_train_normal)

            m = OneClassSVM(kernel="rbf", nu=nu, gamma=gamma)
            m.fit(X_tr_scaled)

            X_te_scaled = scaler.transform(X_te)
            y_pred = m.predict(X_te_scaled)

            metrics = calcular_metricas(y_te, y_pred)
            f1_scores.append(metrics["f1"])

        resultados.append({
            "nu": nu, "gamma": str(gamma),
            "f1_medio": round(np.mean(f1_scores), 4),
            "f1_std": round(np.std(f1_scores), 4),
        })
        print(f"  nu={nu}, gamma={str(gamma):>6s}: F1={np.mean(f1_scores):.4f} +/- {np.std(f1_scores):.4f}")

    df_res = pd.DataFrame(resultados).sort_values("f1_medio", ascending=False)
    print("\n=== Top 5 combinacoes ===")
    for _, row in df_res.head(5).iterrows():
        print(f"  nu={row['nu']}, gamma={row['gamma']:>6s}: F1={row['f1_medio']:.4f} +/- {row['f1_std']:.4f}")

    return df_res


def avaliar_modelo_salvo(df_normais, df_anomalos, feature_cols):
    model = joblib.load(f"{MODELS_DIR}/svm_anomalia.pkl")
    scaler = joblib.load(f"{MODELS_DIR}/scaler.pkl")

    X_norm = np.nan_to_num(df_normais[feature_cols].values, nan=0.0)
    X_anom = np.nan_to_num(df_anomalos[feature_cols].values, nan=0.0)

    if len(X_norm) > len(X_anom) * 3:
        idx = np.random.RandomState(42).choice(len(X_norm), len(X_anom) * 3, replace=False)
        X_norm = X_norm[idx]

    X_test = np.vstack([X_norm, X_anom])
    y_test = np.hstack([np.ones(len(X_norm)), -np.ones(len(X_anom))])

    X_scaled = scaler.transform(X_test)
    y_pred = model.predict(X_scaled)

    metrics = calcular_metricas(y_test, y_pred)
    print("\n=== Avaliacao do modelo salvo ===")
    print(f"VP={metrics['vp']}  FP={metrics['fp']}  FN={metrics['fn']}  VN={metrics['vn']}")
    print(f"Precisao: {metrics['precisao']:.2%}")
    print(f"Recall:   {metrics['recall']:.2%}")
    print(f"F1-score: {metrics['f1']:.2%}")

    return metrics
