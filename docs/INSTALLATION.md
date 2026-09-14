# Installation / Deployment - v0.21.6

## Deutsch

### Voraussetzungen

Benötigt werden ein Linux-Host oder eine VM, Docker Engine, Docker Compose Plugin und Git.

```bash
docker --version
docker compose version
git --version
```

Repository installieren:

```bash
git clone https://github.com/21Koblenz/haushaltpro.git
cd haushaltpro
```

### Variante A - nur lokal auf dem Server

```bash
cp .env.example .env
docker compose pull
docker compose up -d
docker compose ps
```

Standard: `HAUSHALTPRO_BIND_IP=127.0.0.1`. Die Anwendung ist damit nur auf dem Docker-Host unter `http://127.0.0.1:8080` erreichbar.

### Variante B - LAN

Wenn Geräte im vertrauenswürdigen Heimnetz zugreifen sollen:

```bash
cp .env.example .env
sed -i 's/HAUSHALTPRO_BIND_IP=127.0.0.1/HAUSHALTPRO_BIND_IP=0.0.0.0/' .env
docker compose pull
docker compose up -d
```

Danach: `http://SERVER-IP:8080`.

**Keine Router-Portweiterleitung auf 8080 einrichten.**

### Variante C - VPN

Für Zugriff von unterwegs wird VPN empfohlen. HaushaltPro bleibt dabei im privaten Netz und muss nicht öffentlich exponiert werden.

Architektur:

```text
Notebook/Smartphone -> WireGuard/VPN -> Heimnetz -> HaushaltPro:8080
```

Wenn der VPN-Server auf demselben Host oder im selben LAN läuft, kann HaushaltPro wie in der LAN-Variante an die private Netzschnittstelle gebunden werden. Die Firewall sollte Port 8080 nur aus LAN/VPN erlauben.

Beispiel-Prüfung vom VPN-Client:

```bash
curl -I http://SERVER-IP:8080/
```

### Variante D - öffentlich / Online

Nur verwenden, wenn öffentlicher Zugriff wirklich erforderlich ist. HaushaltPro selbst bleibt auf `127.0.0.1:8080`; ein Reverse Proxy übernimmt TLS auf Port 443.

```bash
cp .env.public.example .env
openssl rand -hex 32
```

Den erzeugten Wert als `PUBLIC_SETUP_TOKEN` eintragen und `ALLOWED_HOSTS` auf den echten Hostnamen setzen.

Caddy-Beispiel:

```caddyfile
haushalt.example.de {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8080
}
```

Dann:

```bash
docker compose pull
docker compose up -d
```

Wichtig: 8080 nicht per Router/NAT direkt veröffentlichen. Nur 443 zum Reverse Proxy freigeben. `TRUST_PROXY_HEADERS=true` ist nur sicher, wenn der App-Port nicht direkt aus dem Internet erreichbar ist.

Weitere Details stehen in `PUBLIC-DEPLOYMENT.md`.

### Kontrolle

```bash
docker compose ps
docker compose logs --tail=100 haushaltpro
curl http://127.0.0.1:8080/healthz
```

Erwartet:

```json
{"status":"ok"}
```

### Backup vor Updates

Vor Updates ein portables verschlüsseltes Backup herunterladen und außerhalb des Hosts sichern. Das Docker-Volume nicht löschen.

### Update

```bash
git fetch --tags
docker compose pull
docker compose up -d
```


### Entwicklung / lokaler Build aus dem Quellcode

Die normale Compose-Datei zieht das veröffentlichte Docker-Hub-Image. Für Entwicklung oder einen lokalen Build aus dem Git-Checkout:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml build --pull
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

---

## English

### Requirements

Linux host/VM, Docker Engine, Docker Compose plugin and Git.

```bash
git clone https://github.com/21Koblenz/haushaltpro.git
cd haushaltpro
cp .env.example .env
docker compose pull
docker compose up -d
```

The secure default binds to `127.0.0.1:8080`.

### Local / LAN

For trusted LAN access set `HAUSHALTPRO_BIND_IP=0.0.0.0` in `.env`. Do not configure Internet router forwarding to port 8080.

### VPN

VPN is the preferred method for remote private access. Route the client into the private network and allow port 8080 only from LAN/VPN ranges.

### Public Internet

Use `.env.public.example`, a concrete `ALLOWED_HOSTS`, a strong `PUBLIC_SETUP_TOKEN` and an HTTPS reverse proxy. Keep HaushaltPro itself bound to `127.0.0.1:8080`; expose only HTTPS/443 at the proxy.

See `PUBLIC-DEPLOYMENT.md` for Caddy/nginx examples and public-mode security requirements.
