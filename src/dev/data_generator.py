"""
EletroFrio - Gerador de Dados Sintéticos de Compressores
=========================================================
Simula leituras de sensores de compressores de refrigeração industrial
usados em supermercados. Os dados são salvos em banco SQLite.

Variáveis simuladas:
    - Temperatura de sucção (°C)
    - Temperatura de descarga (°C)
    - Temperatura ambiente (°C)
    - Temperatura do evaporador (°C)
    - Pressão de sucção (bar)
    - Pressão de descarga (bar)
    - Corrente elétrica (A)
    - Vibração (mm/s)
    - Nível de refrigerante (%)
    - Horas de operação desde última manutenção
    - Falha (0 = normal, 1 = falha)
"""

import sqlite3
import numpy as np
import pandas as pd
import os
from datetime import datetime, timedelta

# ── Configurações globais ────────────────────────────────────────────────────

RANDOM_SEED = 42
NUM_COMPRESSORS = 10          # número de compressores na frota
RECORDS_PER_COMPRESSOR = 2000 # leituras por compressor
FAILURE_RATE = 0.12           # ~12 % dos registros com falha (desequilíbrio real)

# Intervalos normais de operação ─────────────────────────────
NORMAL = {
    "temp_succao":      (-5.0,  10.0),   # °C
    "temp_descarga":    (60.0,  85.0),   # °C
    "temp_ambiente":    (18.0,  30.0),   # °C
    "temp_evaporador":  (-18.0, -5.0),   # °C
    "pressao_succao":   (1.2,    2.5),   # bar
    "pressao_descarga": (12.0,  18.0),   # bar
    "corrente":         (8.0,   15.0),   # A
    "vibracao":         (0.5,    3.0),   # mm/s
    "nivel_refrig":     (70.0,  100.0),  # %
}

# Intervalos durante falha (desvios que indicam problemas)
FAILURE = {
    "temp_succao":      (12.0,  25.0),   # muito alta → sucção comprometida
    "temp_descarga":    (90.0, 130.0),   # superaquecimento
    "temp_ambiente":    (18.0,  35.0),
    "temp_evaporador":  (-4.0,   5.0),   # perde capacidade de resfriamento
    "pressao_succao":   (0.5,    1.1),   # pressão baixa → vazamento
    "pressao_descarga": (19.0,  26.0),   # alta pressão → bloqueio
    "corrente":         (16.0,  28.0),   # sobrecarga elétrica
    "vibracao":         (4.0,   12.0),   # desgaste mecânico
    "nivel_refrig":     (20.0,  65.0),   # baixo nível → vazamento
}


