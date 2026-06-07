from src.api_client import abrir_chamado
from src.config import THRESHOLD_RISCO
from src.models import OneClassSVMModel


def avaliar_e_abrir_chamados(
    df_leituras,
    modelo_predict_proba,
    feature_cols: list[str],
    modelo_oneclass: OneClassSVMModel = None,
) -> list[dict]:
    chamados_abertos = []

    for _, row in df_leituras.iterrows():
        feats_disponiveis = [c for c in feature_cols if c in row.index and row[c] == row[c]]
        if not feats_disponiveis:
            continue

        X = row[feats_disponiveis].values.reshape(1, -1)
        try:
            proba = float(modelo_predict_proba(X)[0])
        except Exception:
            proba = 0.0

        anomalia_msg = None
        if modelo_oneclass is not None and hasattr(modelo_oneclass, 'gerar_motivo'):
            try:
                features_dict = {c: row.get(c, 0.0) for c in feats_disponiveis}
                pred_raw = modelo_oneclass.predict_raw(X)[0]
                if pred_raw == -1:
                    anomalia_msg = modelo_oneclass.gerar_motivo(features_dict, 1)
            except Exception:
                pass

        criticidade = row.get("criticidade", "I")
        sem_tratativa = bool(row.get("sem_tratativa", 0))

        deve_abrir = (proba >= THRESHOLD_RISCO) or (criticidade == "C" and sem_tratativa) or (anomalia_msg is not None)

        if deve_abrir:
            motivo = _montar_motivo(row, proba, anomalia_msg)
            try:
                resposta = abrir_chamado(
                    loja_id=int(row["loja_id"]),
                    loja_nome=str(row["loja_nome"]),
                    dispositivo_id=int(row["dispositivo_id"]),
                    tag=str(row.get("tag", "")),
                    motivo_ia=motivo,
                    requer_tecnico=True,
                )
                chamados_abertos.append({
                    "dispositivo_id": row["dispositivo_id"],
                    "proba_falha": proba,
                    "motivo": motivo,
                    "resposta_api": resposta,
                })
                print(f"  [CHAMADO] dispositivo={row['dispositivo_id']} | risco={proba:.0%} | {motivo}")
            except Exception as e:
                print(f"  [ERRO] Falha ao abrir chamado para dispositivo {row['dispositivo_id']}: {e}")

    return chamados_abertos


def _montar_motivo(row, proba: float, anomalia_msg: str = None) -> str:
    partes = [f"Risco de falha previsto pelo modelo: {proba:.0%}"]

    if anomalia_msg:
        partes.append(f"Anomalia detectada: {anomalia_msg}")

    temp_max = row.get("temp_maxima")
    if temp_max and temp_max == temp_max:
        partes.append(f"temperatura maxima registrada {temp_max:.1f}C")

    tendencia = row.get("temp_tendencia")
    if tendencia and tendencia == tendencia and tendencia > 0:
        partes.append(f"tendencia de alta de {tendencia:.2f}C/leitura")

    alarme = row.get("alarme_desc", "")
    if alarme:
        partes.append(f"alarme ativo: {alarme}")

    return ". ".join(partes) + "."
