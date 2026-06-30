#!/bin/bash
# Fetchr — Refresh YouTube cookies
# Run this when the admin panel shows "cookies expired"
# or when downloads start failing with bot detection errors.
#
# Usage: bash refresh-cookies.sh

VPS="ubuntu@152.228.137.122"
COOKIE_FILE="/tmp/youtube_cookies.txt"
ZEN_PROFILE=$(find ~/.config/zen -name "cookies.sqlite" 2>/dev/null | head -1)

if [ -z "$ZEN_PROFILE" ]; then
    echo "❌ Impossible de trouver le profil Zen Browser"
    echo "   Vérifie que Zen est installé et que tu es connecté à YouTube."
    exit 1
fi

echo "🍪 Extraction des cookies YouTube depuis Zen Browser..."

python3 -c "
import sqlite3, shutil, tempfile, os

src = '$ZEN_PROFILE'
tmp = tempfile.mktemp(suffix='.sqlite')
shutil.copy2(src, tmp)

conn = sqlite3.connect(tmp)
cur = conn.cursor()
essential_names = ('SID', 'HSID', 'SSID', 'APISID', 'SAPISID', 'LOGIN_INFO', '__Secure-1PSID', '__Secure-3PSID', '__Secure-1PAPISID', '__Secure-3PAPISID', 'CONSENT', 'SOCS', 'VISITOR_INFO1_LIVE', 'YSC', 'PREF', '__Secure-1PSIDTS', '__Secure-3PSIDTS', '__Secure-1PSIDCC', '__Secure-3PSIDCC', 'SIDCC')
placeholders = ','.join('?' * len(essential_names))
cur.execute(f\"SELECT host, CASE WHEN host LIKE '.%' THEN 'TRUE' ELSE 'FALSE' END, path, CASE WHEN isSecure THEN 'TRUE' ELSE 'FALSE' END, expiry, name, value FROM moz_cookies WHERE (host LIKE '%youtube.com' OR host LIKE '%google.com') AND name IN ({placeholders})\", essential_names)
rows = cur.fetchall()
conn.close()
os.unlink(tmp)

with open('$COOKIE_FILE', 'w') as f:
    f.write('# Netscape HTTP Cookie File\n')
    for row in rows:
        host, subdomain, path, secure, expiry, name, value = row
        if expiry > 9999999999:
            expiry = expiry // 1000
        f.write(f'{host}\t{subdomain}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n')

print(f'   ✅ {len(rows)} cookies extraits')
"

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors de l'extraction des cookies"
    exit 1
fi

echo "📤 Upload vers le VPS..."
scp "$COOKIE_FILE" "$VPS:/home/ubuntu/fetchr/cookies.txt"

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors de l'upload"
    exit 1
fi

echo "🔄 Redémarrage du backend..."
ssh "$VPS" "docker restart fetchr-backend-1"

sleep 3

echo "🧪 Test..."
RESULT=$(curl -s -X POST https://fetchr.fr/api/prepare \
    -H "Content-Type: application/json" \
    -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}')

if echo "$RESULT" | grep -q "session_id"; then
    echo "✅ Cookies renouvelés avec succès ! Le service fonctionne."
else
    echo "❌ Le test a échoué. Réponse: $RESULT"
    echo "   Vérifie que tu es bien connecté à YouTube dans Zen Browser."
    exit 1
fi

rm -f "$COOKIE_FILE"
