#!/usr/bin/env python3
"""
Initialize jitsi-mgr database and generate JWT keys.
Run this before first deployment of jitsi-mgr service.
"""

import os
import sys
import secrets
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEPLOY_ROOT = SCRIPT_DIR.parent
JITSI_MGR_DATA = DEPLOY_ROOT / "data" / "jitsi-mgr"
KEYS_DIR = JITSI_MGR_DATA / "keys"

def create_directories():
    """Create necessary data directories."""
    print("[*] Creating data directories...")
    
    JITSI_MGR_DATA.mkdir(parents=True, exist_ok=True)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"[OK] Created: {JITSI_MGR_DATA}")
    print(f"[OK] Created: {KEYS_DIR}")

def generate_jwt_keys():
    """Generate RSA key pair for JWT signing."""
    print("\n[*] Generating JWT RSA key pair...")
    
    private_key = KEYS_DIR / "jwt-private.pem"
    public_key = KEYS_DIR / "jwt-public.pem"
    
    # Check if keys already exist
    if private_key.exists() and public_key.exists():
        print("[!] JWT keys already exist!")
        response = input("Overwrite existing keys? (yes/no): ").strip().lower()
        if response != "yes":
            print("[OK] Keeping existing keys")
            return True
    
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        print("[ERROR] cryptography library not installed")
        print("Please install: pip install cryptography")
        return False
    
    # Generate private key
    print("Generating private key...")
    private_key_obj = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Write private key to file
    with open(private_key, "wb") as f:
        f.write(private_key_obj.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    print(f"[OK] Generated: {private_key}")
    
    # Generate public key
    print("Generating public key...")
    public_key_obj = private_key_obj.public_key()
    
    # Write public key to file
    with open(public_key, "wb") as f:
        f.write(public_key_obj.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    
    print(f"[OK] Generated: {public_key}")
    
    # Set appropriate permissions (read-only for private key)
    private_key.chmod(0o600)
    public_key.chmod(0o644)
    
    print("[OK] Set appropriate file permissions")
    
    return True

def generate_db_password():
    """Generate a random database password."""
    print("\n[*] Generating database password...")
    
    # Generate 32-character random password using Python secrets
    password = secrets.token_urlsafe(32)
    
    # Save to .env file
    env_file = DEPLOY_ROOT / ".env"
    env_lines = []
    
    # Read existing .env if it exists
    if env_file.exists():
        with open(env_file, "r") as f:
            env_lines = f.readlines()
    
    # Check if JITSI_MGR_DB_PASSWORD already exists
    has_password = any("JITSI_MGR_DB_PASSWORD=" in line for line in env_lines)
    
    if has_password:
        print("[!] JITSI_MGR_DB_PASSWORD already exists in .env")
        response = input("Overwrite existing password? (yes/no): ").strip().lower()
        if response != "yes":
            print("[OK] Keeping existing password")
            return True
        
        # Remove old password line
        env_lines = [line for line in env_lines if "JITSI_MGR_DB_PASSWORD=" not in line]
    
    # Add new password
    env_lines.append(f"\n# jitsi-mgr Database Password (auto-generated)\n")
    env_lines.append(f"JITSI_MGR_DB_PASSWORD={password}\n")
    
    # Write back to .env
    with open(env_file, "w") as f:
        f.writelines(env_lines)
    
    print(f"[OK] Saved JITSI_MGR_DB_PASSWORD to {env_file}")
    print(f"[*] Password: {password}")
    
    return True

def main():
    """Main initialization process."""
    print("=" * 60)
    print("[*] Initializing jitsi-mgr Service")
    print("=" * 60)
    
    # Create directories
    create_directories()
    
    # Generate JWT keys
    if not generate_jwt_keys():
        print("\n[ERROR] JWT key generation failed")
        return 1
    
    # Generate database password
    if not generate_db_password():
        print("\n[ERROR] Database password generation failed")
        return 1
    
    print("\n" + "=" * 60)
    print("[OK] jitsi-mgr Initialization Complete!")
    print("=" * 60)
    print(f"\n[*] Data directory: {JITSI_MGR_DATA}")
    print(f"[*] JWT keys: {KEYS_DIR}")
    print(f"[*] Environment: {DEPLOY_ROOT / '.env'}")
    print("\nNext steps:")
    print("1. Build backend: python build-tools/build-jitsi-mgr-backend.py")
    print("2. Build frontend: python build-tools/build-jitsi-mgr-frontend.py")
    print("3. Deploy: docker-compose up -d jitsi-mgr")
    print("4. Access UI: https://{YOUR_HOST}/api/mgr/ui/")
    print("5. Default admin: username=admin, password=Admin123!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
