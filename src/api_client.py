# -*- coding: utf-8 -*-
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://credenciamento.eletrofrio.com.br:5900/galileo/api/api_hackathon"
TIMEOUT = 300
EQUIPE = "EletroFrio ML"


def _get(params: dict) -> dict | list:
    resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT, verify=False)
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
        "equipe": EQUIPE,
        "lojaId": loja_id,
        "lojaNome": loja_nome,
        "dispositivoId": dispositivo_id,
        "tag": tag,
        "motivoIA": motivo_ia,
        "requerTecnico": requer_tecnico,
    }
    resp = requests.post(
        BASE_URL,
        params={"route": "abrir-chamado"},
        json=payload,
        timeout=TIMEOUT,
        verify=False,
    )
    resp.raise_for_status()
    return resp.json()
