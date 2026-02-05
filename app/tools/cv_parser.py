"""
app/tools/cv_parser.py - PostgreSQL Checkpointer para LangGraph
"""
from openai import AsyncOpenAI
from app.config import settings
import json
import PyPDF2
from io import BytesIO
from typing import Dict, Any


async def parse_cv_with_llm(pdf_content: bytes) -> Dict[str, Any]:
    text = extract_text_from_pdf(pdf_content)
    
    if not text or len(text.strip()) < 50:
        return create_empty_cv_data("No se pudo extraer texto del PDF")
    
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    prompt = build_extraction_prompt(text)
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un extractor de datos de CV. Responde SOLO JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=500
        )
        
        parsed_data = clean_and_parse_response(response.choices[0].message.content)
        return normalize_cv_data(parsed_data)
        
    except Exception as e:
        return create_empty_cv_data(str(e))


def extract_text_from_pdf(pdf_content: bytes) -> str:
    try:
        pdf_file = BytesIO(pdf_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        return text.strip()
        
    except Exception:
        return ""


def build_extraction_prompt(text: str) -> str:
    return f"""Extrae la siguiente información del CV en formato JSON:

{{
  "first_name": "string",
  "last_name": "string",
  "email": "string o null",
  "phone": "string o null",
  "years_experience": number,
  "education": "último grado académico",
  "skills": ["lista de habilidades"],
  "languages": ["lista de idiomas"],
  "certifications": ["lista de certificaciones"],
  "summary": "breve resumen profesional (2-3 líneas)",
  "work_history": [{{"company": "empresa", "position": "cargo", "years": number}}]
}}

REGLAS:
- first_name y last_name: separa el nombre completo
- email: formato válido o null
- phone: solo dígitos, sin espacios ni guiones
- years_experience: suma total de años trabajando
- education: último título obtenido
- skills: máximo 10 habilidades principales
- work_history: últimas 3 empresas
- Responde SOLO JSON válido, sin markdown

CV:
{text[:8000]}"""


def clean_and_parse_response(raw_response: str) -> Dict[str, Any]:
    cleaned = raw_response.strip()
    
    if cleaned.startswith("```json"):
        cleaned = cleaned.split("```json")[1].split("```")[0].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1].split("```")[0].strip()
    
    return json.loads(cleaned)


def normalize_cv_data(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data.get("work_history"):
        data["work_history"] = []
    if not data.get("languages"):
        data["languages"] = []
    if not data.get("certifications"):
        data["certifications"] = []
    
    return data


def create_empty_cv_data(error_message: str) -> Dict[str, Any]:
    return {
        "first_name": None,
        "last_name": None,
        "email": None,
        "phone": None,
        "years_experience": 0,
        "education": None,
        "skills": [],
        "work_history": [],
        "languages": [],
        "certifications": [],
        "error": error_message
    }