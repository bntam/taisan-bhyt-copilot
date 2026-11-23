"""
Build & Packaging Script for BHYT Clinical Copilot Extension
Creates production zip archives for Chrome Web Store and developer distribution.
"""

import os
import sys
import json
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(BASE_DIR, "extension")
MANIFEST_PATH = os.path.join(EXT_DIR, "manifest.json")

def build_extension_zip():
    if not os.path.exists(MANIFEST_PATH):
        print(f"Error: manifest.json not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    version = manifest.get("version", "1.0.0")
    zip_filename = f"bhyt-copilot-extension-v{version}.zip"
    zip_path = os.path.join(BASE_DIR, zip_filename)

    print(f"Packaging BHYT Clinical Copilot Chrome Extension v{version}...")
    file_count = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(EXT_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for file in files:
                if file.startswith(".") or file.endswith(".tmp") or file.endswith(".crx") or file.endswith(".pem"):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, EXT_DIR)
                zipf.write(file_path, rel_path)
                file_count += 1

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"Successfully created: {zip_path}")
    print(f"Total files: {file_count} | Size: {size_kb:.1f} KB")
    return zip_path

if __name__ == "__main__":
    build_extension_zip()
