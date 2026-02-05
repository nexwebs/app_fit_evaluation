"""
app/services/r2_storage.py - PostgreSQL Checkpointer para LangGraph
"""
import boto3
from app.config import settings
from datetime import datetime, timezone
import os


def get_r2_client():
    return boto3.client(
        's3',
        endpoint_url=os.getenv('R2_ENDPOINT_URL'),
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
        region_name='auto'
    )


async def upload_to_r2(
    file_content: bytes,
    prospect_id: str,
    filename: str
) -> str:
    try:
        s3 = get_r2_client()
        
        bucket_name = os.getenv('R2_BUCKET_NAME', 'serverdevsfastapi')
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        
        safe_filename = f"cv_{timestamp}_{prospect_id}.pdf"
        r2_key = f"fit_evaluation/cvs/{prospect_id}/{safe_filename}"
        
        s3.put_object(
            Bucket=bucket_name,
            Key=r2_key,
            Body=file_content,
            ContentType='application/pdf',
            Metadata={
                'original_filename': filename,
                'prospect_id': prospect_id,
                'uploaded_at': datetime.now(timezone.utc).isoformat()
            }
        )
        
        return r2_key
        
    except Exception as e:
        print(f"Error subiendo a R2: {e}")
        raise


async def get_presigned_url(r2_key: str, expiration: int = 3600) -> str:
    try:
        s3 = get_r2_client()
        
        bucket_name = os.getenv('R2_BUCKET_NAME', 'serverdevsfastapi')
        
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': r2_key},
            ExpiresIn=expiration
        )
        
        return url
        
    except Exception as e:
        print(f"Error generando URL presigned: {e}")
        raise