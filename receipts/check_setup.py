"""Checks that the API key works and shows which models the key can use.

Run:  python -m receipts.check_setup
"""

import os

from dotenv import load_dotenv


def main() -> None:
    from google import genai

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is missing from the .env file.")
    client = genai.Client(api_key=api_key)

    print("Models this key can see:")
    for model in client.models.list():
        print("  ", model.name)

    model = os.environ.get("GEMINI_MODEL")
    if not model:
        raise SystemExit("\nNow pick a Flash model from the list and set GEMINI_MODEL in .env.")
    response = client.models.generate_content(model=model, contents="Reply with the single word: ok")
    print(f"\nTest call to {model} worked. Reply: {response.text!r}")


if __name__ == "__main__":
    main()