def _gerar_leituras_compressor(
    compressor_id: str,
    n_records: int,
    failure_rate: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Gera n_records leituras para um único compressor."""

    # Labels de falha com distribuição realista
    labels = rng.choice([0, 1], size=n_records, p=[1 - failure_rate, failure_rate])

    rows = []
    hora_manutencao = rng.integers(0, 500)  # horas iniciais aleatórias

    timestamp = datetime(2024, 1, 1) + timedelta(hours=rng.integers(0, 24).item())

    for i, label in enumerate(labels):
        faixa = FAILURE if label == 1 else NORMAL

        # Ruído gaussiano leve sobre os valores uniformes
        def sample(key):
            lo, hi = faixa[key]
            val = rng.uniform(lo, hi)
            noise = rng.normal(0, (hi - lo) * 0.03)
            return round(float(np.clip(val + noise, lo - 2, hi + 2)), 3)

        hora_manutencao += rng.integers(1, 4).item()  # avança horas

        row = {
            "compressor_id":      compressor_id,
            "timestamp":          timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "temp_succao":        sample("temp_succao"),
            "temp_descarga":      sample("temp_descarga"),
            "temp_ambiente":      sample("temp_ambiente"),
            "temp_evaporador":    sample("temp_evaporador"),
            "pressao_succao":     sample("pressao_succao"),
            "pressao_descarga":   sample("pressao_descarga"),
            "corrente":           sample("corrente"),
            "vibracao":           sample("vibracao"),
            "nivel_refrigerante": sample("nivel_refrig"),
            "horas_desde_manut":  int(hora_manutencao),
            "falha":              int(label),
        }
        rows.append(row)
        timestamp += timedelta(minutes=rng.integers(15, 60).item())

    return pd.DataFrame(rows)


def gerar_dataset(
    n_compressores: int = NUM_COMPRESSORS,
    registros_por_compressor: int = RECORDS_PER_COMPRESSOR,
    taxa_falha: float = FAILURE_RATE,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Gera o dataset completo com todos os compressores.

    Returns:
        DataFrame com todas as leituras concatenadas.
    """
    rng = np.random.default_rng(seed)
    partes = []

    for i in range(1, n_compressores + 1):
        comp_id = f"COMP-{i:03d}"
        df_comp = _gerar_leituras_compressor(
            compressor_id=comp_id,
            n_records=registros_por_compressor,
            failure_rate=taxa_falha,
            rng=rng,
        )
        partes.append(df_comp)
        print(f"  ✓ {comp_id} | {registros_por_compressor} leituras geradas")

    df = pd.concat(partes, ignore_index=True)
    df.index.name = "id"
    return df


def salvar_sqlite(df: pd.DataFrame, db_path: str) -> None:
    """
    Persiste o DataFrame em SQLite com três tabelas:
      - compressores_leituras  → leituras brutas dos sensores
      - compressores_info      → metadados de cada compressor
      - falhas_registradas     → apenas registros com falha (view materializada)
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        # Tabela principal de leituras
        df.to_sql("compressores_leituras", conn, if_exists="replace", index=True)

        # Tabela de metadados dos compressores
        info = pd.DataFrame({
            "compressor_id":   df["compressor_id"].unique(),
            "modelo":          ["Carrier 06D", "Bitzer S4T", "Copeland ZR",
                                "Embraco EMI", "Danfoss MT", "Kenmore 110",
                                "Tecumseh AZA", "Panasonic UA", "Emerson CR",
                                "Secop SC"][: df["compressor_id"].nunique()],
            "capacidade_hp":   [5, 7.5, 10, 5, 7.5, 10, 5, 7.5, 10, 5][: df["compressor_id"].nunique()],
            "instalacao":      ["2021-03-" + str(d).zfill(2)
                                for d in range(1, df["compressor_id"].nunique() + 1)],
        })
        info.to_sql("compressores_info", conn, if_exists="replace", index=False)

        # Tabela com apenas falhas
        falhas = df[df["falha"] == 1].copy()
        falhas.to_sql("falhas_registradas", conn, if_exists="replace", index=True)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_comp ON compressores_leituras(compressor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ts   ON compressores_leituras(timestamp)")
        conn.commit()

    total = len(df)
    n_falhas = int(df["falha"].sum())
    print(f"\n  ✓ SQLite salvo em: {db_path}")
    print(f"    Total de registros : {total:,}")
    print(f"    Registros normais  : {total - n_falhas:,}  ({(total-n_falhas)/total*100:.1f}%)")
    print(f"    Registros c/ falha : {n_falhas:,}  ({n_falhas/total*100:.1f}%)")


if __name__ == "__main__":
    print("=" * 60)
    print("  EletroFrio — Gerador de Dados de Compressores")
    print("=" * 60)
    print("\nGerando leituras sintéticas de sensores...\n")

    df = gerar_dataset()
    db_path = os.path.join("data", "eletrofrio.db")
    salvar_sqlite(df, db_path)

    print("\nPré-visualização dos dados:")
    print(df.head(5).to_string())
    print("\nDistribuição de falhas por compressor:")
    print(df.groupby("compressor_id")["falha"].agg(["sum", "count"]).rename(
        columns={"sum": "falhas", "count": "total"}
    ))
