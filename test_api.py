#!/usr/bin/env python
"""
Test OpenAI API Key
==================

This script tests if the OpenAI API key is correctly loaded from the .env file
and can successfully make a simple API call.
"""

import os
import openai
from dotenv import load_dotenv, find_dotenv

def test_api_key():
    """Test if the OpenAI API key is correctly loaded and works."""
    # Load environment variables
    load_dotenv()
    
    # Check the contents of the .env file directly
    env_path = find_dotenv()
    print(f"Using .env file at: {env_path}")
    
    try:
        with open(env_path, 'r') as f:
            env_contents = f.read()
            print("\nContents of .env file:")
            for line in env_contents.splitlines():
                if line.startswith('OPENAI_API_KEY='):
                    key_value = line.split('=', 1)[1]
                    masked_key = key_value[:4] + "..." + key_value[-4:] if len(key_value) > 8 else "***"
                    print(f"OPENAI_API_KEY={masked_key}")
                else:
                    print(line)
    except Exception as e:
        print(f"Error reading .env file: {str(e)}")
    
    # Get API key from environment
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("\n❌ ERROR: OpenAI API key not found in environment")
        print("Please add your OpenAI API key to the .env file with the variable name OPENAI_API_KEY")
        return False
    
    # Print part of the key for verification
    print(f"\nAPI key loaded from environment: {api_key[:4]}...{api_key[-4:]}")
    
    # Set the API key
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
        return True
    except Exception as e:
        print(f"❌ API call failed: {str(e)}")
        return False

if __name__ == "__main__":
    test_api_key() 