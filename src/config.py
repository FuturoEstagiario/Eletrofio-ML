import os

API_BASE = "https://credenciamento.eletrofrio.com.br:5900/galileo/api/api_hackathon"
API_TIMEOUT = 12
API_EQUIPE = "EletroFrio ML"

WINDOW_HOURS = 6
WINDOW_POINTS = 72
STRIDE_POINTS = 5

TEMP_CONGE_ADAS_MAX = -5
TEMP_RESFRIADOS_MAX = 12
TEMP_CONGE_ADAS_MIN = -25
TEMP_RESFRIADOS_MIN = -2
NORMAL_TEMP_THRESHOLD = 5.0

SERIES_MAP = {
    "Temperatura Ambiente": "temp",
    "Setpoint Ambiente": "setpoint",
    "Status Degelo": "degelo",
    "Estado de Funcionamento ON/OFF": "onoff",
    "Temperatura de Degelo": "temp_degelo",
    "Relé de Degelo": "rele_degelo",
    "L1 - Pressão de Sucção": "pressao_succao",
    "L1 - Pressão de Condensação": "pressao_cond",
    "L1 - Temperatura da sucção": "temp_succao",
    "L1 - Temperatura de Evaporação": "temp_evap",
    "L1 - Superaquecimento": "superaquecimento",
    "L1 - Setpoint Sucção": "setpoint_succao",
    "Abertura de válvula %": "abertura_valvula",
    "L1 - Status Compressor 1": "comp1_on",
    "L1 - Status Compressor 2": "comp2_on",
    "L1 - Status Compressor 3": "comp3_on",
    "L1 - Status Compressor 4": "comp4_on",
    "L1 - Status Compressor 5": "comp5_on",
    "L1 - Requisição de compressores": "req_compressores",
    "L1 - Status Ventilador 1": "ventilador1_on",
    "Status Condensador 1": "cond1_on",
    "Status Condensador 2": "cond2_on",
    "Temperatura Entrada do Glicol": "temp_glicol_entrada",
    "Temperatura de Saída do Glicol": "temp_glicol_saida",
    "Temperatura Subresfriamento": "temp_subresfriamento",
    "Temperatura do Ar Externo": "temp_ar_externo",
}

CRITICIDADE_MAP = {"A": 3, "M": 2, "B": 1, "C": 4}
CRITICIDADE_SCORE = {"C": 4, "A": 3, "M": 2, "B": 1, "I": 0}
CRITICIDADE_FALHA = {"C", "A"}

THRESHOLD_RISCO = 0.75

DB_PATH = os.path.join("data", "eletrofrio.db")
MODELS_DIR = "models"
REPORTS_DIR = "reports"
DATA_DIR = "dados_coletados"

MODEL_SVM = "svm_eletrofrio.pkl"
MODEL_RF = "rf_eletrofrio.pkl"
MODEL_ONECLASS = "svm_anomalia.pkl"
MODEL_SCALER = "scaler.pkl"
MODEL_FEATURE_COLS = "feature_cols.pkl"
