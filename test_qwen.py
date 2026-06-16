import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('OPENROUTER_API_KEY')
if api_key:
    api_key = api_key.strip().replace('"', '')

headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
body = {'model': 'qwen/qwen3.5-flash-02-23', 'messages': [{'role': 'user', 'content': 'Test'}]}

with httpx.Client() as client:
    r = client.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=body)
    try:
        data = r.json()
        print('Status Code:', r.status_code)
        if r.status_code == 200:
            print('Has usage:', 'usage' in data)
            if 'usage' in data:
                print('Usage value:', data['usage'])
        else:
            print('Error:', data)
    except Exception as e:
        print('Exception:', e)
        print('Response text:', r.text)
