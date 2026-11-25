#!/usr/bin/env python3
"""
Build script for jitsi-mgr backend (JAR)
Compiles the Spring Boot application and outputs to deploy/artifacts/
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
JITSI_MGR_APP = JITSI_MGR_ROOT / "jitsi-mgr-app"
ARTIFACTS_DIR = DEPLOY_ROOT / "artifacts"

def calculate_sha256(file_path):
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def check_prerequisites():
    """Check if Maven and Java are available."""
    print("[*] Checking prerequisites...")
    
    try:
        result = subprocess.run(["mvn", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] Maven not found or failed")
            return False
        print(f"[OK] Maven: {result.stdout.splitlines()[0]}")
    except FileNotFoundError:
        print("[ERROR] Maven not found in PATH")
        return False
    
    try:
        result = subprocess.run(["java", "-version"], capture_output=True, text=True, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            print("[ERROR] Java not found or failed")
            return False
        print(f"[OK] Java: {result.stdout.splitlines()[0]}")
    except FileNotFoundError:
        print("[ERROR] Java not found in PATH")
        return False
    
    return True

def clean_build():
    """Clean previous build artifacts."""
    print("\n[*] Cleaning previous build...")
    target_dir = JITSI_MGR_APP / "target"
    if target_dir.exists():
        shutil.rmtree(target_dir)
        print(f"[OK] Removed {target_dir}")
    else:
        print("[OK] No previous build artifacts")

def build_jar():
    """Build the Spring Boot JAR using Maven."""
    print("\n[*] Building jitsi-mgr JAR...")
    
    if not JITSI_MGR_APP.exists():
        print(f"[ERROR] jitsi-mgr-app not found at {JITSI_MGR_APP}")
        return False
    
    # Run Maven build
    cmd = ["mvn", "clean", "package", "-DskipTests"]
    print(f"Running: {' '.join(cmd)}")
    
    result = subprocess.run(
        cmd,
        cwd=JITSI_MGR_APP,
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
        print("[ERROR] Maven build failed")
        return False
    
    print("[OK] Maven build successful")
    return True

def copy_artifacts():
    """Copy built JAR to deploy/artifacts/"""
    print("\n[*] Copying artifacts...")
    
    # Find the built JAR
    target_dir = JITSI_MGR_APP / "target"
    jar_files = list(target_dir.glob("jitsi-mgr-*.jar"))
    
    # Exclude the -sources.jar and -javadoc.jar
    jar_files = [f for f in jar_files if not f.name.endswith(("-sources.jar", "-javadoc.jar"))]
    
    if not jar_files:
        print(f"[ERROR] No JAR file found in {target_dir}")
        return False
    
    if len(jar_files) > 1:
        print(f"[!]  Multiple JAR files found, using: {jar_files[0].name}")
    
    source_jar = jar_files[0]
    
    # Create artifacts directory if not exists
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy JAR to artifacts/jitsi-mgr.jar
    dest_jar = ARTIFACTS_DIR / "jitsi-mgr.jar"
    shutil.copy2(source_jar, dest_jar)
    
    # Calculate SHA256
    sha256 = calculate_sha256(dest_jar)
    
    # Save SHA256 to file
    sha256_file = ARTIFACTS_DIR / "jitsi-mgr.jar.sha256"
    with open(sha256_file, "w") as f:
        f.write(f"{sha256}  jitsi-mgr.jar\n")
    
    print(f"[OK] Copied: {source_jar.name} -> {dest_jar}")
    print(f"[OK] SHA256: {sha256}")
    print(f"[OK] SHA256 saved to: {sha256_file}")
    
    return True

def main():
    """Main build process."""
    print("=" * 60)
    print("[*] Building jitsi-mgr Backend (JAR)")
    print("=" * 60)
    
    # Check prerequisites
    if not check_prerequisites():
        print("\n[ERROR] Prerequisites check failed")
        return 1
    
    # Clean previous build
    clean_build()
    
    # Build JAR
    if not build_jar():
        print("\n[ERROR] Build failed")
        return 1
    
    # Copy artifacts
    if not copy_artifacts():
        print("\n[ERROR] Artifact copy failed")
        return 1
    
    print("\n" + "=" * 60)
    print("[OK] jitsi-mgr Backend Build Complete!")
    print("=" * 60)
    print(f"[*] Artifact location: {ARTIFACTS_DIR / 'jitsi-mgr.jar'}")
    print(f"[*] SHA256: {ARTIFACTS_DIR / 'jitsi-mgr.jar.sha256'}")
    print("\nNext steps:")
    print("1. Build frontend: python build-tools/build-jitsi-mgr-frontend.py")
    print("2. Deploy: Use standard CloudMeet deployment process")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
