# HaushaltPro öffentlich per HTTPS betreiben

Für private Nutzung ist LAN/VPN der bevorzugte Modus. Eine öffentliche Installation darf nicht direkt über Port 8080 ins Internet veröffentlicht werden.

## 1. Public-Konfiguration

```bash
cp .env.public.example .env
# ALLOWED_HOSTS und PUBLIC_SETUP_TOKEN anpassen
```

Erzeuge den Setup-Token z. B. mit:

```bash
openssl rand -hex 32
```

`HAUSHALTPRO_BIND_IP=127.0.0.1` bleibt gesetzt. Dadurch ist Port 8080 nur lokal auf dem Docker-Host erreichbar.

## 2. Reverse Proxy mit TLS

Der Proxy muss den Original-Host sowie `X-Forwarded-Proto: https` weitergeben. Beispiel Caddy auf dem Host:

```caddyfile
haushalt.example.de {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8080
}
```

Beispiel nginx (TLS-Zertifikat/SSL-Konfiguration erfolgt separat):

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_http_version 1.1;
    client_max_body_size 25m;
}
```

## 3. Public-Schutzmechanismen

Im `public`-Modus startet die App nur mit `SECURE_COOKIES=true` und konkreten `ALLOWED_HOSTS`. Zusätzlich werden HTTPS erzwungen, `__Host-`-Cookies verwendet, HSTS gesendet, Selbstregistrierung standardmäßig deaktiviert, die Ersteinrichtung durch einen separaten Setup-Token geschützt, Login/Setup/Registrierung begrenzt, Request-Größen vor dem Multipart-Parser begrenzt und öffentliche Health-Daten minimiert.

`TRUST_PROXY_HEADERS=true` darf nur verwendet werden, wenn Port 8080 nicht direkt von außen erreichbar ist.

## 4. Security-Scan vor Veröffentlichung

```bash
docker compose build --pull --no-cache
python -m pip install pip-audit
# Trivy nach Herstelleranleitung installieren
./scripts/security-scan.sh haushaltpro:0.21.0
```

Ein grüner Scan ist keine Garantie gegen unbekannte Schwachstellen. Base-Image und Python-Abhängigkeiten sollten regelmäßig aktualisiert und erneut gescannt werden.
