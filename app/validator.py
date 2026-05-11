"""
Motor de validaciones de glosa preventiva aduanal.
Versión 2 — incluye:
  - Validación de partidas (descripción, UMC, cantidad vs factura y packing)
  - Recálculo de valor en aduana con incrementables convertidos a MXN
  - Validación 3.1.8 completa (13 campos del artículo)
"""
import re
from typing import Dict, List, Optional
from app.models import Hallazgo, RiesgoNivel, SemaforoColor


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────

def normalizar(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip().upper().replace("  ", " ")


def extraer_numero(v) -> Optional[float]:
    """Extrae el primer número de un string, soporta comas de miles y símbolo $."""
    if v is None:
        return None
    s = str(v).replace(",", "").replace("$", "").replace(" ", "")
    nums = re.findall(r'\d+\.?\d*', s)
    return float(nums[0]) if nums else None


def valores_numericos_coinciden(v1, v2, tolerancia=0.02) -> bool:
    n1 = extraer_numero(v1)
    n2 = extraer_numero(v2)
    if n1 is None or n2 is None:
        return True
    if n1 == 0 and n2 == 0:
        return True
    dif = abs(n1 - n2) / max(abs(n1), abs(n2))
    return dif <= tolerancia


def palabras_coinciden(texto1: str, texto2: str, umbral: float = 0.4) -> bool:
    """Compara dos strings por similitud de palabras clave."""
    p1 = set(normalizar(texto1).split())
    p2 = set(normalizar(texto2).split())
    # Filtrar palabras cortas o comunes
    stop = {"DE", "LA", "EL", "LOS", "LAS", "SA", "CV", "S.A.", "S.A", "AND", "THE", "OF"}
    p1 = p1 - stop
    p2 = p2 - stop
    if not p1 or not p2:
        return True
    coincidencia = len(p1 & p2) / min(len(p1), len(p2))
    return coincidencia >= umbral


def hacer_hallazgo(campo, val_ped, val_doc, doc_fuente, fundamento, riesgo, accion) -> Hallazgo:
    return Hallazgo(
        campo=campo,
        valor_pedimento=str(val_ped) if val_ped not in (None, "") else "No declarado",
        valor_documento_fuente=str(val_doc) if val_doc not in (None, "") else "No encontrado",
        documento_fuente=doc_fuente,
        fundamento_legal=fundamento,
        riesgo=riesgo,
        accion_recomendada=accion,
        requiere_revision_humana=(riesgo in [RiesgoNivel.CRITICO, RiesgoNivel.ALTO])
    )


MESES_EN = {
    "JANUARY": "01", "FEBRUARY": "02", "MARCH": "03", "APRIL": "04",
    "MAY": "05", "JUNE": "06", "JULY": "07", "AUGUST": "08",
    "SEPTEMBER": "09", "OCTOBER": "10", "NOVEMBER": "11", "DECEMBER": "12",
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "JUN": "06", "JUL": "07", "AUG": "08", "SEP": "09",
    "OCT": "10", "NOV": "11", "DEC": "12",
}
MESES_ES = {
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
    "ENE": "01", "FEB": "02", "MAR": "03", "ABR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AGO": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DIC": "12",
}


def normalizar_fecha(fecha: str) -> str:
    """
    Normaliza una fecha a formato DDMMYYYY para comparación.
    Soporta todos los formatos comunes en documentos aduanales:
      - MX:  15/03/2024 | 15-03-2024 | 15 de marzo de 2024
      - EN:  March 15, 2024 | Mar 15 2024 | 03/15/2024 | January 10 2024
      - ISO: 2024-03-15
    """
    if not fecha:
        return ""
    original = str(fecha).strip().upper()

    # ── Paso 1: detectar si hay nombre de mes y su posición ──
    todos_meses = {**MESES_ES, **MESES_EN}
    mes_num = None        # número del mes detectado por nombre
    mes_al_inicio = None  # True=mes antes del día, False=día antes del mes

    for nombre, num in sorted(todos_meses.items(), key=lambda x: -len(x[0])):
        m = re.search(r'\b' + nombre + r'\b', original)
        if m:
            mes_num = num
            # ¿Hay dígitos antes del mes? → día-mes (ES/MX escrito)
            texto_antes = original[:m.start()].strip()
            hay_digitos_antes = bool(re.search(r'\d', texto_antes))
            mes_al_inicio = not hay_digitos_antes  # True=mes primero (EN), False=día primero (ES)
            break

    # ── Paso 2: limpiar el texto ──
    f = original
    for nombre in todos_meses:
        f = re.sub(r'\b' + nombre + r'\b', ' ', f)
    f = re.sub(r'\bDE\b|\bOF\b', ' ', f)
    f = re.sub(r'[,./\-]', ' ', f)

    nums = re.findall(r'\d+', f)
    if not nums:
        return re.sub(r'\D', '', original)

    # ── Paso 3: identificar año ──
    yyyy = next((n for n in nums if len(n) == 4 and int(n) > 1900), None)
    if not yyyy:
        return re.sub(r'\D', '', original)

    rest = [n for n in nums if n != yyyy]
    if not rest:
        return re.sub(r'\D', '', original)

    # ── Paso 4: asignar día y mes ──
    if mes_num:
        # Teníamos nombre de mes → el único número restante es el día
        dd = rest[0].zfill(2) if rest else "01"
        mm = mes_num
    elif len(rest) >= 2:
        n0, n1 = int(rest[0]), int(rest[1])
        # Formato ISO ya fue manejado
        if len(nums[0]) == 4 and int(nums[0]) > 1900:
            # ISO: YYYY-MM-DD
            mm, dd = rest[0].zfill(2), rest[1].zfill(2)
        elif n0 > 12:
            dd, mm = str(n0).zfill(2), str(n1).zfill(2)   # MX: DD/MM
        elif n1 > 12:
            mm, dd = str(n0).zfill(2), str(n1).zfill(2)   # EN: MM/DD
        else:
            # Ambiguo → asumir MX (DD/MM) para documentos aduanales mexicanos
            dd, mm = str(n0).zfill(2), str(n1).zfill(2)
    else:
        return re.sub(r'\D', '', original)

    return dd + mm + yyyy


INCOTERMS_VALIDOS = ["EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"]
INCOTERMS_SIN_FLETE = ["EXW", "FCA", "FAS", "FOB"]   # Origen → flete a cargo del comprador


def extraer_incoterm(texto: str) -> str:
    t = normalizar(texto)
    for inc in INCOTERMS_VALIDOS:
        if inc in t:
            return inc
    return t


# ─────────────────────────────────────────────
# BLOQUE A — IMPORTADOR
# ─────────────────────────────────────────────

def validar_importador(ped: dict, factura: dict, carta: dict) -> List[Hallazgo]:
    h = []
    rfc_ped = normalizar(ped.get("rfc_importador"))

    for doc, fuente in [(factura, "Factura Comercial"), (carta, "Carta 3.1.8")]:
        if not doc:
            continue
        rfc_doc = normalizar(doc.get("rfc_importador"))
        if rfc_ped and rfc_doc and rfc_ped != rfc_doc:
            h.append(hacer_hallazgo(
                "RFC Importador",
                ped.get("rfc_importador"), doc.get("rfc_importador"), fuente,
                "Anexo 22 / RGCE 3.1.8 / Art. 76 Ley Aduanera",
                RiesgoNivel.CRITICO,
                f"RFC del pedimento ({rfc_ped}) difiere del {fuente} ({rfc_doc}). Corregir antes de validar."
            ))

    # Nombre importador
    nom_ped = normalizar(ped.get("nombre_importador"))
    nom_fac = normalizar(factura.get("nombre_importador")) if factura else ""
    if nom_ped and nom_fac and not palabras_coinciden(nom_ped, nom_fac, 0.5):
        h.append(hacer_hallazgo(
            "Nombre / Razón Social Importador",
            ped.get("nombre_importador"), factura.get("nombre_importador"),
            "Factura Comercial",
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.ALTO,
            "La razón social del importador no coincide entre pedimento y factura. Verificar."
        ))

    # Domicilio importador
    dom_ped = normalizar(ped.get("domicilio_importador"))
    dom_fac = normalizar(factura.get("domicilio_importador")) if factura else ""
    if dom_ped and dom_fac and not palabras_coinciden(dom_ped, dom_fac, 0.35):
        h.append(hacer_hallazgo(
            "Domicilio Importador",
            ped.get("domicilio_importador"), factura.get("domicilio_importador"),
            "Factura Comercial",
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.MEDIO,
            "El domicilio del importador difiere entre documentos. Revisar."
        ))

    return h


# ─────────────────────────────────────────────
# BLOQUE B — PROVEEDOR
# ─────────────────────────────────────────────

def validar_proveedor(ped: dict, factura: dict, carta: dict) -> List[Hallazgo]:
    h = []
    doc = factura or carta
    fuente = "Factura Comercial" if factura else "Carta 3.1.8"
    if not doc:
        return h

    # Nombre proveedor
    prov_ped = normalizar(ped.get("nombre_proveedor"))
    prov_doc = normalizar(doc.get("nombre_proveedor"))
    if prov_ped and prov_doc and not palabras_coinciden(prov_ped, prov_doc, 0.4):
        h.append(hacer_hallazgo(
            "Nombre Proveedor",
            ped.get("nombre_proveedor"), doc.get("nombre_proveedor"), fuente,
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.ALTO,
            "El proveedor declarado en pedimento no coincide con el documento fuente."
        ))

    # Domicilio proveedor
    dom_ped = normalizar(ped.get("domicilio_proveedor"))
    dom_doc = normalizar(doc.get("domicilio_proveedor"))
    if dom_ped and dom_doc and not palabras_coinciden(dom_ped, dom_doc, 0.3):
        h.append(hacer_hallazgo(
            "Domicilio Proveedor",
            ped.get("domicilio_proveedor"), doc.get("domicilio_proveedor"), fuente,
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.MEDIO,
            "El domicilio del proveedor difiere entre documentos."
        ))

    # ID fiscal proveedor
    id_ped = normalizar(ped.get("id_fiscal_proveedor"))
    id_doc = normalizar(doc.get("id_fiscal_proveedor"))
    if id_ped and id_doc and id_ped != id_doc:
        h.append(hacer_hallazgo(
            "ID Fiscal Proveedor",
            ped.get("id_fiscal_proveedor"), doc.get("id_fiscal_proveedor"), fuente,
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.ALTO,
            "El ID fiscal del proveedor no coincide entre pedimento y documento fuente."
        ))

    # Número de factura
    nfac_ped = normalizar(ped.get("numero_factura"))
    nfac_doc = normalizar(doc.get("numero_factura"))
    if nfac_ped and nfac_doc and nfac_ped != nfac_doc:
        h.append(hacer_hallazgo(
            "Número de Factura",
            ped.get("numero_factura"), doc.get("numero_factura"), fuente,
            "Anexo 22 / RGCE 3.1.8",
            RiesgoNivel.CRITICO,
            "El número de factura declarado en pedimento no coincide con el documento cargado."
        ))

    # Fecha de factura — comparación normalizada (soporta formatos MX y EN)
    fecha_ped = normalizar(ped.get("fecha_factura"))
    fecha_doc = normalizar(doc.get("fecha_factura"))
    if fecha_ped and fecha_doc and fecha_ped != fecha_doc:
        if normalizar_fecha(fecha_ped) != normalizar_fecha(fecha_doc):
            h.append(hacer_hallazgo(
                "Fecha de Factura",
                ped.get("fecha_factura"), doc.get("fecha_factura"), fuente,
                "Anexo 22 / RGCE 3.1.8",
                RiesgoNivel.ALTO,
                "La fecha de factura difiere entre el pedimento y el documento fuente."
            ))

    return h


# ─────────────────────────────────────────────
# BLOQUE C — INCOTERM
# ─────────────────────────────────────────────

def validar_incoterm(ped: dict, factura: dict, carta: dict) -> List[Hallazgo]:
    h = []
    ped_inc = extraer_incoterm(ped.get("incoterm", ""))

    for doc, fuente in [(factura, "Factura Comercial"), (carta, "Carta 3.1.8")]:
        if not doc:
            continue
        doc_inc = extraer_incoterm(doc.get("incoterm", ""))
        if ped_inc and doc_inc and ped_inc != doc_inc:
            h.append(hacer_hallazgo(
                "Incoterm",
                ped_inc, doc_inc, fuente,
                "Anexo 22, Apéndice 14 / RGCE 3.1.8",
                RiesgoNivel.CRITICO,
                f"Incoterm pedimento ({ped_inc}) ≠ {fuente} ({doc_inc}). Confirmar término correcto."
            ))

    # Si Incoterm es de origen → revisar que flete esté como incrementable
    doc = factura or carta
    fuente = "Factura Comercial" if factura else "Carta 3.1.8"
    if ped_inc in INCOTERMS_SIN_FLETE and doc:
        flete_doc = doc.get("flete")
        seguro_doc = doc.get("seguro")
        flete_ped = ped.get("incrementables_flete")
        seguro_ped = ped.get("incrementables_seguro")

        if flete_doc and not flete_ped:
            h.append(hacer_hallazgo(
                "Incrementable: Flete",
                "No declarado", str(flete_doc), fuente,
                "Art. 65-66 Ley Aduanera / Apéndice 14 Anexo 22",
                RiesgoNivel.CRITICO,
                f"Incoterm {ped_inc}: el flete es a cargo del importador y debe declararse como incrementable."
            ))

        if seguro_doc and not seguro_ped:
            h.append(hacer_hallazgo(
                "Incrementable: Seguro",
                "No declarado", str(seguro_doc), fuente,
                "Art. 65-66 Ley Aduanera / Apéndice 14 Anexo 22",
                RiesgoNivel.CRITICO,
                f"Incoterm {ped_inc}: el seguro es a cargo del importador y debe declararse como incrementable."
            ))

    return h


# ─────────────────────────────────────────────
# BLOQUE D — MONEDA, VALORES E INCREMENTABLES
# ─────────────────────────────────────────────

def validar_moneda_valores(ped: dict, factura: dict) -> List[Hallazgo]:
    h = []
    if not factura:
        return h

    # Moneda
    mon_ped = normalizar(ped.get("moneda"))
    mon_fac = normalizar(factura.get("moneda"))
    if mon_ped and mon_fac and mon_ped != mon_fac:
        h.append(hacer_hallazgo(
            "Moneda",
            ped.get("moneda"), factura.get("moneda"),
            "Factura Comercial",
            "Anexo 22 / Art. 64 Ley Aduanera",
            RiesgoNivel.CRITICO,
            "La moneda del pedimento no coincide con la factura."
        ))

    # Val. Mon. Fact. vs subtotal factura (sin cargos adicionales)
    val_mon_ped = extraer_numero(ped.get("valor_moneda_factura"))
    subtotal_fac = extraer_numero(factura.get("subtotal") or factura.get("valor_total"))
    if val_mon_ped and subtotal_fac:
        if not valores_numericos_coinciden(val_mon_ped, subtotal_fac, tolerancia=0.02):
            h.append(hacer_hallazgo(
                "Valor Moneda Factura (Val. Mon. Fact.)",
                ped.get("valor_moneda_factura"), factura.get("subtotal") or factura.get("valor_total"),
                "Factura Comercial",
                "Anexo 22 / Art. 64-66 Ley Aduanera",
                RiesgoNivel.CRITICO,
                "El Val. Mon. Fact. del pedimento no coincide con el valor de la factura. Recalcular."
            ))

    # Recálculo del valor en aduana
    h.extend(_validar_valor_aduana(ped, factura))

    return h


def _validar_valor_aduana(ped: dict, factura: dict) -> List[Hallazgo]:
    """
    Verifica que: Valor en aduana ≈ Valor comercial + Flete + Seguro + Otros incrementables
    Todo convertido a MXN usando el tipo de cambio del pedimento.
    """
    h = []
    tc = extraer_numero(ped.get("tipo_cambio"))
    val_aduana_ped = extraer_numero(ped.get("valor_aduana"))
    val_comercial = extraer_numero(ped.get("valor_comercial"))

    if not tc or not val_aduana_ped or not val_comercial:
        return h

    # Sumar incrementables declarados en pedimento
    flete_ped_mxn   = (extraer_numero(ped.get("incrementables_flete"))   or 0)
    seguro_ped_mxn  = (extraer_numero(ped.get("incrementables_seguro"))  or 0)
    otros_ped_mxn   = (extraer_numero(ped.get("incrementables_otros"))   or 0)

    valor_aduana_calculado = val_comercial + flete_ped_mxn + seguro_ped_mxn + otros_ped_mxn

    if not valores_numericos_coinciden(val_aduana_ped, valor_aduana_calculado, tolerancia=0.02):
        h.append(hacer_hallazgo(
            "Valor en Aduana (recálculo)",
            f"{val_aduana_ped:,.2f} MXN",
            f"{valor_aduana_calculado:,.2f} MXN (comercial + incrementables)",
            "Pedimento",
            "Art. 64-66 Ley Aduanera / Anexo 22",
            RiesgoNivel.CRITICO,
            f"Valor en aduana declarado ({val_aduana_ped:,.2f}) ≠ Valor calculado ({valor_aduana_calculado:,.2f}). Revisar incrementables."
        ))

    # Verificar si hay incrementables en factura que no se sumaron al valor en aduana
    if factura:
        flete_fac = extraer_numero(factura.get("flete")) or 0
        seguro_fac = extraer_numero(factura.get("seguro")) or 0

        if flete_fac > 0 and flete_ped_mxn == 0:
            flete_mxn = flete_fac * tc
            h.append(hacer_hallazgo(
                "Incrementable Flete — Impacto en Valor Aduana",
                "No declarado",
                f"{flete_fac} {ped.get('moneda','USD')} = ~{flete_mxn:,.2f} MXN",
                "Factura Comercial",
                "Art. 65-66 Ley Aduanera",
                RiesgoNivel.CRITICO,
                f"Flete no declarado. Impacto estimado en valor en aduana: +${flete_mxn:,.2f} MXN (TC: {tc})"
            ))

        if seguro_fac > 0 and seguro_ped_mxn == 0:
            seguro_mxn = seguro_fac * tc
            h.append(hacer_hallazgo(
                "Incrementable Seguro — Impacto en Valor Aduana",
                "No declarado",
                f"{seguro_fac} {ped.get('moneda','USD')} = ~{seguro_mxn:,.2f} MXN",
                "Factura Comercial",
                "Art. 65-66 Ley Aduanera",
                RiesgoNivel.CRITICO,
                f"Seguro no declarado. Impacto estimado en valor en aduana: +${seguro_mxn:,.2f} MXN (TC: {tc})"
            ))

    return h


# ─────────────────────────────────────────────
# BLOQUE E — COVE
# ─────────────────────────────────────────────

def validar_cove(ped: dict, cove: dict) -> List[Hallazgo]:
    h = []
    if not cove:
        return h

    cove_ped = normalizar(ped.get("numero_cove"))
    cove_doc = normalizar(cove.get("numero_cove"))
    if cove_ped and cove_doc and cove_ped != cove_doc:
        h.append(hacer_hallazgo(
            "Número de COVE",
            ped.get("numero_cove"), cove.get("numero_cove"),
            "COVE / Acuse de Valor",
            "Anexo 22 / RGCE",
            RiesgoNivel.CRITICO,
            "El número de COVE del pedimento no coincide con el COVE cargado."
        ))

    # Factura vinculada en COVE
    nfac_ped = normalizar(ped.get("numero_factura"))
    nfac_cove = normalizar(cove.get("numero_factura"))
    if nfac_ped and nfac_cove and nfac_ped != nfac_cove:
        h.append(hacer_hallazgo(
            "Factura Vinculada en COVE",
            ped.get("numero_factura"), cove.get("numero_factura"),
            "COVE / Acuse de Valor",
            "Anexo 22 / RGCE",
            RiesgoNivel.ALTO,
            "La factura vinculada en el COVE difiere del número de factura del pedimento."
        ))

    # Valor en COVE vs pedimento
    val_ped = extraer_numero(ped.get("valor_comercial"))
    val_cove = extraer_numero(cove.get("valor"))
    if val_ped and val_cove and not valores_numericos_coinciden(val_ped, val_cove, 0.05):
        h.append(hacer_hallazgo(
            "Valor en COVE",
            ped.get("valor_comercial"), cove.get("valor"),
            "COVE / Acuse de Valor",
            "Anexo 22 / RGCE",
            RiesgoNivel.ALTO,
            "El valor declarado en pedimento difiere del valor en COVE."
        ))

    # Proveedor en COVE
    prov_ped = normalizar(ped.get("nombre_proveedor"))
    prov_cove = normalizar(cove.get("nombre_proveedor"))
    if prov_ped and prov_cove and not palabras_coinciden(prov_ped, prov_cove, 0.4):
        h.append(hacer_hallazgo(
            "Proveedor en COVE",
            ped.get("nombre_proveedor"), cove.get("nombre_proveedor"),
            "COVE / Acuse de Valor",
            "Anexo 22 / RGCE",
            RiesgoNivel.ALTO,
            "El proveedor declarado en el COVE no coincide con el del pedimento."
        ))

    return h


# ─────────────────────────────────────────────
# BLOQUE F — LOGÍSTICA (Peso, Bultos, BL)
# ─────────────────────────────────────────────

def validar_logistica(ped: dict, packing: dict, bl: dict) -> List[Hallazgo]:
    h = []

    # Número BL
    bl_ped = normalizar(ped.get("numero_bl"))
    bl_doc = normalizar(bl.get("numero_bl")) if bl else ""
    if bl_ped and bl_doc and bl_ped != bl_doc:
        h.append(hacer_hallazgo(
            "Número BL / Guía",
            ped.get("numero_bl"), bl.get("numero_bl"),
            "Bill of Lading",
            "Anexo 22 / Art. 36-A Ley Aduanera",
            RiesgoNivel.CRITICO,
            "El número de BL del pedimento no coincide con el documento de transporte."
        ))

    # Peso bruto
    peso_ped = extraer_numero(ped.get("peso_bruto"))
    for doc, fuente in [(packing, "Packing List"), (bl, "Bill of Lading")]:
        if not doc:
            continue
        campo = "peso_bruto_total" if fuente == "Packing List" else "peso_bruto"
        peso_doc = extraer_numero(doc.get(campo))
        if peso_ped and peso_doc and not valores_numericos_coinciden(peso_ped, peso_doc, 0.03):
            h.append(hacer_hallazgo(
                f"Peso Bruto vs {fuente}",
                f"{peso_ped} KGS", f"{peso_doc} KGS", fuente,
                "Anexo 22",
                RiesgoNivel.ALTO,
                f"Peso bruto del pedimento ({peso_ped} kg) difiere del {fuente} ({peso_doc} kg)."
            ))

    # Bultos
    bultos_ped = extraer_numero(ped.get("bultos"))
    for doc, fuente in [(packing, "Packing List"), (bl, "Bill of Lading")]:
        if not doc:
            continue
        bultos_doc = extraer_numero(doc.get("total_bultos") if fuente == "Packing List" else doc.get("bultos"))
        if bultos_ped and bultos_doc and not valores_numericos_coinciden(bultos_ped, bultos_doc, 0.01):
            h.append(hacer_hallazgo(
                f"Total Bultos vs {fuente}",
                str(int(bultos_ped)), str(int(bultos_doc)), fuente,
                "Anexo 22",
                RiesgoNivel.ALTO,
                f"Bultos en pedimento ({int(bultos_ped)}) difieren del {fuente} ({int(bultos_doc)})."
            ))

    return h


# ─────────────────────────────────────────────
# BLOQUE G — PARTIDAS (nuevo en v2)
# ─────────────────────────────────────────────

def validar_partidas(ped: dict, factura: dict, packing: dict) -> List[Hallazgo]:
    """
    Compara las partidas del pedimento contra factura y packing list:
    - Descripción de la mercancía
    - Unidad de medida comercial (UMC)
    - Cantidad UMC
    - Precio unitario
    - Valor por partida
    """
    h = []
    partidas_ped = ped.get("partidas") or []
    if not partidas_ped or not isinstance(partidas_ped, list):
        return h

    partidas_fac = (factura.get("partidas") or []) if factura else []
    partidas_pack = (packing.get("partidas") or []) if packing else []

    for i, p_ped in enumerate(partidas_ped):
        if not isinstance(p_ped, dict):
            continue

        num_partida = p_ped.get("numero") or str(i + 1)
        desc_ped = normalizar(p_ped.get("descripcion") or "")
        umc_ped = normalizar(p_ped.get("umc") or "")
        cant_ped = extraer_numero(p_ped.get("cantidad_umc"))
        precio_ped = extraer_numero(p_ped.get("precio_unitario"))

        # ── vs Factura ──
        p_fac = partidas_fac[i] if i < len(partidas_fac) else None
        if p_fac and isinstance(p_fac, dict):

            # Descripción
            desc_fac = normalizar(p_fac.get("descripcion") or "")
            if desc_ped and desc_fac and not palabras_coinciden(desc_ped, desc_fac, 0.35):
                h.append(hacer_hallazgo(
                    f"Partida {num_partida} — Descripción",
                    desc_ped[:120], desc_fac[:120],
                    "Factura Comercial",
                    "Anexo 22 / RGCE 3.1.8",
                    RiesgoNivel.ALTO,
                    f"La descripción de la partida {num_partida} del pedimento difiere de la factura."
                ))

            # UMC vs unidad factura
            umc_fac = normalizar(p_fac.get("unidad") or "")
            if umc_ped and umc_fac:
                # Mapeamos abreviaciones comunes
                UMC_MAP = {"PZA": ["PCS", "PC", "PIECE", "PIECES", "PZ", "PZA", "UNIT", "UNITS"],
                           "KG":  ["KGS", "KG", "KILO", "KILOS", "KILOGRAM"],
                           "LT":  ["LTR", "LITER", "LITERS", "LT"],
                           "MT":  ["MTR", "METER", "METERS", "MT", "M"],
                           "PAR": ["PAIR", "PAIRS", "PAR"]}
                def mismo_umc(u1, u2):
                    for canon, variantes in UMC_MAP.items():
                        if u1 in variantes and u2 in variantes:
                            return True
                    return u1 == u2
                if not mismo_umc(umc_ped, umc_fac):
                    h.append(hacer_hallazgo(
                        f"Partida {num_partida} — UMC",
                        umc_ped, umc_fac,
                        "Factura Comercial",
                        "Anexo 22",
                        RiesgoNivel.ALTO,
                        f"La unidad de medida (UMC) de la partida {num_partida} difiere de la factura."
                    ))

            # Cantidad UMC
            cant_fac = extraer_numero(p_fac.get("cantidad"))
            if cant_ped and cant_fac and not valores_numericos_coinciden(cant_ped, cant_fac, 0.01):
                h.append(hacer_hallazgo(
                    f"Partida {num_partida} — Cantidad UMC",
                    str(cant_ped), str(cant_fac),
                    "Factura Comercial",
                    "Anexo 22",
                    RiesgoNivel.CRITICO,
                    f"La cantidad de la partida {num_partida} ({cant_ped}) no coincide con la factura ({cant_fac})."
                ))

            # Precio unitario
            precio_fac = extraer_numero(p_fac.get("precio_unitario"))
            if precio_ped and precio_fac and not valores_numericos_coinciden(precio_ped, precio_fac, 0.02):
                h.append(hacer_hallazgo(
                    f"Partida {num_partida} — Precio Unitario",
                    str(precio_ped), str(precio_fac),
                    "Factura Comercial",
                    "Anexo 22 / Art. 64 Ley Aduanera",
                    RiesgoNivel.CRITICO,
                    f"El precio unitario de la partida {num_partida} difiere entre pedimento y factura."
                ))

        # ── vs Packing List ──
        p_pack = partidas_pack[i] if i < len(partidas_pack) else None
        if p_pack and isinstance(p_pack, dict):
            cant_pack = extraer_numero(p_pack.get("cantidad"))
            if cant_ped and cant_pack and not valores_numericos_coinciden(cant_ped, cant_pack, 0.01):
                h.append(hacer_hallazgo(
                    f"Partida {num_partida} — Cantidad vs Packing",
                    str(cant_ped), str(cant_pack),
                    "Packing List",
                    "Anexo 22",
                    RiesgoNivel.ALTO,
                    f"La cantidad de la partida {num_partida} del pedimento difiere del packing list."
                ))

    return h


# ─────────────────────────────────────────────
# BLOQUE H — REGLA 3.1.8 COMPLETA (13 campos)
# ─────────────────────────────────────────────

def validar_regla_318(factura: dict, carta: dict) -> List[Hallazgo]:
    """
    Valida los 13 campos requeridos por la Regla 3.1.8 de las RGCE.
    """
    h = []
    doc = factura or carta
    if not doc:
        return h
    fuente = "Factura Comercial" if factura else "Carta 3.1.8"

    # Los 13 campos que exige la regla 3.1.8
    campos_318 = [
        ("lugar_expedicion",    "Lugar de expedición"),
        ("fecha_factura",       "Fecha de expedición"),
        ("nombre_importador",   "Nombre y domicilio del destinatario"),
        ("nombre_proveedor",    "Nombre y domicilio del vendedor/proveedor"),
        ("numero_factura",      "Número de factura o documento equivalente"),
        ("descripcion_general", "Descripción comercial detallada de la mercancía"),
        ("moneda",              "Moneda de la operación"),
        ("valor_total",         "Valor total de la operación"),
    ]
    # Campos extra de la carta 3.1.8
    if carta:
        campos_318 += [
            ("cantidad",        "Cantidad de unidades"),
            ("unidad",          "Unidad de medida"),
            ("valor_unitario",  "Valor unitario"),
        ]

    for campo_key, campo_nombre in campos_318:
        val = doc.get(campo_key)
        if not val:
            h.append(hacer_hallazgo(
                f"3.1.8 — {campo_nombre}",
                "N/A", "NO LOCALIZADO EN DOCUMENTO", fuente,
                "RGCE Regla 3.1.8",
                RiesgoNivel.MEDIO,
                f"Verificar que el documento incluya: {campo_nombre}"
            ))

    # Verificación especial: descripción comercial detallada
    desc = str(doc.get("descripcion_general") or "")
    if desc:
        palabras = desc.split()
        # Detectar si la descripción es solo códigos/SKUs (menos de 3 palabras reales)
        palabras_reales = [p for p in palabras if len(p) > 4 and not p.replace("-", "").replace("_", "").isdigit()]
        if len(palabras_reales) < 2 or len(desc) < 15:
            h.append(hacer_hallazgo(
                "3.1.8 — Descripción Comercial Detallada",
                desc[:100], "Descripción insuficiente o solo códigos/SKUs",
                fuente,
                "RGCE 3.1.8 — Descripción comercial detallada",
                RiesgoNivel.MEDIO,
                "La descripción debe ser comercialmente detallada. No se aceptan solo códigos, SKUs o números de parte."
            ))

    # Verificar domicilios (deben estar en el mismo campo o detectables)
    dom_imp = doc.get("domicilio_importador")
    dom_prov = doc.get("domicilio_proveedor")
    if not dom_imp:
        h.append(hacer_hallazgo(
            "3.1.8 — Domicilio del Destinatario",
            "N/A", "NO LOCALIZADO", fuente,
            "RGCE Regla 3.1.8",
            RiesgoNivel.MEDIO,
            "Verificar que la factura incluya el domicilio completo del destinatario/importador."
        ))
    if not dom_prov:
        h.append(hacer_hallazgo(
            "3.1.8 — Domicilio del Vendedor",
            "N/A", "NO LOCALIZADO", fuente,
            "RGCE Regla 3.1.8",
            RiesgoNivel.MEDIO,
            "Verificar que la factura incluya el domicilio completo del vendedor/proveedor."
        ))

    return h


# ─────────────────────────────────────────────
# BLOQUE I — INCREMENTABLES ADICIONALES
# ─────────────────────────────────────────────

def validar_incrementables(ped: dict, factura: dict, carta: dict) -> List[Hallazgo]:
    """Detecta incrementables en factura/carta que no están en el pedimento."""
    h = []
    doc = factura or carta
    if not doc:
        return h
    fuente = "Factura Comercial" if factura else "Carta 3.1.8"

    conceptos = [
        ("embalaje",      "Embalaje/Packing",   ped.get("incrementables_otros")),
        ("otros_cargos",  "Otros Cargos",        ped.get("incrementables_otros")),
    ]

    for campo_doc, nombre, campo_ped in conceptos:
        monto = doc.get(campo_doc)
        if monto and not campo_ped:
            h.append(hacer_hallazgo(
                f"Incrementable: {nombre}",
                "No declarado", str(monto), fuente,
                "Art. 65-66 Ley Aduanera / Apéndice 14 Anexo 22",
                RiesgoNivel.ALTO,
                f"Se detectó '{nombre}' en {fuente} pero no está declarado como incrementable en el pedimento."
            ))

    return h


# ─────────────────────────────────────────────
# SEMÁFORO
# ─────────────────────────────────────────────

def calcular_semaforo(hallazgos: List[Hallazgo]) -> tuple:
    criticos = sum(1 for h in hallazgos if h.riesgo == RiesgoNivel.CRITICO)
    altos    = sum(1 for h in hallazgos if h.riesgo == RiesgoNivel.ALTO)
    medios   = sum(1 for h in hallazgos if h.riesgo == RiesgoNivel.MEDIO)
    bajos    = sum(1 for h in hallazgos if h.riesgo == RiesgoNivel.BAJO)

    if criticos >= 3:
        color = SemaforoColor.NEGRO
        rec = (f"RIESGO GRAVE. {criticos} hallazgos críticos, {altos} altos, {medios} medios. "
               "NO validar. Escalar a glosa senior o dirección.")
    elif criticos >= 1:
        color = SemaforoColor.ROJO
        rec = (f"NO VALIDAR. {criticos} hallazgos críticos detectados. "
               f"Corregir proforma antes de validar. ({altos} altos, {medios} medios, {bajos} bajos)")
    elif altos >= 2:
        color = SemaforoColor.AMARILLO
        rec = (f"REVISAR ANTES DE VALIDAR. {altos} hallazgos altos y {medios} medios. "
               "Requiere revisión humana.")
    elif altos >= 1 or medios >= 1:
        color = SemaforoColor.AMARILLO
        rec = (f"REVISAR. {altos} hallazgos altos, {medios} medios. "
               "Se recomienda revisión antes de validar.")
    else:
        color = SemaforoColor.VERDE
        rec = (f"SIN DIFERENCIAS CRÍTICAS. La proforma puede avanzar a validación. "
               f"{bajos} observaciones menores.")

    return color, rec, criticos, altos, medios, bajos


# ─────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────

def ejecutar_validaciones(documentos: Dict[str, dict]) -> tuple:
    ped    = documentos.get("pedimento_borrador", {})
    fac    = documentos.get("factura_comercial")
    carta  = documentos.get("carta_318")
    cove   = documentos.get("cove")
    packing= documentos.get("packing_list")
    bl     = documentos.get("bl")

    if not ped:
        return [], SemaforoColor.AMARILLO, "No se cargó pedimento/proforma. Sin datos para comparar.", 0, 0, 0, 0

    hallazgos = []
    hallazgos.extend(validar_importador(ped, fac, carta))
    hallazgos.extend(validar_proveedor(ped, fac, carta))
    hallazgos.extend(validar_incoterm(ped, fac, carta))
    hallazgos.extend(validar_moneda_valores(ped, fac))
    hallazgos.extend(validar_cove(ped, cove))
    hallazgos.extend(validar_logistica(ped, packing, bl))
    hallazgos.extend(validar_partidas(ped, fac, packing))       # ← NUEVO v2
    hallazgos.extend(validar_regla_318(fac, carta))              # ← MEJORADO v2
    hallazgos.extend(validar_incrementables(ped, fac, carta))

    color, rec, criticos, altos, medios, bajos = calcular_semaforo(hallazgos)
    return hallazgos, color, rec, criticos, altos, medios, bajos
