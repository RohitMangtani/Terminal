#!/usr/bin/env python
"""
Direct OpenAI API Test
======================

This script directly reads the API key from the .env file and uses it 
to make an API call, bypassing the environment variable loading.
"""

import openai

# Directly read the API key from .env
with open('.env', 'r') as f:
    env_contents = f.read()
    for line in env_contents.splitlines():
        if line.startswith('OPENAI_API_KEY='):
            api_key = line.split('=', 1)[1]
            print(f"API key found in .env: {api_key[:4]}...{api_key[-4:]}")
            break
    else:
        print("API key not found in .env file")
        exit(1)

# Directly set the API key
openai.api_key = api_key

# Try to make a simple API call
try:
    print("\nMaking a test API call...")
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'API test successful'"}
        ],
        max_tokens=20
    )
    print(f"✅ API call successful: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ API call failed: {str(e)}") 