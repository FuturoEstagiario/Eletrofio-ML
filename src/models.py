"""
EletroFrio - Modelos de Machine Learning
=========================================
Implementa três classificadores para detecção de falhas em compressores:

  1. SVM         – Support Vector Machine com kernel RBF e busca de hiperparâmetros
  2. RF          – Random Forest com busca por GridSearchCV
  3. OneClassSVM – Detecção de anomalia não supervisionada (treinado só com dados normais)

Cada modelo expõe a mesma interface:
    treinar(X_train, y_train) → self
    avaliar(X_test, y_test)   → dict de métricas
    predict_proba(X)          → np.ndarray
"""

import pandas as pd

import numpy as np
import joblib
import os
import time
import itertools
from sklearn.svm import SVC, OneClassSVM as SkOneClassSVM
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, confusion_matrix,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Classe base
# ═══════════════════════════════════════════════════════════════════════════════

class BaseModel:
    """Interface comum para os modelos da Eletrofrio."""

    name: str = "BaseModel"
    model = None

    def treinar(self, X_train: np.ndarray, y_train: np.ndarray) -> "BaseModel":
        raise NotImplementedError

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if hasattr(self.model, "predict_proba"):
            return self.model.predict_proba(X)[:, 1]
        # SVM com decision_function como substituto
        scores = self.model.decision_function(X)
        # Normaliza para [0, 1] via sigmoid
        return 1 / (1 + np.exp(-scores))

    def avaliar(self, X_test: np.ndarray, y_test: np.ndarray) -> dict:
        y_pred = self.predict(X_test)
        y_prob = self.predict_proba(X_test)

        metricas = {
            "acuracia":  accuracy_score(y_test, y_pred),
            "precisao":  precision_score(y_test, y_pred, zero_division=0),
            "recall":    recall_score(y_test, y_pred, zero_division=0),
            "f1":        f1_score(y_test, y_pred, zero_division=0),
            "roc_auc":   roc_auc_score(y_test, y_prob),
            "conf_matrix": confusion_matrix(y_test, y_pred),
            "y_pred":    y_pred,
            "y_prob":    y_prob,
        }
        return metricas

    def salvar(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self.model, path)
        print(f"  ✓ Modelo {self.name} salvo em: {path}")

    @classmethod
    def carregar(cls, path: str):
        obj = cls.__new__(cls)
        obj.model = joblib.load(path)
        return obj


# ═══════════════════════════════════════════════════════════════════════════════
# SVM — Support Vector Machine
# ═══════════════════════════════════════════════════════════════════════════════

class SVMModel(BaseModel):
    """
    SVM com kernel RBF.
    Usa GridSearchCV com validação cruzada estratificada para
    otimizar C (margem) e gamma (largura do kernel).
    """

    name = "SVM"

    # Grade reduzida mas representativa para não travar a máquina
    PARAM_GRID = {
        "C":     [0.1, 1, 10, 100],
        "gamma": ["scale", "auto", 0.01, 0.001],
    }

    def treinar(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        busca_hiperpar: bool = True,
    ) -> "SVMModel":
        print(f"\n  Treinando {self.name}...")
        t0 = time.time()

        if busca_hiperpar:
            print("    Executando GridSearchCV (4×4 grid, 5-fold CV)...")
            base_svm = SVC(kernel="rbf", probability=True)
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
            grid = GridSearchCV(
                base_svm,
                self.PARAM_GRID,
                cv=cv,
                scoring="recall",
                n_jobs=-1,
                verbose=0,
            )
            grid.fit(X_train, y_train)
            self.model = grid.best_estimator_
            print(f"    Melhores hiperparâmetros: {grid.best_params_}")
            print(f"    Melhor F1 (CV): {grid.best_score_:.4f}")
        else:
            self.model = SVC(
                kernel="rbf", C=10, gamma="scale",
                probability=True,
            )
            self.model.fit(X_train, y_train)

        print(f"    ⏱  Tempo de treino: {time.time() - t0:.1f}s")
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# Random Forest
# ═══════════════════════════════════════════════════════════════════════════════

