"""
EletroFrio - Modelos de Machine Learning
=========================================
Implementa dois classificadores para detecção de falhas em compressores:

  1. SVM  – Support Vector Machine com kernel RBF e busca de hiperparâmetros
  2. RF   – Random Forest com busca por GridSearchCV

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
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV, StratifiedKFold
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



