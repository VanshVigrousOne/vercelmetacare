import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load the API key from your .env file
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print(f"Loaded API Key starting with: {api_key[:5] if api_key else 'None'}...\n")

genai.configure(api_key=api_key)

try:
    print("Available Models for Content Generation:")
    # Loop through and print all models your key has access to
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f" - {m.name}")
    print("\n✅ SUCCESS: Your API key is perfectly valid and connected!")
except Exception as e:
    print(f"\n❌ ERROR: Could not connect to Gemini. \nDetails: {e}")