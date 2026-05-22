"""
Generador del Reporte de Glosa Preventiva Experta.
Usa Claude con el prompt del Agente Glosador Aduanal para producir
un dictamen narrativo completo en formato Markdown.
"""
import json
import time
from app.extractor import get_claude_client

# ─────────────────────────────────────────────
# SYSTEM PROMPT DEL EXPERTO GLOSADOR
# ─────────────────────────────────────────────
SYSTEM_GLOSADOR = """Eres un Agente Glosador Aduanal Experto con más de 20 años de experiencia en comercio exterior mexicano. Tu función es realizar una GLOSA PREVENTIVA completa y detallada de un pedimento aduanal ANTES de su validación ante el SAT/VUCEM, actuando como si fueras el glosador más meticuloso de un agente aduanal certificado (AA) en México.

DOCUMENTOS QUE RECIBES Y CÓMO PROCESARLOS
Recibirás los datos ya extraídos de los documentos. SIEMPRE convierte los valores monetarios a PESOS MEXICANOS (MXN) usando el tipo de cambio del pedimento (Art. 20 CFF). Si el TC no está disponible, indícalo como alerta.

CONVERSIÓN DE MONEDAS — REGLA OBLIGATORIA:
- Identifica la divisa (USD, EUR, CNY, JPY, etc.)
- Aplica el TC del pedimento o indica: "⚠️ VERIFICAR: TC aplicado [X] vs. TC SAT publicado para [fecha]"
- Muestra el cálculo: [Valor divisa] × [TC] = [Valor MXN]
- Cualquier diferencia en TC vs. publicado es hallazgo CRÍTICO

REGLAS DE COMPORTAMIENTO:
- NUNCA omitas una sección del reporte aunque no tengas todos los documentos
- Si un documento NO fue cargado: indica "⚠️ [Documento] NO CARGADO — no se pudo verificar [puntos afectados]"
- Si detectas posible subfacturación o sobrefacturación: ERROR CRÍTICO con cálculo
- Inconsistencia entre BL y factura en consignatario: ERROR CRÍTICO (puede causar embargo)
- Aplica normativa vigente: LA, RG CAAAREM, Anexo 22, TIGIE, CFF, LFD, Ley IVA, Ley IEPS
- Usa lenguaje técnico aduanal mexicano
- Al final SIEMPRE da el dictamen: 🟢 APTO / 🟡 CON OBSERVACIONES / 🔴 NO VALIDAR"""

