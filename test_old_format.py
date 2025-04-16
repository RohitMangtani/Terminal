#!/usr/bin/env python
"""
Test OpenAI API Key with older library format
============================================

This script tests if the OpenAI API key is correctly loaded from the .env file
and can successfully make a simple API call using the older format from openai v0.28.0.
"""

import os
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Directly read API key from .env file
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

# Set the API key directly
openai.api_key = api_key

# Try to make a simple API call using the older format (openai v0.28.0)
try:
    print("\nMaking a test API call with openai v0.28.0 format...")
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt="Say 'API test successful'",
        max_tokens=20
    )
    print(f"✅ API call successful: {response.choices[0].text.strip()}")
except Exception as e:
    print(f"❌ API call failed: {str(e)}")

# Try with ChatCompletion as alternative
try:
    print("\nTrying alternative method with ChatCompletion...")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'API test successful'"}
        ],
        max_tokens=20
    )
    print(f"✅ API call successful: {response.choices[0].message['content']}")
except Exception as e:
    print(f"❌ API call failed: {str(e)}") 