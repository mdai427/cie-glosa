from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum


class TipoDocumento(str, Enum):
    PEDIMENTO = "pedimento_borrador"
    FACTURA = "factura_comercial"
    CARTA_318 = "carta_318"
    COVE = "cove"
    PACKING_LIST = "packing_list"
    BL = "bl"
    DESCONOCIDO = "desconocido"


class RiesgoNivel(str, Enum):
    CRITICO = "Crítico"
    ALTO = "Alto"
    MEDIO = "Medio"
    BAJO = "Bajo"


class SemaforoColor(str, Enum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"
    NEGRO = "negro"


class Hallazgo(BaseModel):
    campo: str
    valor_pedimento: str
    valor_documento_fuente: str
    documento_fuente: str
    fundamento_legal: str
    riesgo: RiesgoNivel
    accion_recomendada: str
    requiere_revision_humana: bool = False


class DocumentoExtraido(BaseModel):
    tipo: TipoDocumento
    nombre_archivo: str
    datos: Dict[str, Any] = {}


class ResultadoGlosa(BaseModel):
    id: str
    referencia: str
    fecha_revision: str
    documentos_cargados: List[str] = []
    tipos_detectados: Dict[str, str] = {}  # archivo → tipo detectado
    campos_correctos: List[str] = []       # campos validados sin discrepancias
    hallazgos: List[Hallazgo] = []
    semaforo: SemaforoColor = SemaforoColor.VERDE
    recomendacion: str = ""
    total_criticos: int = 0
    total_altos: int = 0
    total_medios: int = 0
    total_bajos: int = 0
    estatus: str = "completado"


class RevisionRequest(BaseModel):
    referencia: Optional[str] = None
    cliente: Optional[str] = None
