#!/usr/bin/env python3
import sys
from services.claude_client import ClaudeClient


def test_connection():
    print("Testing Claude API connection...")
    print("-" * 50)

    try:
        client = ClaudeClient()
        print(f"Using model: {client.model}")
        print("Attempting to connect to Claude API...")

        if client.test_connection():
            print("\n✓ Connection successful!")
            print("Your API key is valid and working.")
            return 0
        else:
            print("\n✗ Connection failed!")
            print("The API returned an unexpected response.")
            return 1

    except ValueError as e:
        print(f"\n✗ Configuration error: {e}")
        print("\nPlease ensure ANTHROPIC_API_KEY is set in your .env file")
        return 1

    except Exception as e:
        print(f"\n✗ Connection failed: {type(e).__name__}")
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(test_connection())
