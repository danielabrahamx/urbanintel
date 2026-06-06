"""Quick test of Gemini API connectivity."""
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
print(f"API key loaded: {api_key[:10]}..." if api_key else "ERROR: No API key found")

try:
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    # Test with a simple text prompt
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content("Say 'API works' and nothing else.")
    print(f"Response: {response.text.strip()}")
    print("SUCCESS: Gemini API is working")
except Exception as e:
    print(f"ERROR: {e}")
