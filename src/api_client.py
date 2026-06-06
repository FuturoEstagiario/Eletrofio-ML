import requests
import urllib3
from src.config import API_BASE, API_TIMEOUT, API_EQUIPE

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _get(params: dict) -> dict | list:
    resp = requests.get(API_BASE, params=params, timeout=API_TIMEOUT, verify=False)
    resp.raise_for_status()
    return resp.json()


def buscar_alarmes() -> list[dict]:
    return _get({"route": "alarmes"})


def buscar_unidades() -> list[dict]:
    return _get({"route": "unidades"})


def buscar_telemetria(dispositivo_id: int) -> dict:
    return _get({"route": "telemetria", "dispositivoId": dispositivo_id})


def abrir_chamado(
    loja_id: int,
    loja_nome: str,
    dispositivo_id: int,
    tag: str,
    motivo_ia: str,
    requer_tecnico: bool = True,
) -> dict:
    payload = {
        "equipe": API_EQUIPE,
        "lojaId": loja_id,
        "lojaNome": loja_nome,
        "dispositivoId": dispositivo_id,
        "tag": tag,
        "motivoIA": motivo_ia,
        "requerTecnico": requer_tecnico,
    }
    resp = requests.post(
        API_BASE,
        params={"route": "abrir-chamado"},
        json=payload,
        timeout=API_TIMEOUT,
        verify=False,
    )
    resp.raise_for_status()
    return resp.json()
