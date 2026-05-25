import asyncio
import aiohttp
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

async def test():
    from solvers import MODELS, NVIDIA_URL
    print(f"Current MODELS priority list (Sequential):")
    for i, m in enumerate(MODELS):
        print(f"  Attempt {i+1}: {m}")
    
    nkey = os.getenv('NVIDIA_API_KEY')
    
    # Health check for the top 3 expert models
    candidates = [
        ('NV', NVIDIA_URL, nkey, MODELS[0]),
        ('NV', NVIDIA_URL, nkey, MODELS[1]),
        ('NV', NVIDIA_URL, nkey, MODELS[2]),
    ]
    
    async with aiohttp.ClientSession() as session:
        for prov, url, k, model in candidates:
            headers = {'Authorization': f'Bearer {k}', 'Content-Type': 'application/json'}
            payload = {'model': model, 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 5, 'stream': False}
            try:
                async with session.post(url, headers=headers, json=payload, timeout=20) as r:
                    print(f"[{prov}] {model} Status: {r.status}")
            except Exception as e:
                print(f"[{prov}] {model} ERROR: {e}")

asyncio.run(test())
