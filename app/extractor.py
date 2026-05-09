import pdfplumber
import anthropic
import json
import os
import re
from pathlib import Path
from app.models import TipoDocumento

def get_claude_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY no configurada")
    return anthropic.Anthropic(api_key=api_key)


def extract_text_from_pdf(file_path: str) -> str:
    """Extrae texto de un PDF usando pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        text = f"[Error al leer PDF: {str(e)}]"
    return text.strip()


def extract_text_from_file(file_path: str) -> str:
    """Extrae texto según el tipo de archivo."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in [".txt", ".csv"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        # Intenta leer como texto
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except:
            return ""


def identify_document_type(text: str, filename: str) -> TipoDocumento:
    """Identifica el tipo de documento por palabras clave en el texto y nombre."""
    text_lower = text.lower()
    filename_lower = filename.lower()

    # Por nombre de archivo
    if any(k in filename_lower for k in ["pedimento", "proforma", "borrador"]):
        return TipoDocumento.PEDIMENTO
    if any(k in filename_lower for k in ["factura", "invoice", "commercial"]):
        return TipoDocumento.FACTURA
    if any(k in filename_lower for k in ["3.1.8", "318", "carta", "checklist"]):
        return TipoDocumento.CARTA_318
    if any(k in filename_lower for k in ["cove", "acuse", "valor"]):
        return TipoDocumento.COVE
    if any(k in filename_lower for k in ["packing", "lista", "empaque"]):
        return TipoDocumento.PACKING_LIST
    if any(k in filename_lower for k in ["bl", "bill", "lading", "guia", "guía", "awb", "mbl"]):
        return TipoDocumento.BL

    # Por contenido
    if any(k in text_lower for k in ["pedimento", "val. seg.", "val. fletes", "fracción arancelaria", "clave pedimento"]):
        return TipoDocumento.PEDIMENTO
    if any(k in text_lower for k in ["invoice", "commercial invoice", "factura comercial", "unit price"]):
        return TipoDocumento.FACTURA
    if any(k in text_lower for k in ["regla 3.1.8", "3.1.8", "checklist", "lista de verificación"]):
        return TipoDocumento.CARTA_318
    if any(k in text_lower for k in ["cove", "acuse de valor", "e-document"]):
        return TipoDocumento.COVE
    if any(k in text_lower for k in ["packing list", "lista de empaque", "gross weight", "net weight", "cartons"]):
        return TipoDocumento.PACKING_LIST
    if any(k in text_lower for k in ["bill of lading", "b/l", "shipper", "consignee", "notify party", "ocean freight"]):
        return TipoDocumento.BL

    return TipoDocumento.DESCONOCIDO


