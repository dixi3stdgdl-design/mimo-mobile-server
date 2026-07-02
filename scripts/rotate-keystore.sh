#!/bin/bash
# Rotate APK signing keystore
# Usage: ./rotate-keystore.sh <new-password>

set -e

NEW_PASS="${1:-$(openssl rand -hex 16)}"
ALIAS="mimomobile"
KEYSTORE="/tmp/rotated-keystore.jks"
EXPIRY_DAYS=10000

echo "=== Keystore Rotation ==="
echo "Generating new keystore..."

keytool -genkeypair \
  -keystore "$KEYSTORE" \
  -alias "$ALIAS" \
  -keyalg RSA \
  -keysize 2048 \
  -validity "$EXPIRY_DAYS" \
  -storepass "$NEW_PASS" \
  -keypass "$NEW_PASS" \
  -dname "CN=Octavio Garcia, OU=Development, O=dixi3stdgdl-design, L=Guadalajara, ST=Jalisco, C=MX"

echo "Encoding to base64..."
BASE64=$(base64 -w 0 "$KEYSTORE")

echo "Updating GitHub secret KEYSTORE_BASE64..."
echo "$BASE64" | gh secret set KEYSTORE_BASE64 --repo dixi3stdgdl-design/mimomobile

echo "Updating GitHub secret KEYSTORE_PASSWORD..."
gh secret set KEYSTORE_PASSWORD --body "$NEW_PASS" --repo dixi3stdgdl-design/mimomobile

echo "Updating GitHub secret KEY_PASSWORD..."
gh secret set KEY_PASSWORD --body "$NEW_PASS" --repo dixi3stdgdl-design/mimomobile

echo "Updating GitHub secret KEY_ALIAS..."
gh secret set KEY_ALIAS --body "$ALIAS" --repo dixi3stdgdl-design/mimomobile

rm -f "$KEYSTORE"

echo ""
echo "=== Rotation Complete ==="
echo "New password: $NEW_PASS"
echo "Save this password securely!"
echo "Date: $(date -Iseconds)"
