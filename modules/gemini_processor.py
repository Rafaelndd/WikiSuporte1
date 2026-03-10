# C:\WikiSuporte\modules\gemini_processor.py
import streamlit as st
import tempfile
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from typing import Optional, Dict, Union

def processar_audio_com_gemini(
    audio_bytes, 
    modo_completo: bool = True,
    modelo: str = 'gemini-2.0-flash-exp'
) -> Optional[Union[Dict, str]]:
    """Processa áudio com Gemini e retorna texto estruturado"""
    if not audio_bytes:
        return None
    
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        st.error("Chave GEMINI_API_KEY não configurada!")
        return None

    # Cria arquivo temporário
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        if hasattr(audio_bytes, 'getvalue'):
            tmp.write(audio_bytes.getvalue())
        else:
            tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(modelo)
        
        # Upload do áudio
        audio_file = genai.upload_file(path=tmp_path)
        
        # Prompt baseado no modo
        if modo_completo:
            prompt = """
            Ouça o áudio e retorne APENAS um JSON válido no formato:
            {"titulo": "...", "categoria": "...", "subcategoria": "...", "conteudo": "..."}
            Use tom profissional e corporativo. Baseie-se APENAS no áudio.
            """
        else:
            prompt = "Transcreva o áudio com tom profissional e corporativo."
        
        # Gera conteúdo
        response = model.generate_content([prompt, audio_file])
        
        # Limpeza
        genai.delete_file(audio_file.name)
        os.remove(tmp_path)
        
        res_text = response.text.strip()
        
        if modo_completo:
            # Remove markdown se presente
            res_text = res_text.replace("```json", "").replace("```", "").strip()
            return json.loads(res_text)
        else:
            return res_text
        
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None