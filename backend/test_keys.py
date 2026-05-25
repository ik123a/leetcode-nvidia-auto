import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
NVIDIA_KEY = os.getenv("NVIDIA_API_KEY")

async def test_openrouter():
    print("Testing OpenRouter (Model: google/gemini-2.0-flash-001)...")
    if not OPENROUTER_KEY:
        print("ERROR: OpenRouter Key missing in .env")
        return
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    payload = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": "hi"}]}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=20) as r:
                print(f"HTTP Status: {r.status}")
                if r.status == 200:
                    data = await r.json()
                    print("SUCCESS: OpenRouter Success!")
                else:
                    body = await r.text()
                    print(f"FAILURE: OpenRouter Failure: {body[:300]}")
    except Exception as e:
        print(f"EXCEPTION: OpenRouter Exception: {e}")

async def test_nvidia():
    print("\nTesting NVIDIA NIM (Model: meta/llama-3.3-70b)...")
    if not NVIDIA_KEY:
        print("ERROR: NVIDIA Key missing in .env")
        return
    
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {NVIDIA_KEY}", "Content-Type": "application/json"}
    payload = {"model": "meta/llama-3.3-70b", "messages": [{"role": "user", "content": "hi"}]}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=20) as r:
                print(f"HTTP Status: {r.status}")
                if r.status == 200:
                    data = await r.json()
                    print("SUCCESS: NVIDIA NIM Success!")
                else:
                    body = await r.text()
                    print(f"FAILURE: NVIDIA NIM Failure: {body[:300]}")
    except Exception as e:
        print(f"EXCEPTION: NVIDIA NIM Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_openrouter())
    asyncio.run(test_nvidia())
