#!/usr/bin/env python3
"""Generate a Fernet encryption key for credential storage.

This script generates a cryptographically secure Fernet key for use with
the credential encryption system. The generated key should be stored as
the FERNET_KEY environment variable in Railway.

Usage:
    python scripts/generate_fernet_key.py

Output:
    Prints the generated key in a format ready to copy to Railway environment
    variables.

Security Notes:
    - Generate a unique key per environment (staging, production)
    - Store only in Railway environment variables, never in code
    - Key rotation requires re-encrypting all stored credentials
    - Keep a secure backup of production keys
"""

from cryptography.fernet import Fernet


def main() -> None:
    """Generate and display a new Fernet encryption key."""
    # Generate a new Fernet key (44 URL-safe base64-encoded bytes)
    key = Fernet.generate_key()

    # Decode to string for display (Fernet keys are already base64)
    key_string = key.decode()

    print("=" * 60)
    print("Generated Fernet Encryption Key")
    print("=" * 60)
    print()
    print("Add this to your Railway environment variables:")
    print()
    print(f"FERNET_KEY={key_string}")
    print()
    print("-" * 60)
    print("Usage Instructions:")
    print("-" * 60)
    print("1. Copy the entire line above (including 'FERNET_KEY=')")
    print("2. Go to Railway Dashboard → Your Project → Variables")
    print("3. Add a new variable with name 'FERNET_KEY'")
    print("4. Paste the key value (after the '=' sign)")
    print()
    print("IMPORTANT:")
    print("  - Never commit this key to version control")
    print("  - Keep a secure backup of production keys")
    print("  - Use different keys for staging and production")
    print("  - Key rotation requires re-encrypting all credentials")
    print("=" * 60)


if __name__ == "__main__":
    main()