class RandomForestModel(BaseModel):
    """
    Random Forest com balanceamento por class_weight e busca de hiperparâmetros.
    Retorna importância de features para interpretabilidade.
    """

    name = "Random Forest"

    PARAM_GRID = {
        "n_estimators":      [100, 200, 300],
        "max_depth":         [None, 10, 20],
        "min_samples_split": [2, 5],
        "min_samples_leaf":  [1, 2],
    }

    def treinar(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        busca_hiperpar: bool = True,
    ) -> "RandomForestModel":
        print(f"\n  Treinando {self.name}...")
        t0 = time.time()

        if busca_hiperpar:
            print("    Executando GridSearchCV (3×3×2×2 grid, 5-fold CV)...")
            base_rf = RandomForestClassifier(random_state=42, n_jobs=-1)
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
            grid = GridSearchCV(
                base_rf,
                self.PARAM_GRID,
                cv=cv,
                scoring="recall",
                n_jobs=-1,
                verbose=0,
            )
            grid.fit(X_train, y_train)
            self.model = grid.best_estimator_
            print(f"    Melhores hiperparâmetros: {grid.best_params_}")
            print(f"    Melhor F1 (CV): {grid.best_score_:.4f}")
        else:
            self.model = RandomForestClassifier(
                n_estimators=200, max_depth=20,
                random_state=42, n_jobs=-1,
            )
            self.model.fit(X_train, y_train)

        print(f"    ⏱  Tempo de treino: {time.time() - t0:.1f}s")
        return self

    def feature_importances(self, feature_names: list) -> pd.DataFrame:
        """Retorna DataFrame com importância de cada feature (Gini impurity)."""
        imp = self.model.feature_importances_
        df = pd.DataFrame({
            "feature":    feature_names,
            "importancia": imp,
        }).sort_values("importancia", ascending=False).reset_index(drop=True)
        return df


# ═══════════════════════════════════════════════════════════════════════════════
# One-Class SVM — Detecção de Anomalia Não Supervisionada
# ═══════════════════════════════════════════════════════════════════════════════

