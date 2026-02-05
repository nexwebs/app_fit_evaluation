"""
app/tools/email_tools.py
Envío de emails con templates mejorados
"""
from app.services.email_service import EmailService
from app.config import settings

email_service = EmailService()


async def send_evaluation_result_email(
    prospect_email: str,
    prospect_name: str,
    total_score: float,
    test_1_score: float,
    test_2_score: float,
    passed: bool
) -> bool:
    try:
        if passed:
            subject, body = build_approval_email(
                prospect_name, total_score, test_1_score, test_2_score
            )
        else:
            subject, body = build_rejection_email(
                prospect_name, total_score, test_1_score, test_2_score
            )
        
        return await email_service._enviar_email(
            destinatario=prospect_email,
            subject=subject,
            body=body
        )
        
    except Exception:
        return False


async def send_hr_notification(
    evaluation_id: str,
    prospect_name: str,
    position_title: str,
    total_score: float,
    test_1_score: float,
    test_2_score: float
) -> bool:
    try:
        subject = f"Nuevo Prospecto Aprobado: {prospect_name} - {position_title}"
        body = build_hr_notification_body(
            evaluation_id, prospect_name, position_title,
            total_score, test_1_score, test_2_score
        )
        
        return await email_service._enviar_email(
            destinatario=settings.EMAIL_VENTAS,
            subject=subject,
            body=body
        )
        
    except Exception:
        return False


def build_approval_email(
    prospect_name: str,
    total_score: float,
    test_1_score: float,
    test_2_score: float
) -> tuple[str, str]:
    subject = f"¡Felicitaciones! Has aprobado - {settings.NOMBRE_EMPRESA}"
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #28a745; color: white; padding: 30px; text-align: center;">
            <h1>APROBADO</h1>
            <p style="font-size: 18px;">Puntaje Total: <strong>{total_score:.2f}/100</strong></p>
        </div>
        
        <div style="background: white; padding: 30px; border: 1px solid #ddd;">
            <h2>Estimado/a {prospect_name},</h2>
            
            <p>¡Felicitaciones! Has aprobado exitosamente nuestra evaluación inicial.</p>
            
            <h3>Tus Resultados</h3>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Test 1 - Competencias Técnicas</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{test_1_score:.2f}/100</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Test 2 - Competencias Transversales</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{test_2_score:.2f}/100</td>
                </tr>
                <tr style="background: #e8f5e9;">
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Puntaje Total</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;"><strong>{total_score:.2f}/100</strong></td>
                </tr>
            </table>
            
            <h3>Próximos Pasos</h3>
            <ol>
                <li><strong>Revisión de CV:</strong> Nuestro equipo de RRHH revisará tu perfil completo (24-48 hrs)</li>
                <li><strong>Entrevista:</strong> Si tu perfil es seleccionado, te contactaremos para agendar una entrevista</li>
                <li><strong>Validación de referencias:</strong> Solicitaremos referencias laborales</li>
                <li><strong>Propuesta formal:</strong> Presentación de oferta laboral</li>
            </ol>
            
            <p style="margin-top: 30px;">
                Cualquier duda, responde este correo o contáctanos:
            </p>
            
            <p>
                Email: {settings.EMAIL_SOPORTE}<br>
                Teléfono: {settings.TELEFONO_SOPORTE}<br>
                Web: {settings.SITIO_WEB}
            </p>
            
            <p style="margin-top: 30px;">
                Saludos cordiales,<br>
                <strong>Equipo de Recursos Humanos</strong><br>
                {settings.NOMBRE_EMPRESA}
            </p>
        </div>
    </body>
    </html>
    """
    
    return subject, body


def build_rejection_email(
    prospect_name: str,
    total_score: float,
    test_1_score: float,
    test_2_score: float
) -> tuple[str, str]:
    subject = f"Resultado de tu Evaluación - {settings.NOMBRE_EMPRESA}"
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #dc3545; color: white; padding: 30px; text-align: center;">
            <h1>NO APROBADO</h1>
            <p style="font-size: 18px;">Puntaje Total: <strong>{total_score:.2f}/100</strong></p>
            <p style="font-size: 14px;">(Puntaje mínimo requerido: 70/100)</p>
        </div>
        
        <div style="background: white; padding: 30px; border: 1px solid #ddd;">
            <h2>Estimado/a {prospect_name},</h2>
            
            <p>Gracias por tu interés en unirte a nuestro equipo y por completar la evaluación.</p>
            
            <h3>Tus Resultados</h3>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Test 1 - Competencias Técnicas</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{test_1_score:.2f}/100</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Test 2 - Competencias Transversales</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{test_2_score:.2f}/100</td>
                </tr>
                <tr style="background: #ffebee;">
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Puntaje Total</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;"><strong>{total_score:.2f}/100</strong></td>
                </tr>
            </table>
            
            <h3>Áreas de Mejora</h3>
            <p>Basándonos en tu evaluación, te recomendamos fortalecer las siguientes áreas:</p>
            <ul>
                <li><strong>Experiencia específica del rol:</strong> Considera buscar oportunidades que te permitan desarrollar habilidades más especializadas</li>
                <li><strong>Preparación para entrevistas:</strong> Practica respuestas estructuradas usando el método STAR (Situación, Tarea, Acción, Resultado)</li>
                <li><strong>Conocimientos técnicos:</strong> Actualiza tus habilidades a través de cursos online o certificaciones</li>
            </ul>
            
            <h3>Te Invitamos a Repostular</h3>
            <p>Puedes volver a postular en <strong>6 meses</strong> una vez que hayas fortalecido las áreas mencionadas.</p>
            
            <p style="margin-top: 30px;">
                ¡Te deseamos mucho éxito en tu desarrollo profesional!
            </p>
            
            <p style="margin-top: 30px;">
                Saludos cordiales,<br>
                <strong>Equipo de Recursos Humanos</strong><br>
                {settings.NOMBRE_EMPRESA}
            </p>
        </div>
    </body>
    </html>
    """
    
    return subject, body


def build_hr_notification_body(
    evaluation_id: str,
    prospect_name: str,
    position_title: str,
    total_score: float,
    test_1_score: float,
    test_2_score: float
) -> str:
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #28a745; color: white; padding: 25px; text-align: center;">
            <h1>PROSPECTO APROBADO</h1>
            <p style="font-size: 18px;">{prospect_name}</p>
            <p style="font-size: 16px;">Posición: {position_title}</p>
        </div>
        
        <div style="background: white; padding: 30px; border: 1px solid #ddd;">
            <h2>Resultados de la Evaluación</h2>
            
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Test 1 - Técnico</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{test_1_score:.2f}/100</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Test 2 - Transversal</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{test_2_score:.2f}/100</td>
                </tr>
                <tr style="background: #e8f5e9;">
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Puntaje Total</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;"><strong>{total_score:.2f}/100</strong></td>
                </tr>
            </table>
            
            <h3>Acción Requerida</h3>
            <p>Ingresa al panel de RRHH para:</p>
            <ol>
                <li>Revisar CV completo</li>
                <li>Ver respuestas detalladas</li>
                <li>Aprobar para entrevista o rechazar</li>
            </ol>
            
            <p style="margin-top: 30px;">
                <strong>ID Evaluación:</strong> {evaluation_id}
            </p>
        </div>
    </body>
    </html>
    """