PROMPTS = {
    TipoDocumento.PEDIMENTO: """Eres un experto en comercio exterior mexicano. Analiza este pedimento o proforma de pedimento y extrae los datos. Devuelve ÚNICAMENTE JSON válido, sin markdown, sin explicaciones.

Formato requerido:
{
  "rfc_importador": "RFC del importador (12 o 13 caracteres)",
  "nombre_importador": "Nombre o razón social del importador",
  "domicilio_importador": "Domicilio completo del importador",
  "nombre_proveedor": "Nombre del proveedor o exportador",
  "domicilio_proveedor": "Domicilio del proveedor",
  "id_fiscal_proveedor": "ID fiscal o tax ID del proveedor extranjero",
  "numero_factura": "Número(s) de factura declarados",
  "fecha_factura": "Fecha de la factura (DD/MM/YYYY o como aparezca)",
  "incoterm": "Clave Incoterm declarado (EXW, FOB, CIF, CFR, etc.)",
  "moneda": "Clave de moneda (USD, EUR, MXN, etc.)",
  "valor_moneda_factura": "Valor en moneda de la factura (Val. Mon. Fact.)",
  "valor_dolares": "Valor en dólares",
  "valor_comercial": "Valor comercial o precio pagado en MXN",
  "valor_aduana": "Valor en aduana en MXN",
  "incrementables_flete": "Monto de flete declarado como incrementable",
  "incrementables_seguro": "Monto de seguro declarado como incrementable",
  "incrementables_otros": "Otros incrementables declarados",
  "tipo_cambio": "Tipo de cambio aplicado",
  "numero_cove": "Número de COVE declarado",
  "numero_bl": "Número de BL, guía o documento de transporte",
  "peso_bruto": "Peso bruto total declarado",
  "bultos": "Total de bultos declarados",
  "partidas": [
    {
      "numero": "número de partida",
      "descripcion": "descripción de mercancía",
      "fraccion": "fracción arancelaria",
      "nico": "NICO si aplica",
      "umc": "unidad de medida comercial",
      "cantidad_umc": "cantidad en UMC",
      "valor_partida": "valor de la partida",
      "precio_unitario": "precio unitario",
      "pais_origen": "país de origen",
      "pais_vendedor": "país vendedor",
      "identificadores": "identificadores y complementos declarados"
    }
  ]
}

Si un campo no está en el documento, usa null. Nunca inventes datos.
DOCUMENTO:
""",

    TipoDocumento.FACTURA: """Eres un experto en comercio exterior. Analiza esta factura comercial y extrae los datos. Devuelve ÚNICAMENTE JSON válido, sin markdown, sin explicaciones.

Formato requerido:
{
  "rfc_importador": "RFC del importador o buyer si aplica",
  "nombre_importador": "Nombre del comprador o destinatario",
  "domicilio_importador": "Domicilio del comprador o destinatario",
  "nombre_proveedor": "Nombre del vendedor o exportador",
  "domicilio_proveedor": "Domicilio del vendedor",
  "id_fiscal_proveedor": "ID fiscal o tax ID del vendedor",
  "numero_factura": "Número de factura o invoice",
  "fecha_factura": "Fecha de emisión",
  "incoterm": "Incoterm declarado (EXW, FOB, CIF, etc.)",
  "moneda": "Moneda de la factura (USD, EUR, etc.)",
  "valor_total": "Valor total de la factura",
  "subtotal": "Subtotal antes de cargos adicionales",
  "flete": "Monto de flete si aparece en la factura",
  "seguro": "Monto de seguro si aparece",
  "embalaje": "Cargo por embalaje si aparece",
  "otros_cargos": "Otros cargos adicionales",
  "descripcion_general": "Descripción general de las mercancías",
  "partidas": [
    {
      "numero": "número de línea",
      "descripcion": "descripción del producto",
      "cantidad": "cantidad",
      "unidad": "unidad de medida",
      "precio_unitario": "precio por unidad",
      "valor_total_linea": "valor total de la línea",
      "pais_origen": "país de origen si se indica",
      "numero_parte": "número de parte o SKU"
    }
  ]
}

Si un campo no está en el documento, usa null. Nunca inventes datos.
DOCUMENTO:
""",

    TipoDocumento.CARTA_318: """Eres un experto en comercio exterior mexicano, específicamente en la regla 3.1.8 de las RGCE. Analiza este documento (carta o checklist 3.1.8) y extrae los datos. Devuelve ÚNICAMENTE JSON válido, sin markdown.

Formato requerido:
{
  "rfc_importador": "RFC del importador",
  "nombre_importador": "Nombre o razón social del importador",
  "domicilio_importador": "Domicilio del importador",
  "nombre_proveedor": "Nombre del proveedor o vendedor",
  "domicilio_proveedor": "Domicilio del proveedor",
  "id_fiscal_proveedor": "ID fiscal del proveedor",
  "numero_factura": "Número de factura referenciada",
  "fecha_factura": "Fecha de la factura",
  "incoterm": "Incoterm acordado",
  "moneda": "Moneda de la operación",
  "valor": "Valor de la operación",
  "lugar_expedicion": "Lugar de expedición del documento",
  "fecha_expedicion": "Fecha de expedición del documento",
  "descripcion_mercancia": "Descripción de la mercancía",
  "cantidad": "Cantidad declarada",
  "unidad": "Unidad de medida",
  "valor_unitario": "Valor unitario",
  "tiene_descripcion_comercial": "true/false si la descripción es comercialmente detallada",
  "incrementables_flete": "Flete si se menciona",
  "incrementables_seguro": "Seguro si se menciona",
  "otros_incrementables": "Otros cargos adicionales mencionados"
}

Si un campo no está, usa null. Nunca inventes datos.
DOCUMENTO:
""",

    TipoDocumento.COVE: """Eres un experto en comercio exterior mexicano. Analiza este COVE (Comprobante de Valor Electrónico) o acuse de valor y extrae los datos. Devuelve ÚNICAMENTE JSON válido, sin markdown.

Formato requerido:
{
  "numero_cove": "Número de COVE o folio del acuse",
  "rfc_importador": "RFC del importador o comprador",
  "nombre_importador": "Nombre del importador",
  "nombre_proveedor": "Nombre del proveedor o vendedor",
  "numero_factura": "Número de factura vinculada al COVE",
  "fecha": "Fecha del COVE o de la transmisión",
  "valor": "Valor declarado en el COVE",
  "moneda": "Moneda del COVE",
  "descripcion": "Descripción de mercancías en el COVE",
  "cantidad": "Cantidad de mercancía",
  "unidad": "Unidad de medida",
  "fecha_factura": "Fecha de la factura vinculada"
}

Si un campo no está, usa null.
DOCUMENTO:
""",

    TipoDocumento.PACKING_LIST: """Eres un experto en comercio exterior. Analiza este packing list (lista de empaque) y extrae los datos. Devuelve ÚNICAMENTE JSON válido, sin markdown.

Formato requerido:
{
  "peso_bruto_total": "Peso bruto total (con unidad, ej: 1500 KGS)",
  "peso_neto_total": "Peso neto total si aparece",
  "total_bultos": "Total de bultos, cajas, pallets, etc.",
  "marcas_numeros": "Marcas y números del embarque",
  "descripcion_general": "Descripción general de las mercancías",
  "numero_factura": "Número de factura referenciada si aparece",
  "partidas": [
    {
      "descripcion": "descripción del ítem",
      "cantidad": "cantidad",
      "unidad": "unidad",
      "peso_bruto": "peso bruto del ítem",
      "bultos": "número de bultos del ítem"
    }
  ]
}

Si un campo no está, usa null.
DOCUMENTO:
""",

    TipoDocumento.BL: """Eres un experto en comercio exterior y logística. Analiza este Bill of Lading, guía aérea o documento de transporte y extrae los datos. Devuelve ÚNICAMENTE JSON válido, sin markdown.

Formato requerido:
{
  "numero_bl": "Número de B/L, guía aérea o documento de transporte",
  "shipper": "Nombre del embarcador (shipper/exporter)",
  "consignee": "Nombre del consignatario",
  "notify_party": "Notify party si aplica",
  "peso_bruto": "Peso bruto total declarado en el BL",
  "bultos": "Total de bultos, contenedores, piezas",
  "descripcion": "Descripción de las mercancías",
  "puerto_origen": "Puerto o aeropuerto de origen",
  "puerto_destino": "Puerto o aeropuerto de destino",
  "fecha_embarque": "Fecha de embarque",
  "marcas_numeros": "Marcas y números",
  "tipo_transporte": "Marítimo, aéreo, terrestre"
}

Si un campo no está, usa null.
DOCUMENTO:
""",

    TipoDocumento.DESCONOCIDO: """Analiza este documento y extrae todos los campos relevantes que puedas identificar para una operación de comercio exterior mexicano. Devuelve ÚNICAMENTE JSON válido con los campos que encuentres.

DOCUMENTO:
"""
}


