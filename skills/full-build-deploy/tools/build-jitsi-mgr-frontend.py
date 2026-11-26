#!/usr/bin/env python3
"""
Build script for jitsi-mgr frontend (React)
Compiles the React application and outputs to deploy/artifacts/
"""

import os
import sys
import subprocess
import shutil
import hashlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEPLOY_ROOT = SCRIPT_DIR.parent
JITSI_MGR_ROOT = DEPLOY_ROOT.parent / "jitsi-mgr"
JITSI_MGR_FRONTEND = JITSI_MGR_ROOT / "jitsi-mgr-frontend"
ARTIFACTS_DIR = DEPLOY_ROOT / "artifacts"

def calculate_sha256(file_path):
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def check_prerequisites():
    """Check if Node.js and npm are available."""
    print("[*] Checking prerequisites...")

    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] Node.js not found or failed")
            return False
        print(f"[OK] Node.js: {result.stdout.strip()}")
    except FileNotFoundError:
        print("[ERROR] Node.js not found in PATH")
        return False

    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] npm not found or failed")
            return False
        print(f"[OK] npm: {result.stdout.strip()}")
    except FileNotFoundError:
        print("[ERROR] npm not found in PATH")
        return False

    return True

def install_dependencies():
    """Install npm dependencies if needed."""
    print("\n[*] Checking npm dependencies...")

    node_modules = JITSI_MGR_FRONTEND / "node_modules"
    if node_modules.exists():
        print("[OK] node_modules exists, skipping npm install")
        return True

    print("[*] Running npm install...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=JITSI_MGR_FRONTEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.returncode != 0:
        print("[ERROR] npm install failed")
        print(result.stdout)
        return False

    print("[OK] npm install successful")
    return True

def clean_build():
    """Clean previous build artifacts."""
    print("\n[*] Cleaning previous build...")
    build_dir = JITSI_MGR_FRONTEND / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print(f"[OK] Removed {build_dir}")
    else:
        print("[OK] No previous build artifacts")

def build_frontend():
    """Build the React frontend using npm."""
    print("\n[*] Building jitsi-mgr frontend...")

    if not JITSI_MGR_FRONTEND.exists():
        print(f"[ERROR] jitsi-mgr-frontend not found at {JITSI_MGR_FRONTEND}")
        return False

    # Update API base URL for production
    env_file = JITSI_MGR_FRONTEND / ".env.production"
    with open(env_file, "w") as f:
        f.write("REACT_APP_API_BASE_URL=/api/mgr/v1\n")
    print(f"[OK] Created {env_file}")

    # Run npm build
    cmd = ["npm", "run", "build"]
    print(f"Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=JITSI_MGR_FRONTEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Print last 50 lines of output
    output_lines = result.stdout.splitlines()
    print("\n--- Build Output (last 50 lines) ---")
    for line in output_lines[-50:]:
        print(line)
    print("--- End Build Output ---\n")

    if result.returncode != 0:
        print("[ERROR] npm build failed")
        return False

    print("[OK] npm build successful")
    return True

def copy_artifacts():
    """Copy built files to deploy/artifacts/jitsi-mgr-ui/"""
    print("\n[*] Copying artifacts...")

    # Source build directory
    build_dir = JITSI_MGR_FRONTEND / "build"
    if not build_dir.exists():
        print(f"[ERROR] Build directory not found: {build_dir}")
        return False

    # Destination directory
    dest_dir = ARTIFACTS_DIR / "jitsi-mgr-ui"

    # Remove existing destination
    if dest_dir.exists():
        shutil.rmtree(dest_dir)

    # Copy build to artifacts
    shutil.copytree(build_dir, dest_dir)
    print(f"[OK] Copied: {build_dir} -> {dest_dir}")

    # Calculate SHA256 of all files
    sha256_file = ARTIFACTS_DIR / "jitsi-mgr-ui.sha256"
    with open(sha256_file, "w") as f:
        for file_path in sorted(dest_dir.rglob("*")):
            if file_path.is_file():
                rel_path = file_path.relative_to(dest_dir)
                sha256 = calculate_sha256(file_path)
                f.write(f"{sha256}  {rel_path}\n")

    print(f"[OK] SHA256 manifest saved to: {sha256_file}")

    return True

def main():
    """Main build process."""
    print("=" * 60)
    print("[*] Building jitsi-mgr Frontend (React)")
    print("=" * 60)

    # Check prerequisites
    if not check_prerequisites():
        print("\n[ERROR] Prerequisites check failed")
        return 1

    # Install dependencies
    if not install_dependencies():
        print("\n[ERROR] Dependency installation failed")
        return 1

    # Clean previous build
    clean_build()

    # Build frontend
    if not build_frontend():
        print("\n[ERROR] Build failed")
        return 1

    # Copy artifacts
    if not copy_artifacts():
        print("\n[ERROR] Artifact copy failed")
        return 1

    print("\n" + "=" * 60)
    print("[OK] jitsi-mgr Frontend Build Complete!")
    print("=" * 60)
    print(f"[*] Artifact location: {ARTIFACTS_DIR / 'jitsi-mgr-ui'}")
    print(f"[*] SHA256: {ARTIFACTS_DIR / 'jitsi-mgr-ui.sha256'}")
    print("\nNext steps:")
    print("1. Update Caddy to serve frontend at /api/mgr/ui/")
    print("2. Deploy: Use standard CloudMeet deployment process")

    return 0

if __name__ == "__main__":
    sys.exit(main())
