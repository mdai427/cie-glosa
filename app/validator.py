"""
Motor de validaciones de glosa preventiva.
Compara los campos extraídos de todos los documentos y genera hallazgos.
"""
from typing import Dict, Any, List
from app.models import Hallazgo, RiesgoNivel, SemaforoColor


def normalizar(valor) -> str:
    """Normaliza un valor para comparación: mayúsculas, sin espacios extra."""
    if valor is None:
        return ""
    return str(valor).strip().upper().replace("  ", " ")


def valores_coinciden(v1, v2) -> bool:
    """Compara dos valores normalizados."""
    n1 = normalizar(v1)
    n2 = normalizar(v2)
    if not n1 or not n2:
        return True  # Si falta uno, no podemos comparar
    return n1 == n2


def valores_numericos_coinciden(v1, v2, tolerancia=0.01) -> bool:
    """Compara valores numéricos extrayendo solo los dígitos."""
    def extraer_numero(v):
        if v is None:
            return None
        import re
        # Quitar comas de miles y dejar punto decimal
        s = str(v).replace(",", "").replace("$", "").strip()
        nums = re.findall(r'\d+\.?\d*', s)
        return float(nums[0]) if nums else None

    n1 = extraer_numero(v1)
    n2 = extraer_numero(v2)
    if n1 is None or n2 is None:
        return True
    if n1 == 0 and n2 == 0:
        return True
    diferencia = abs(n1 - n2) / max(abs(n1), abs(n2)) if max(abs(n1), abs(n2)) > 0 else 0
    return diferencia <= tolerancia


def hallazgo(campo, val_ped, val_doc, doc_fuente, fundamento, riesgo, accion) -> Hallazgo:
    return Hallazgo(
        campo=campo,
        valor_pedimento=str(val_ped) if val_ped else "No declarado",
        valor_documento_fuente=str(val_doc) if val_doc else "No encontrado",
        documento_fuente=doc_fuente,
        fundamento_legal=fundamento,
        riesgo=riesgo,
        accion_recomendada=accion,
        requiere_revision_humana=(riesgo in [RiesgoNivel.CRITICO, RiesgoNivel.ALTO])
    )


def validar_importador(ped: dict, factura: dict, carta: dict) -> List[Hallazgo]:
    hallazgos = []

    # RFC importador
    rfc_ped = normalizar(ped.get("rfc_importador"))
    rfc_fac = normalizar(factura.get("rfc_importador")) if factura else ""
    rfc_car = normalizar(carta.get("rfc_importador")) if carta else ""

    if rfc_ped and rfc_fac and rfc_ped != rfc_fac:
        hallazgos.append(hallazgo(
            "RFC Importador",
            ped.get("rfc_importador"), factura.get("rfc_importador"),
            "Factura Comercial",
            "Anexo 22 / RGCE 3.1.8 / Art. 76 Ley Aduanera",
            RiesgoNivel.CRITICO,
            "Corregir RFC del importador antes de validar"
        ))
    if rfc_ped and rfc_car and rfc_ped != rfc_car:
        hallazgos.append(hallazgo(
            "RFC Importador",
            ped.get("rfc_importador"), carta.get("rfc_importador"),
            "Carta 3.1.8",
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.CRITICO,
            "Corregir RFC del importador antes de validar"
        ))

    # Nombre importador
    nom_ped = normalizar(ped.get("nombre_importador"))
    nom_fac = normalizar(factura.get("nombre_importador")) if factura else ""
    if nom_ped and nom_fac:
        # Comparación flexible: si uno contiene al otro
        if nom_ped not in nom_fac and nom_fac not in nom_ped:
            # Verificar si comparten palabras clave
            palabras_ped = set(nom_ped.split())
            palabras_fac = set(nom_fac.split())
            coincidencia = len(palabras_ped & palabras_fac) / max(len(palabras_ped), 1)
            if coincidencia < 0.5:
                hallazgos.append(hallazgo(
                    "Nombre Importador",
                    ped.get("nombre_importador"), factura.get("nombre_importador"),
                    "Factura Comercial",
                    "Anexo 22 / RGCE 3.1.8",
                    RiesgoNivel.ALTO,
                    "Verificar que la razón social coincida entre pedimento y factura"
                ))

    return hallazgos