def extract_fields_with_claude(text: str, doc_type: TipoDocumento) -> dict:
    """Usa Claude para extraer campos estructurados del texto del documento."""
    client = get_claude_client()
    prompt = PROMPTS.get(doc_type, PROMPTS[TipoDocumento.DESCONOCIDO])

    # Limitar texto para no exceder tokens (usar primeros 12000 chars)
    text_truncated = text[:12000] if len(text) > 12000 else text

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": prompt + text_truncated
                }
            ]
        )
        response_text = message.content[0].text.strip()
        # Limpiar markdown si Claude lo incluye
        response_text = re.sub(r'^```json\s*', '', response_text)
        response_text = re.sub(r'^```\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        return {"error": f"No se pudo parsear JSON: {str(e)}", "raw": response_text[:500]}
    except Exception as e:
        return {"error": str(e)}


def process_document(file_path: str, filename: str) -> dict:
    """Procesa un documento completo: extrae texto, identifica tipo y extrae campos."""
    text = extract_text_from_file(file_path)
    doc_type = identify_document_type(text, filename)
    campos = extract_fields_with_claude(text, doc_type)

    return {
        "tipo": doc_type.value,
        "nombre_archivo": filename,
        "texto_preview": text[:500] if text else "",
        "datos": campos
    }
