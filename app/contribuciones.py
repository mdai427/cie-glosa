"""
Cálculo estimado de contribuciones de importación.
Los resultados son REFERENCIALES, no constituyen declaración fiscal.
Tasas arancelarias deben verificarse en TIGIE vigente.
"""

from dataclasses import dataclass, field
from typing import Optional

# Tasa DTA vigente (Art. 49 LFD) — 0.008 sobre valor en aduana
TASA_DTA = 0.008
DTA_MINIMO = 471.00   # Actualizar con valor DOF vigente
DTA_MAXIMO = 892.00   # Actualizar con valor DOF vigente

# IVA importación
TASA_IVA = 0.16


@dataclass
class ResultadoContribuciones:
    valor_aduana_mxn: float
    igi_estimado: float
    igi_tasa_aplicada: float
    iva_estimado: float
    dta_estimado: float
    total_estimado: float
    advertencias: list
    es_estimado: bool = True
    nota: str = "Cálculo referencial. Verificar tasas en TIGIE vigente y DOF."


def calcular_contribuciones(
    valor_aduana_mxn: float,
    fraccion: str = "",
    pais_origen: str = "",
    tiene_trato_preferencial: bool = False,
    tasa_igi_manual: Optional[float] = None,
) -> ResultadoContribuciones:
    """
    Calcula estimado de IGI, IVA y DTA.

    Args:
        valor_aduana_mxn: Valor en aduana en pesos mexicanos
        fraccion: Fracción arancelaria (8 dígitos)
        pais_origen: País de origen de la mercancía
        tiene_trato_preferencial: Si aplica trato preferencial TLC
        tasa_igi_manual: Si se conoce la tasa exacta, usarla directamente
    """
    advertencias = []

    # Determinar tasa IGI
    if tasa_igi_manual is not None:
        tasa_igi = tasa_igi_manual
    elif tiene_trato_preferencial:
        tasa_igi = 0.0
        advertencias.append(
            "Tasa 0% asumida por trato preferencial TLC — verificar que el certificado "
            "de origen sea válido y que la fracción califique"
        )
    else:
        tasa_igi = _tasa_general_por_capitulo(fraccion)
        advertencias.append(
            f"Tasa IGI estimada {tasa_igi * 100:.1f}% — verificar tasa exacta en TIGIE "
            f"vigente para fracción {fraccion}"
        )

    # Países con TLC con México
    PAISES_TLC = [
        "ESTADOS UNIDOS", "USA", "US", "CANADA", "CANADÁ", "ALEMANIA", "ESPAÑA",
        "FRANCE", "FRANCIA", "ITALIA", "COLOMBIA", "CHILE", "PERU", "PERÚ",
        "JAPÓN", "JAPON", "UNITED STATES",
    ]
    pais_upper = pais_origen.upper()
    if any(p in pais_upper for p in PAISES_TLC) and not tiene_trato_preferencial and tasa_igi > 0:
        advertencias.append(
            f"País de origen '{pais_origen}' tiene TLC con México — verificar si aplica "
            "trato preferencial para reducir o eliminar IGI"
        )

    # Cálculos
    igi = valor_aduana_mxn * tasa_igi
    base_iva = valor_aduana_mxn + igi   # IVA se calcula sobre valor aduana + IGI
    iva = base_iva * TASA_IVA
    dta = max(DTA_MINIMO, min(DTA_MAXIMO, valor_aduana_mxn * TASA_DTA))
    total = igi + iva + dta

    if valor_aduana_mxn <= 0:
        advertencias.append("Valor en aduana inválido o no encontrado — no se puede calcular")

    return ResultadoContribuciones(
        valor_aduana_mxn=round(valor_aduana_mxn, 2),
        igi_estimado=round(igi, 2),
        igi_tasa_aplicada=tasa_igi,
        iva_estimado=round(iva, 2),
        dta_estimado=round(dta, 2),
        total_estimado=round(total, 2),
        advertencias=advertencias,
    )


def _tasa_general_por_capitulo(fraccion: str) -> float:
    """
    Tasa general estimada por capítulo arancelario.
    SIMPLIFICADA — solo para referencia, verificar en TIGIE.
    """
    if not fraccion or len(fraccion) < 2:
        return 0.05

    cap_str = fraccion.replace(".", "")[:2]
    if not cap_str.isdigit():
        return 0.05
    capitulo = int(cap_str)

    tasas = [
        (range(1, 5),   0.20),   # animales vivos, carnes
        (range(5, 15),  0.15),   # productos agropecuarios
        (range(15, 25), 0.15),   # grasas, alimentos preparados
        (range(25, 28), 0.00),   # minerales, sal, cemento
        (range(28, 40), 0.05),   # químicos, plásticos
        (range(40, 44), 0.10),   # caucho, cuero
        (range(44, 50), 0.10),   # madera, papel
        (range(50, 68), 0.20),   # textiles, ropa, calzado
        (range(68, 72), 0.05),   # cerámica, vidrio
        (range(72, 84), 0.05),   # metales
        (range(84, 86), 0.00),   # maquinaria
        (range(86, 90), 0.05),   # vehículos
        (range(90, 93), 0.05),   # óptica, instrumentos
        (range(93, 94), 0.10),   # armas
        (range(94, 97), 0.15),   # muebles, juguetes
    ]

    for rango, tasa in tasas:
        if capitulo in rango:
            return tasa
    return 0.05