def validar_proveedor(ped: dict, factura: dict, carta: dict) -> List[Hallazgo]:
    hallazgos = []

    # Nombre proveedor
    prov_ped = normalizar(ped.get("nombre_proveedor"))
    prov_fac = normalizar(factura.get("nombre_proveedor")) if factura else ""
    if prov_ped and prov_fac:
        palabras_ped = set(prov_ped.split())
        palabras_fac = set(prov_fac.split())
        coincidencia = len(palabras_ped & palabras_fac) / max(len(palabras_ped), 1)
        if coincidencia < 0.4:
            hallazgos.append(hallazgo(
                "Nombre Proveedor",
                ped.get("nombre_proveedor"), factura.get("nombre_proveedor"),
                "Factura Comercial",
                "Anexo 22 / RGCE 3.1.8",
                RiesgoNivel.ALTO,
                "Verificar que el proveedor declarado coincida con la factura"
            ))

    # Número de factura
    nfac_ped = normalizar(ped.get("numero_factura"))
    nfac_fac = normalizar(factura.get("numero_factura")) if factura else ""
    if nfac_ped and nfac_fac and nfac_ped != nfac_fac:
        hallazgos.append(hallazgo(
            "Número de Factura",
            ped.get("numero_factura"), factura.get("numero_factura"),
            "Factura Comercial",
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.CRITICO,
            "El número de factura del pedimento no coincide con la factura cargada"
        ))

    # Fecha de factura
    fecha_ped = normalizar(ped.get("fecha_factura"))
    fecha_fac = normalizar(factura.get("fecha_factura")) if factura else ""
    if fecha_ped and fecha_fac and fecha_ped != fecha_fac:
        hallazgos.append(hallazgo(
            "Fecha de Factura",
            ped.get("fecha_factura"), factura.get("fecha_factura"),
            "Factura Comercial",
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.ALTO,
            "Verificar fecha correcta de la factura"
        ))

    return hallazgos


def validar_incoterm(ped: dict, factura: dict, carta: dict) -> List[Hallazgo]:
    hallazgos = []

    inc_ped = normalizar(ped.get("incoterm"))
    inc_fac = normalizar(factura.get("incoterm")) if factura else ""
    inc_car = normalizar(carta.get("incoterm")) if carta else ""

    # Extraer solo la clave Incoterm (3 letras)
    import re
    incoterms_validos = ["EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"]

    def extraer_incoterm(texto):
        for inc in incoterms_validos:
            if inc in texto:
                return inc
        return texto

    ped_inc = extraer_incoterm(inc_ped)
    fac_inc = extraer_incoterm(inc_fac)
    car_inc = extraer_incoterm(inc_car)

    if ped_inc and fac_inc and ped_inc != fac_inc:
        hallazgos.append(hallazgo(
            "Incoterm",
            ped.get("incoterm"), factura.get("incoterm"),
            "Factura Comercial",
            "Anexo 22, Apéndice 14 / Regla 3.1.8",
            RiesgoNivel.CRITICO,
            "El Incoterm del pedimento no coincide con la factura. Confirmar el término correcto"
        ))

    if ped_inc and car_inc and ped_inc != car_inc:
        hallazgos.append(hallazgo(
            "Incoterm",
            ped.get("incoterm"), carta.get("incoterm"),
            "Carta 3.1.8",
            "Anexo 22, Apéndice 14",
            RiesgoNivel.CRITICO,
            "El Incoterm del pedimento no coincide con la carta 3.1.8"
        ))

    # Advertencia de incrementables por Incoterm
    incoterms_sin_flete = ["EXW", "FCA", "FAS", "FOB"]
    if ped_inc in incoterms_sin_flete:
        flete_fac = factura.get("flete") if factura else None
        flete_ped = ped.get("incrementables_flete")
        if flete_fac and not flete_ped:
            hallazgos.append(hallazgo(
                "Incrementable: Flete",
                "No declarado",
                str(flete_fac),
                "Factura Comercial",
                "Art. 65 y 66 Ley Aduanera / Apéndice 14 Anexo 22",
                RiesgoNivel.CRITICO,
                f"Incoterm {ped_inc} requiere declarar flete como incrementable. Se detectó flete en factura"
            ))

    return hallazgos


