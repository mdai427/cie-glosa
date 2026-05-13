"""
Catálogo de NOMs, regulaciones y permisos por fracción arancelaria.
Extensible: agregar fracciones manualmente en REGULACIONES_POR_FRACCION.
"""

REGULACIONES_POR_FRACCION = {
    # Textiles y ropa
    "6101": ["NOM-004-SCFI-2006 (Productos textiles - etiquetado)", "Aviso Automático de Importación"],
    "6102": ["NOM-004-SCFI-2006 (Productos textiles - etiquetado)"],
    "6201": ["NOM-004-SCFI-2006 (Productos textiles - etiquetado)"],
    # Calzado
    "6401": ["NOM-113-SCFI-1995 (Calzado - etiquetado)", "NOM-086-SSA1 si tiene componentes médicos"],
    "6402": ["NOM-113-SCFI-1995 (Calzado - etiquetado)"],
    # Alimentos y bebidas
    "1601": ["NOM-051-SCFI/SSA1-2010 (Etiquetado alimentos)", "Registro Sanitario COFEPRIS", "Certificado Zoosanitario SENASICA"],
    "2101": ["NOM-051-SCFI/SSA1-2010 (Etiquetado alimentos)", "Registro Sanitario COFEPRIS"],
    "2106": ["NOM-051-SCFI/SSA1-2010 (Etiquetado alimentos)", "Registro Sanitario COFEPRIS"],
    "2201": ["NOM-051-SCFI/SSA1-2010 (Etiquetado alimentos)", "NOM-218-SCFI-2017 (Bebidas)", "Registro Sanitario COFEPRIS"],
    "2202": ["NOM-051-SCFI/SSA1-2010 (Etiquetado alimentos)", "Registro Sanitario COFEPRIS"],
    # Bebidas alcohólicas
    "2203": ["NOM-142-SSA1/SCFI-2014 (Bebidas alcohólicas)", "Registro Sanitario COFEPRIS", "Permiso COFEPRIS importación"],
    "2204": ["NOM-142-SSA1/SCFI-2014 (Bebidas alcohólicas)", "Registro Sanitario COFEPRIS"],
    "2208": ["NOM-142-SSA1/SCFI-2014 (Bebidas alcohólicas)", "Registro Sanitario COFEPRIS", "Permiso COFEPRIS importación"],
    # Medicamentos
    "3003": ["NOM-059-SSA1-2015 (Medicamentos)", "Registro Sanitario COFEPRIS obligatorio", "Permiso previo importación SSA", "Aviso de funcionamiento"],
    "3004": ["NOM-059-SSA1-2015 (Medicamentos)", "Registro Sanitario COFEPRIS obligatorio", "Permiso previo importación SSA"],
    # Cosméticos
    "3303": ["NOM-141-SSA1/SCFI-2012 (Cosméticos)", "Aviso de Cosméticos COFEPRIS"],
    "3304": ["NOM-141-SSA1/SCFI-2012 (Cosméticos)", "Aviso de Cosméticos COFEPRIS"],
    "3305": ["NOM-141-SSA1/SCFI-2012 (Cosméticos)", "Aviso de Cosméticos COFEPRIS"],
    # Juguetes
    "9501": ["NOM-015-SCFI-2007 (Juguetes - seguridad)", "NOM-050-SCFI-2004 (Etiquetado general)"],
    "9502": ["NOM-015-SCFI-2007 (Juguetes - seguridad)", "NOM-050-SCFI-2004 (Etiquetado general)"],
    "9503": ["NOM-015-SCFI-2007 (Juguetes - seguridad)", "NOM-050-SCFI-2004 (Etiquetado general)"],
    # Electrónicos
    "8471": ["NOM-019-SCFI-1998 (Equipos de cómputo)", "NOM-050-SCFI-2004 (Etiquetado general)"],
    "8517": ["NOM-019-SCFI-1998 (Telecomunicaciones)", "Registro IFT obligatorio", "NOM-050-SCFI-2004"],
    "8528": ["NOM-019-SCFI-1998 (Aparatos electrónicos)", "NOM-050-SCFI-2004 (Etiquetado general)"],
    # Vehículos y autopartes
    "8703": ["NOM-041-SEMARNAT-2015 (Emisiones)", "NOM-047-SEMARNAT-2014", "Permiso previo SE", "Verificación de seguridad SCT"],
    "8704": ["NOM-044-SEMARNAT-2017 (Emisiones vehículos pesados)", "Permiso previo SE"],
    "8708": ["NOM-050-SCFI-2004 (Etiquetado general)"],
    # Químicos y plásticos
    "2902": ["Permiso previo SEMARNAT", "Hoja de seguridad (NOM-018-STPS-2015)"],
    "2903": ["Permiso previo SEMARNAT", "Hoja de seguridad (NOM-018-STPS-2015)", "Posible cuota compensatoria"],
    "3901": ["NOM-050-SCFI-2004 si es producto final", "Hoja de seguridad si es materia prima"],
    "3902": ["NOM-050-SCFI-2004 si es producto final"],
    # Acero y aluminio (cuotas compensatorias frecuentes)
    "7208": ["Posible cuota compensatoria - verificar DOF vigente", "Aviso Automático de Importación"],
    "7209": ["Posible cuota compensatoria - verificar DOF vigente"],
    "7210": ["Posible cuota compensatoria - verificar DOF vigente"],
    "7214": ["Posible cuota compensatoria - verificar DOF vigente"],
    "7604": ["Posible cuota compensatoria aluminio - verificar DOF"],
    # Herramientas y ferretería
    "8201": ["NOM-050-SCFI-2004 (Etiquetado general)"],
    "8203": ["NOM-050-SCFI-2004 (Etiquetado general)"],
    # Artículos de uso doméstico
    "7321": ["NOM-003-SCFI-2014 (Aparatos de gas)", "NOM-050-SCFI-2004"],
    "8516": ["NOM-050-SCFI-2004 (Etiquetado general)", "NOM-019-SCFI (si aplica)"],
    # Productos agropecuarios
    "1001": ["Certificado Fitosanitario SENASICA", "Permiso Fitosanitario de Importación"],
    "1005": ["Certificado Fitosanitario SENASICA", "Permiso Fitosanitario de Importación"],
    "0201": ["Certificado Zoosanitario SENASICA", "Permiso Zoosanitario de Importación"],
    "0207": ["Certificado Zoosanitario SENASICA", "Permiso Zoosanitario de Importación"],
    # Armas y explosivos (control SEDENA)
    "9301": ["Permiso SEDENA obligatorio", "Licencia de importación SEDENA"],
    "9302": ["Permiso SEDENA obligatorio"],
    "3601": ["Permiso SEDENA obligatorio", "Permiso SCT para transporte"],
    # Genérico etiquetado
    "NOM_GENERAL": ["NOM-050-SCFI-2004 (Etiquetado general comercial)"],
}

