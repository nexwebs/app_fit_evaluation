"""
app/services/email_service.py
Servicio de emails ASYNC corregido
"""
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings


class EmailService:
    """Servicio para envío de emails asíncrono"""
    
    def __init__(self):
        self.smtp_server = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_USER  # Usar SMTP_USER como from_email
    
    async def _enviar_email(
        self,
        destinatario: str,
        subject: str,
        body: str,
        from_email: str = None
    ) -> bool:
        """
        Envía email de forma ASÍNCRONA usando aiosmtplib
        """
        try:
            # Crear mensaje
            mensaje = MIMEMultipart("alternative")
            mensaje["Subject"] = subject
            mensaje["From"] = from_email or self.from_email
            mensaje["To"] = destinatario
            
            # Agregar body HTML
            html_part = MIMEText(body, "html", "utf-8")
            mensaje.attach(html_part)
            
            print(f"📧 Intentando enviar email a {destinatario}...")
            print(f"   SMTP: {self.smtp_server}:{self.smtp_port}")
            print(f"   User: {self.smtp_user}")
            
            # Enviar usando aiosmtplib con STARTTLS
            await aiosmtplib.send(
                mensaje,
                hostname=self.smtp_server,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,  # STARTTLS para Gmail
            )
            
            print(f"✅ Email enviado exitosamente a {destinatario}")
            return True
            
        except Exception as e:
            print(f"❌ Error enviando email a {destinatario}:")
            print(f"   Tipo: {type(e).__name__}")
            print(f"   Mensaje: {str(e)}")
            import traceback
            traceback.print_exc()
            return False