def validar_moneda_valores(ped: dict, factura: dict) -> List[Hallazgo]:
    hallazgos = []
    if not factura:
        return hallazgos

    # Moneda
    mon_ped = normalizar(ped.get("moneda"))
    mon_fac = normalizar(factura.get("moneda"))
    if mon_ped and mon_fac and mon_ped != mon_fac:
        hallazgos.append(hallazgo(
            "Moneda",
            ped.get("moneda"), factura.get("moneda"),
            "Factura Comercial",
            "Anexo 22 / Art. 64 Ley Aduanera",
            RiesgoNivel.CRITICO,
            "La moneda declarada en pedimento no coincide con la factura"
        ))

    # Valor monetario factura
    val_mon_ped = ped.get("valor_moneda_factura")
    val_total_fac = factura.get("valor_total")
    if val_mon_ped and val_total_fac:
        if not valores_numericos_coinciden(val_mon_ped, val_total_fac, tolerancia=0.02):
            hallazgos.append(hallazgo(
                "Valor Moneda Factura",
                str(val_mon_ped), str(val_total_fac),
                "Factura Comercial",
                "Anexo 22 / Art. 64-66 Ley Aduanera",
                RiesgoNivel.CRITICO,
                "El valor declarado en pedimento no coincide con el total de la factura"
            ))

    return hallazgos


def validar_cove(ped: dict, cove: dict) -> List[Hallazgo]:
    hallazgos = []
    if not cove:
        return hallazgos

    # Número COVE
    cove_ped = normalizar(ped.get("numero_cove"))
    cove_doc = normalizar(cove.get("numero_cove"))
    if cove_ped and cove_doc and cove_ped != cove_doc:
        hallazgos.append(hallazgo(
            "Número de COVE",
            ped.get("numero_cove"), cove.get("numero_cove"),
            "COVE / Acuse de Valor",
            "Anexo 22 / Reglas RGCE",
            RiesgoNivel.CRITICO,
            "El número de COVE del pedimento no coincide con el COVE cargado"
        ))

    # Valor en COVE vs pedimento
    val_ped = ped.get("valor_comercial")
    val_cove = cove.get("valor")
    if val_ped and val_cove:
        if not valores_numericos_coinciden(val_ped, val_cove, tolerancia=0.05):
            hallazgos.append(hallazgo(
                "Valor en COVE",
                str(val_ped), str(val_cove),
                "COVE / Acuse de Valor",
                "Anexo 22 / RGCE",
                RiesgoNivel.ALTO,
                "El valor declarado en pedimento difiere del valor en COVE"
            ))

    return hallazgos


