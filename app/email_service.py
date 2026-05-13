"""
Envío de correos con Resend.
"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "GLOSA <noreply@cielogistica.com>")
APP_URL = os.getenv("APP_URL", "https://web-production-699f8.up.railway.app")


async def enviar_bienvenida(email: str, nombre: str, password: str, rol: str) -> bool:
    """Envía correo de bienvenida con credenciales al nuevo usuario."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY no configurada — correo no enviado")
        return False

    rol_label = "Administrador" if rol == "admin" else "Ejecutivo"

    html = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f6fb;margin:0;padding:0">
  <div style="max-width:520px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
    <!-- Header -->
    <div style="background:#1B2B6B;padding:28px 32px;text-align:center">
      <div style="font-size:26px;font-weight:900;color:#fff;letter-spacing:-1px">
        CIE <span style="color:#CC1F2F">GLOSA</span>
      </div>
      <div style="color:rgba(255,255,255,0.7);font-size:13px;margin-top:4px">
        Sistema de Glosa Preventiva Aduanal
      </div>
    </div>
    <!-- Body -->
    <div style="padding:32px">
      <h2 style="color:#1B2B6B;margin:0 0 16px">¡Bienvenido, {nombre}!</h2>
      <p style="color:#444;font-size:14px;line-height:1.6;margin:0 0 24px">
        Se ha creado tu cuenta en el sistema <strong>CIE GLOSA</strong> con el rol de
        <strong style="color:#1B2B6B">{rol_label}</strong>.
        A continuación tus credenciales de acceso:
      </p>

      <!-- Credenciales -->
      <div style="background:#f4f6fb;border-radius:8px;padding:20px;margin-bottom:24px">
        <div style="margin-bottom:12px">
          <div style="font-size:11px;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Correo</div>
          <div style="font-size:15px;color:#1B2B6B;font-weight:600">{email}</div>
        </div>
        <div>
          <div style="font-size:11px;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Contraseña temporal</div>
          <div style="font-size:18px;font-weight:900;color:#CC1F2F;letter-spacing:2px;font-family:monospace">{password}</div>
        </div>
      </div>

      <p style="color:#666;font-size:13px;margin:0 0 24px">
        ⚠️ Por seguridad, te recomendamos cambiar tu contraseña después de tu primer inicio de sesión.
      </p>

      <!-- CTA -->
      <div style="text-align:center">
        <a href="{APP_URL}" style="display:inline-block;background:#1B2B6B;color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:700;font-size:14px">
          Acceder al sistema →
        </a>
      </div>
    </div>
    <!-- Footer -->
    <div style="background:#f4f6fb;padding:18px 32px;text-align:center;border-top:1px solid #e8eaf0">
      <p style="color:#aaa;font-size:11px;margin:0">
        CIE — Sistema de Glosa Preventiva Aduanal<br>
        Este correo es generado automáticamente, no responder.
      </p>
    </div>
  </div>
</body>
</html>
"""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": FROM_EMAIL,
                    "to": [email],
                    "subject": "Tus credenciales de acceso — CIE GLOSA",
                    "html": html,
                },
            )
            if resp.status_code in (200, 201):
                logger.info(f"Correo de bienvenida enviado a {email}")
                return True
            else:
                logger.error(f"Resend error {resp.status_code}: {resp.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"Error enviando correo a {email}: {e}")
        return False
