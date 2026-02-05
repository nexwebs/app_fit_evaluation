r"""
Test simple: Subir CV a R2
Uso: python upload_r2.py "ruta\al\archivo.pdf"
"""
import boto3
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import uuid
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

# Configuración R2
R2_CONFIG = {
    'endpoint_url': os.getenv('R2_ENDPOINT_URL'),
    'aws_access_key_id': os.getenv('R2_ACCESS_KEY_ID'),
    'aws_secret_access_key': os.getenv('R2_SECRET_ACCESS_KEY'),
    'region_name': 'auto'
}

BUCKET_NAME = os.getenv('R2_BUCKET_NAME', 'serverdevsfastapi')
BASE_PREFIX = 'fit_evaluation/cvs'

def list_available_pdfs():
    """Muestra PDFs disponibles en Downloads para facilitar selección"""
    downloads = Path.home() / "Downloads"
    pdfs = list(downloads.glob("*.pdf"))
    
    if pdfs:
        print("📄 PDFs disponibles en Downloads:")
        for i, pdf in enumerate(pdfs[:5], 1):  # Solo primeros 5
            size_mb = pdf.stat().st_size / 1024 / 1024
            print(f"  {i}. {pdf.name} ({size_mb:.2f} MB)")
        print()
    else:
        print("⚠️  No se encontraron PDFs en Downloads\n")

def upload_cv_to_r2(pdf_path: str) -> dict:
    """Sube CV a R2 y retorna metadata"""
    
    # Normalizar ruta
    pdf_path = pdf_path.strip('"').strip("'")
    
    # Verificar existencia
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"❌ Archivo NO encontrado: {pdf_path}")
        print(f"   Ruta absoluta intentada: {pdf_file.absolute()}")
        print()
        list_available_pdfs()
        raise FileNotFoundError(f"Archivo no encontrado: {pdf_path}")
    
    if pdf_file.suffix.lower() != '.pdf':
        raise ValueError("Solo archivos PDF permitidos")
    
    with open(pdf_file, 'rb') as f:
        file_content = f.read()
    
    # Generar ID único
    prospect_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_filename = f"cv_{timestamp}_{prospect_id}.pdf"
    
    # Ruta en R2
    r2_key = f"{BASE_PREFIX}/{prospect_id}/{safe_filename}"
    
    # Conexión a R2
    s3 = boto3.client('s3', **R2_CONFIG)
    
    # Subir archivo
    print(f"📤 Subiendo {pdf_file.name} ({len(file_content)/1024:.2f} KB) a R2...")
    print(f"📍 Ruta destino: {r2_key}")
    
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=r2_key,
        Body=file_content,
        ContentType='application/pdf',
        Metadata={
            'original_filename': pdf_file.name,
            'prospect_id': prospect_id,
            'uploaded_at': datetime.utcnow().isoformat(),
            'file_size': str(len(file_content))
        }
    )
    
    # URL firmada
    presigned_url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': BUCKET_NAME, 'Key': r2_key},
        ExpiresIn=3600
    )
    
    print(f"\n✅ ¡Upload exitoso!")
    print(f"📦 Bucket: {BUCKET_NAME}")
    print(f"🔑 Key: {r2_key}")
    print(f"🆔 Prospect ID: {prospect_id}")
    print(f"🔗 URL descarga (1h): {presigned_url[:60]}...")
    
    return {
        'prospect_id': prospect_id,
        'r2_key': r2_key,
        'presigned_url': presigned_url,
        'file_size': len(file_content)
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python upload_r2.py \"ruta\\al\\archivo.pdf\"")
        print("\nEjemplos:")
        print(r'  Windows: python upload_r2.py "C:\Users\pc\Downloads\CLAUDIO QUISPE-DATA SCIENCE.pdf"')
        print(r'  Windows (nombre simple): python upload_r2.py "C:\Users\pc\Downloads\cv.pdf"')
        print('\n⚠️  IMPORTANTE: Usa ESPACIOS reales en el nombre, no guiones bajos (_)')
        list_available_pdfs()
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    try:
        result = upload_cv_to_r2(pdf_path)
        print(f"\n📊 Resumen:")
        print(f"   - Prospect ID: {result['prospect_id']}")
        print(f"   - Ruta en R2: {result['r2_key']}")
        print(f"   - Tamaño: {result['file_size'] / 1024:.2f} KB")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)