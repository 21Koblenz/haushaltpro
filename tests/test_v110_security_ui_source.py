from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=(root/'app/main.py').read_text();req=(root/'requirements.txt').read_text();html=(root/'static/index.html').read_text();js=(root/'static/app.js').read_text();css=(root/'static/style.css').read_text();docker=(root/'Dockerfile').read_text();compose=(root/'docker-compose.yml').read_text()
for x in ['fastapi==0.141.1','starlette==1.6.0','uvicorn[standard]==0.52.4','python-multipart==0.0.32','cryptography==50.0.1']: assert x in req,x
assert (('APP_VERSION = "0.11.1"' in main) or ('APP_VERSION = "0.21.0"' in main)) or ('APP_VERSION = "0.21.0"' in main)
assert 'openapi_url=None' in main and 'TrustedHostMiddleware' in main and 'RequestBodyLimitMiddleware' in main
assert '--no-server-header' in docker and '--limit-concurrency' in docker
assert 'HAUSHALTPRO_MODE' in compose and 'ALLOWED_HOSTS' in compose
assert 'id="setupTokenLabel"' in html and 'runtimeStatus.registration_enabled' in js
assert 'user-management-card' in html and '.user-management-card' in css
assert 'repeat(auto-fit,minmax(240px,1fr))' in css and 'overflow:hidden' in css
assert (root/'.env.public.example').exists() and (root/'docs/PUBLIC-DEPLOYMENT.md').exists() and (root/'scripts/security-scan.sh').exists()
print('v0.11.0 dependency/public-security/UI source: PASS')
