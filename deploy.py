#!/usr/bin/env python3
"""Update production URLs in sitemap.xml and robots.txt."""
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python deploy.py https://clipik.pro")
    sys.exit(1)

base_url = sys.argv[1].rstrip("/")
root = Path(__file__).resolve().parent

# Update sitemap.xml
sitemap = root / "sitemap.xml"
if sitemap.exists():
    content = sitemap.read_text(encoding="utf-8")
    content = content.replace("http://127.0.0.1:8767/", f"{base_url}/")
    content = content.replace("http://127.0.0.1:8767/packages.html", f"{base_url}/packages.html")
    content = content.replace("http://127.0.0.1:8767/tips.html", f"{base_url}/tips.html")
    sitemap.write_text(content, encoding="utf-8")
    print(f"Updated {sitemap}")

# Update robots.txt
robots = root / "robots.txt"
if robots.exists():
    content = robots.read_text(encoding="utf-8")
    content = content.replace("http://127.0.0.1:8767/sitemap.xml", f"{base_url}/sitemap.xml")
    robots.write_text(content, encoding="utf-8")
    print(f"Updated {robots}")

print(f"\nDeployment URLs updated to: {base_url}")
print("\nNext steps:")
print("1. Upload all files to your hosting")
print("2. Set BASE_URL environment variable on your server")
print("3. Verify site at:", base_url)