# ─────────────────────────────────────────────
# PROMPT DE USUARIO — construir contexto de datos
# ─────────────────────────────────────────────
def _construir_contexto(documentos: dict, hallazgos_previos: list, campos_correctos: list) -> str:
    """Serializa los documentos extraídos y hallazgos para enviarlos a Claude."""

    nombres_tipo = {
        "pedimento_borrador": "PEDIMENTO (Borrador)",
        "factura_comercial":  "FACTURA COMERCIAL",
        "carta_318":          "CARTA 3.1.8",
        "cove":               "COVE / Acuse de Valor",
        "packing_list":       "PACKING LIST",
        "bl":                 "BILL OF LADING / GUÍA",
    }

    lineas = ["# DATOS EXTRAÍDOS DE LOS DOCUMENTOS\n"]

    for tipo, datos in documentos.items():
        if not datos or not isinstance(datos, dict):
            continue
        nombre = nombres_tipo.get(tipo, tipo.upper())
        lineas.append(f"\n## {nombre}")
        # Excluir campos internos del extractor
        campos = {k: v for k, v in datos.items()
                  if not k.startswith("_") and v not in (None, "", [], {})}
        lineas.append("```json")
        lineas.append(json.dumps(campos, ensure_ascii=False, indent=2))
        lineas.append("```")

    tipos_cargados = set(documentos.keys())
    todos = {"pedimento_borrador", "factura_comercial", "carta_318", "cove", "packing_list", "bl"}
    faltantes = todos - tipos_cargados
    if faltantes:
        lineas.append("\n## DOCUMENTOS NO CARGADOS")
        for f in faltantes:
            lineas.append(f"- ⚠️ {nombres_tipo.get(f, f)} — NO CARGADO")

    if hallazgos_previos:
        lineas.append("\n## HALLAZGOS YA DETECTADOS POR EL SISTEMA (referencia)")
        for h in hallazgos_previos:
            if hasattr(h, 'campo'):
                lineas.append(f"- [{h.riesgo}] {h.campo}: pedimento='{h.valor_pedimento}' vs doc='{h.valor_documento_fuente}'")

    if campos_correctos:
        lineas.append("\n## CAMPOS VERIFICADOS SIN DISCREPANCIAS (referencia)")
        for c in campos_correctos:
            lineas.append(f"- ✅ {c}")

    lineas.append("""
---

Con base en los datos anteriores, genera el REPORTE DE GLOSA PREVENTIVA completo en el siguiente formato EXACTO:

---
# 📋 REPORTE DE GLOSA PREVENTIVA
**Operación:** [referencia del pedimento] | **Cliente:** [importador] | **Fecha:** [fecha análisis]
**Tipo de Operación:** [Importación/Exportación/Temporal] | **Régimen:** [Definitivo/Temporal/etc.]

---
## ✅ PUNTOS CORRECTOS
[Lista específica de elementos verificados y correctos. Sé específico con valores.]

---
## ⚠️ ALERTAS (requieren revisión antes de validar)
Para cada alerta:
- **Hallazgo:** [descripción]
- **Documentos afectados:** [lista]
- **Diferencia detectada:** [valor pedimento] vs [valor documento]
- **Impacto fiscal estimado:** [si aplica, en MXN]
- **Acción requerida:** [qué corregir]

---
## ❌ ERRORES CRÍTICOS (NO validar hasta corregir)
[Misma estructura que alertas. Si no hay errores críticos, escribe "Sin errores críticos detectados."]

---
## 💰 RESUMEN DE CONTRIBUCIONES VERIFICADAS
| Contribución | Base (MXN) | Tasa | Declarado | Calculado | Diferencia |
|---|---|---|---|---|---|
| IGI/IGE | | | | | |
| IVA | | | | | |
| IEPS | | | | | |
| DTA | | | | | |
| Cuotas comp. | | | | | |
| **TOTAL** | | | | | |

---
## 📊 DATOS CLAVE EXTRAÍDOS
| Campo | Valor en Pedimento | Valor en Documentos | ¿Coincide? |
|---|---|---|---|
| Fracción arancelaria | | | |
| Valor comercial | | | |
| Tipo de cambio | | | |
| Valor en aduana (MXN) | | | |
| Número de BL/AWB | | | |
| Número de factura | | | |
| Número de bultos | | | |
| Peso bruto | | | |
| País de origen | | | |
| Incoterm | | | |

---
## 🔒 DICTAMEN FINAL DEL GLOSADOR
**Estado:** [🟢 APTO PARA VALIDAR / 🟡 VALIDAR CON OBSERVACIONES / 🔴 NO VALIDAR — CORREGIR PRIMERO]

**Resumen ejecutivo:** [2-3 líneas sobre el estado general]

**Puntos pendientes antes de validar:**
1. [Lista numerada]
""")

    return "\n".join(lineas)


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────
def generar_reporte_glosa(
    documentos: dict,
    hallazgos: list,
    campos_correctos: list,
    referencia: str = "",
    fecha: str = ""
) -> str:
    """
    Genera el reporte narrativo completo de glosa preventiva usando Claude.
    Retorna el texto en Markdown. En caso de error retorna mensaje de error.
    """
    client = get_claude_client()
    contexto = _construir_contexto(documentos, hallazgos, campos_correctos)

    for intento in range(3):
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8192,
                system=SYSTEM_GLOSADOR,
                messages=[{"role": "user", "content": contexto}]
            )
            return msg.content[0].text.strip()
        except Exception as e:
            err = str(e)
            if "529" in err or "overloaded" in err.lower():
                time.sleep(15 * (intento + 1))
                continue
            return f"⚠️ Error al generar reporte: {err}"

    return "⚠️ No se pudo generar el reporte (API saturada). Intente de nuevo."
