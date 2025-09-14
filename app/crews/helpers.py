import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

# Load environment variables
load_dotenv()

def get_llm():
    """
    Initialize and return an LLM instance.
    
    Returns:
        ChatGroq: Configured Groq LLM instance (for now)
    """
    LLM_TYPE = os.getenv("LLM_TYPE", "GROQ")
    if LLM_TYPE == "GROQ":
        groq_api_key = os.getenv("GROQ_API_KEY")
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set")
        
        return ChatGroq(
            groq_api_key=groq_api_key,
            model_name=groq_model,
            temperature=0.7,
            max_tokens=None,
            timeout=None,
            max_retries=2,
        )