# Fracciones sujetas a precios estimados SAT
PRECIOS_ESTIMADOS_SAT = [
    "0201", "0202", "0203", "0204", "0207",  # carnes
    "0302", "0303", "0304",                   # pescados
    "0402", "0403", "0404",                   # lácteos
    "2203", "2204", "2205", "2206", "2207", "2208",  # bebidas alcohólicas
    "6101", "6102", "6103", "6104", "6105", "6106",  # ropa
    "6401", "6402", "6403", "6404",           # calzado
]


def obtener_regulaciones(fraccion: str) -> dict:
    """
    Retorna regulaciones aplicables para una fracción arancelaria.
    Busca coincidencia exacta de 8 dígitos primero, luego 6, luego 4.
    """
    fraccion_limpia = fraccion.replace(".", "").replace(" ", "").strip()[:8]
    regulaciones = []

    for longitud in [8, 6, 4]:
        prefijo = fraccion_limpia[:longitud]
        if prefijo in REGULACIONES_POR_FRACCION:
            regulaciones.extend(REGULACIONES_POR_FRACCION[prefijo])
            break

    tiene_precio_estimado = any(
        fraccion_limpia.startswith(f) for f in PRECIOS_ESTIMADOS_SAT
    )

    return {
        "regulaciones": list(set(regulaciones)),
        "tiene_precio_estimado_sat": tiene_precio_estimado,
        "fraccion_analizada": fraccion_limpia,
    }