def validar_logistica(ped: dict, packing: dict, bl: dict) -> List[Hallazgo]:
    hallazgos = []

    # Número de BL
    bl_ped = normalizar(ped.get("numero_bl"))
    bl_doc = normalizar(bl.get("numero_bl")) if bl else ""
    if bl_ped and bl_doc and bl_ped != bl_doc:
        hallazgos.append(hallazgo(
            "Número de BL / Guía",
            ped.get("numero_bl"), bl.get("numero_bl"),
            "Bill of Lading / Documento de Transporte",
            "Anexo 22 / Art. 36-A Ley Aduanera",
            RiesgoNivel.CRITICO,
            "El número de BL del pedimento no coincide con el documento de transporte"
        ))

    # Peso bruto
    peso_ped = ped.get("peso_bruto")
    peso_pack = packing.get("peso_bruto_total") if packing else None
    peso_bl = bl.get("peso_bruto") if bl else None

    if peso_ped and peso_pack:
        if not valores_numericos_coinciden(peso_ped, peso_pack, tolerancia=0.03):
            hallazgos.append(hallazgo(
                "Peso Bruto",
                str(peso_ped), str(peso_pack),
                "Packing List",
                "Anexo 22",
                RiesgoNivel.ALTO,
                "El peso bruto del pedimento difiere del packing list"
            ))

    if peso_ped and peso_bl:
        if not valores_numericos_coinciden(peso_ped, peso_bl, tolerancia=0.03):
            hallazgos.append(hallazgo(
                "Peso Bruto",
                str(peso_ped), str(peso_bl),
                "Bill of Lading",
                "Anexo 22",
                RiesgoNivel.ALTO,
                "El peso bruto del pedimento difiere del BL"
            ))

    # Bultos
    bultos_ped = ped.get("bultos")
    bultos_pack = packing.get("total_bultos") if packing else None
    bultos_bl = bl.get("bultos") if bl else None

    if bultos_ped and bultos_pack:
        if not valores_numericos_coinciden(bultos_ped, bultos_pack, tolerancia=0.01):
            hallazgos.append(hallazgo(
                "Total de Bultos",
                str(bultos_ped), str(bultos_pack),
                "Packing List",
                "Anexo 22",
                RiesgoNivel.ALTO,
                "Los bultos declarados en pedimento no coinciden con el packing list"
            ))

    if bultos_ped and bultos_bl:
        if not valores_numericos_coinciden(bultos_ped, bultos_bl, tolerancia=0.01):
            hallazgos.append(hallazgo(
                "Total de Bultos",
                str(bultos_ped), str(bultos_bl),
                "Bill of Lading",
                "Anexo 22",
                RiesgoNivel.ALTO,
                "Los bultos declarados en pedimento no coinciden con el BL"
            ))

    return hallazgos


def validar_regla_318(factura: dict, carta: dict) -> List[Hallazgo]:
    hallazgos = []
    doc = factura or carta
    if not doc:
        return hallazgos

    fuente = "Factura Comercial" if factura else "Carta 3.1.8"

    campos_requeridos = [
        ("nombre_proveedor", "Nombre/domicilio del vendedor"),
        ("nombre_importador", "Nombre/domicilio del destinatario"),
        ("numero_factura", "Número de factura o documento equivalente"),
        ("fecha_factura", "Fecha de expedición"),
        ("moneda", "Moneda"),
        ("valor_total", "Valor total"),
    ]

    for campo_key, campo_nombre in campos_requeridos:
        if not doc.get(campo_key):
            hallazgos.append(hallazgo(
                f"Regla 3.1.8 - {campo_nombre}",
                "N/A",
                "DATO NO LOCALIZADO",
                fuente,
                "RGCE Regla 3.1.8 / Anexo 22",
                RiesgoNivel.MEDIO,
                f"Verificar que la factura incluya {campo_nombre} según regla 3.1.8"
            ))

    # Verificar descripción comercial
    desc = doc.get("descripcion_general") or ""
    if desc:
        desc_lower = desc.lower()
        solo_codigos = all(
            len(palabra) <= 6 or palabra.replace("-", "").replace("_", "").isalnum()
            for palabra in desc_lower.split()[:5]
        ) if desc_lower.split() else False
        if len(desc) < 20 or solo_codigos:
            hallazgos.append(hallazgo(
                "Regla 3.1.8 - Descripción Comercial",
                desc[:100],
                "Descripción posiblemente insuficiente",
                fuente,
                "RGCE 3.1.8 - Descripción comercial detallada",
                RiesgoNivel.MEDIO,
                "Verificar que la descripción sea comercialmente detallada, no solo códigos o SKUs"
            ))

    return hallazgos


def validar_incrementables(ped: dict, factura: dict, carta: dict) -> List[Hallazgo]:
    hallazgos = []
    if not factura and not carta:
        return hallazgos

    doc = factura or carta
    fuente = "Factura Comercial" if factura else "Carta 3.1.8"

    incrementables_detectados = []
    if doc.get("flete"):
        incrementables_detectados.append(("Flete", doc.get("flete")))
    if doc.get("seguro"):
        incrementables_detectados.append(("Seguro", doc.get("seguro")))
    if doc.get("embalaje"):
        incrementables_detectados.append(("Embalaje", doc.get("embalaje")))
    if doc.get("otros_cargos"):
        incrementables_detectados.append(("Otros Cargos", doc.get("otros_cargos")))

    flete_ped = ped.get("incrementables_flete")
    seguro_ped = ped.get("incrementables_seguro")

    for concepto, monto in incrementables_detectados:
        ped_val = flete_ped if concepto == "Flete" else (seguro_ped if concepto == "Seguro" else None)
        if not ped_val:
            hallazgos.append(hallazgo(
                f"Incrementable: {concepto}",
                "No declarado en pedimento",
                str(monto),
                fuente,
                "Art. 65 y 66 Ley Aduanera / Apéndice 14 Anexo 22",
                RiesgoNivel.CRITICO,
                f"Se detectó {concepto.lower()} en {fuente} pero no está declarado como incrementable en el pedimento"
            ))

    return hallazgos