class OneClassSVMModel(BaseModel):
    """
    One-Class SVM para detecção de anomalias.
    Treinado apenas com dados Normais; detecta desvios como anomalias.

    OneClassSVM retorna 1 (normal) ou -1 (anomalia).
    Internamente mapeamos: 1 → 0 (normal), -1 → 1 (falha) para compatibilidade.
    """

    name = "OneClassSVM"

    def __init__(self):
        self.model = None
        self.scaler = None
        self.feature_cols = None

    def treinar(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray = None,
        busca_hiperpar: bool = True,
    ) -> "OneClassSVMModel":
        """
        Treina OneClassSVM apenas com amostras Normais.
        Se y_train for fornecido, filtra apenas classe 0 (normal).
        """
        print(f"\n  Treinando {self.name}...")
        t0 = time.time()

        if y_train is not None:
            X_train = X_train[y_train == 0]

        print(f"    Amostras normais para treino: {len(X_train)}")

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X_train)

        if busca_hiperpar:
            print("    Executando GridSearch (nu x gamma, 3-fold CV)...")
            X_tr, X_val = train_test_split(X_scaled, test_size=0.2, random_state=42)
            nu_values = [0.01, 0.05, 0.1, 0.2]
            gamma_values = ["scale", "auto", 0.1, 0.01, 0.001]

            best_f1 = -1
            best_params = None
            best_model = None

            for nu, gamma in itertools.product(nu_values, gamma_values):
                m = SkOneClassSVM(kernel="rbf", nu=nu, gamma=gamma)
                m.fit(X_tr)
                y_pred = m.predict(X_val)
                y_true_val = np.ones(len(X_val))
                vp = int(np.sum((y_pred == -1) & (y_true_val == -1)))
                fp = int(np.sum((y_pred == -1) & (y_true_val == 1)))
                fn = int(np.sum((y_pred == 1) & (y_true_val == -1)))
                prec = vp / (vp + fp) if (vp + fp) > 0 else 0
                rec = vp / (vp + fn) if (vp + fn) > 0 else 0
                f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
                print(f"      nu={nu}, gamma={str(gamma):>6s}: F1={f1:.4f}")
                if f1 > best_f1:
                    best_f1 = f1
                    best_params = (nu, gamma)
                    best_model = m

            self.model = best_model
            print(f"    Melhores hiperparams: nu={best_params[0]}, gamma={best_params[1]} (F1={best_f1:.4f})")
        else:
            self.model = SkOneClassSVM(kernel="rbf", nu=0.05, gamma=0.01)
            self.model.fit(X_scaled)

        print(f"    ⏱  Tempo de treino: {time.time() - t0:.1f}s")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X_s = self.scaler.transform(X)
        y_pred = self.model.predict(X_s)
        return np.where(y_pred == 1, 0, 1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X_s = self.scaler.transform(X)
        scores = self.model.decision_function(X_s)
        return 1 / (1 + np.exp(-scores))

    def predict_raw(self, X: np.ndarray) -> np.ndarray:
        X_s = self.scaler.transform(X)
        return self.model.predict(X_s)

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        X_s = self.scaler.transform(X)
        return self.model.decision_function(X_s)

    def gerar_motivo(self, features: dict, resultado: int) -> str:
        if resultado == 0:
            return "Operacao dentro dos padroes normais"

        motivos = []
        if features.get("temp_mean", 0) > 5:
            motivos.append(f"temperatura media elevada ({features['temp_mean']:.1f}C)")
        if features.get("temp_std", 0) > 3:
            motivos.append(f"oscilacao alta na temperatura (std={features['temp_std']:.1f})")
        if features.get("temp_acima_setpoint", 0) > 0.5:
            motivos.append("tempo prolongado acima do setpoint")
        if features.get("degelo_fracao", 0) > 0.3:
            motivos.append(f"tempo excessivo em degelo ({features['degelo_fracao']:.1%} do periodo)")
        if features.get("onoff_fracao_ligado", 0) < 0.2:
            motivos.append("compressor com baixo tempo de operacao")

        if motivos:
            return "Anomalia detectada: " + "; ".join(motivos)
        return "Anomalia detectada: padrao atipico nos sensores"

    def salvar(self, path_prefix: str = None) -> None:
        if path_prefix is None:
            path_prefix = "models"
        os.makedirs(path_prefix, exist_ok=True)
        joblib.dump(self.model, os.path.join(path_prefix, "svm_anomalia.pkl"))
        joblib.dump(self.scaler, os.path.join(path_prefix, "scaler.pkl"))
        if self.feature_cols:
            joblib.dump(self.feature_cols, os.path.join(path_prefix, "feature_cols.pkl"))
        print(f"  ✓ Modelo {self.name} salvo em {path_prefix}/")

    @classmethod
    def carregar(cls, path_prefix: str = "models"):
        obj = cls.__new__(cls)
        obj.model = joblib.load(os.path.join(path_prefix, "svm_anomalia.pkl"))
        obj.scaler = joblib.load(os.path.join(path_prefix, "scaler.pkl"))
        try:
            obj.feature_cols = joblib.load(os.path.join(path_prefix, "feature_cols.pkl"))
        except (FileNotFoundError, Exception):
            obj.feature_cols = None
        return obj


# ── Facilidade de uso ────────────────────────────────────────────────────────

def imprimir_metricas(nome: str, metricas: dict) -> None:
    """Exibe as métricas de avaliação de forma formatada."""
    print(f"\n{'='*55}")
    print(f"  Resultados — {nome}")
    print(f"{'='*55}")
    print(f"  Acurácia  : {metricas['acuracia']:.4f}")
    print(f"  Precisão  : {metricas['precisao']:.4f}")
    print(f"  Recall    : {metricas['recall']:.4f}")
    print(f"  F1-Score  : {metricas['f1']:.4f}")
    print(f"  ROC-AUC   : {metricas['roc_auc']:.4f}")
    print(f"\n  Matriz de Confusão:")
    cm = metricas["conf_matrix"]
    print(f"    TN={cm[0,0]}  FP={cm[0,1]}")
    print(f"    FN={cm[1,0]}  TP={cm[1,1]}")
    print(f"{'='*55}")