def calcular_semaforo(hallazgos: List[Hallazgo]) -> tuple:
    """Calcula el color del semáforo y la recomendación final."""
    criticos = sum(1 for h in hallazgos if h.riesgo == RiesgoNivel.CRITICO)
    altos = sum(1 for h in hallazgos if h.riesgo == RiesgoNivel.ALTO)
    medios = sum(1 for h in hallazgos if h.riesgo == RiesgoNivel.MEDIO)
    bajos = sum(1 for h in hallazgos if h.riesgo == RiesgoNivel.BAJO)

    if criticos >= 3:
        color = SemaforoColor.NEGRO
        recomendacion = (
            f"RIESGO GRAVE. Se detectaron {criticos} hallazgos críticos, {altos} altos y {medios} medios. "
            "NO validar el pedimento. Escalar a glosa senior o dirección para revisión completa."
        )
    elif criticos >= 1:
        color = SemaforoColor.ROJO
        recomendacion = (
            f"NO VALIDAR. Se detectaron {criticos} hallazgos críticos. "
            f"Corregir la proforma antes de validar el pedimento. "
            f"Hallazgos adicionales: {altos} altos, {medios} medios, {bajos} bajos."
        )
    elif altos >= 2:
        color = SemaforoColor.AMARILLO
        recomendacion = (
            f"REVISAR ANTES DE VALIDAR. Se detectaron {altos} hallazgos altos y {medios} medios. "
            "Requiere revisión humana. Corregir observaciones antes de validar."
        )
    elif altos >= 1 or medios >= 1:
        color = SemaforoColor.AMARILLO
        recomendacion = (
            f"REVISAR. Se detectaron {altos} hallazgos altos y {medios} medios. "
            "Se recomienda revisión humana antes de validar."
        )
    else:
        color = SemaforoColor.VERDE
        recomendacion = (
            "SIN DIFERENCIAS CRÍTICAS. La proforma puede avanzar a validación. "
            f"Se registraron {bajos} observaciones menores."
        )

    return color, recomendacion, criticos, altos, medios, bajos


def ejecutar_validaciones(documentos: Dict[str, dict]) -> tuple:
    """
    Ejecuta todas las validaciones sobre los documentos extraídos.
    Retorna (lista_hallazgos, semaforo, recomendacion, conteos)
    """
    ped = documentos.get("pedimento_borrador", {})
    fac = documentos.get("factura_comercial")
    carta = documentos.get("carta_318")
    cove = documentos.get("cove")
    packing = documentos.get("packing_list")
    bl = documentos.get("bl")

    if not ped:
        return [], SemaforoColor.AMARILLO, "No se cargó pedimento/proforma. Sin datos para comparar.", 0, 0, 0, 0

    hallazgos = []
    hallazgos.extend(validar_importador(ped, fac, carta))
    hallazgos.extend(validar_proveedor(ped, fac, carta))
    hallazgos.extend(validar_incoterm(ped, fac, carta))
    hallazgos.extend(validar_moneda_valores(ped, fac))
    hallazgos.extend(validar_cove(ped, cove))
    hallazgos.extend(validar_logistica(ped, packing, bl))
    hallazgos.extend(validar_regla_318(fac, carta))
    hallazgos.extend(validar_incrementables(ped, fac, carta))

    color, recomendacion, criticos, altos, medios, bajos = calcular_semaforo(hallazgos)
    return hallazgos, color, recomendacion, criticos, altos, medios, bajos
