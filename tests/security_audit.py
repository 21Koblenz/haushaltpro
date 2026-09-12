from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
main = (root / "app/main.py").read_text()
db = (root / "app/db.py").read_text()
dockerfile = (root / "Dockerfile").read_text()
compose = (root / "docker-compose.yml").read_text()
requirements = (root / "requirements.txt").read_text()

checks = {
    "sqlcipher4_runtime_check": 'startswith("4.")' in db and "PRAGMA cipher_version" in db,
    "sqlcipher_kdf_256k": "PRAGMA kdf_iter = 256000" in db,
    "sqlcipher_sha512": "PBKDF2_HMAC_SHA512" in db and "HMAC_SHA512" in db,
    "cipher_integrity_check": "PRAGMA cipher_integrity_check" in db,
    "prepared_app_queries": not re.search(r'f["\'](?:SELECT|INSERT|UPDATE|DELETE)', main, re.I),
    "pragma_key_escaped": "value.replace(\"'\", \"''\")" in db,
    "argon2id": "PasswordHasher" in main,
    "login_rate_limit": "LOGIN_MAX_FAILURES" in main and "HTTPException(429" in main,
    "csrf": "X-CSRF-Token" in main and "compare_digest" in main,
    "http_only_cookie": "httponly=True" in main and 'samesite="strict"' in main,
    "autolock_idle": "idle_expired" in main,
    "security_headers": "Content-Security-Policy" in main and "X-Frame-Options" in main,
    "backup_aesgcm": "AESGCM" in main and "HPB4" in main,
    "backup_password_not_query": "def backup(x: BackupIn" in main,
    "restore_verification": "verify_database_file" in main,
    "non_root": ("USER appuser" in dockerfile or "USER 10001:10001" in dockerfile),
    "capabilities_dropped": "cap_drop:" in compose and "- ALL" in compose,
    "read_only_root": "read_only: true" in compose,
    "no_new_privileges": "no-new-privileges:true" in compose,
    "no_access_log": "--no-access-log" in dockerfile,
    "maintained_sqlcipher_binding": "sqlcipher3==0.6.2" in requirements and "sqlcipher3-binary" not in requirements and "pysqlcipher3" not in requirements,
    "per_thread_read_connections": "_thread_local" in db and "current_key()" in db and "active_path()" in db,
    "isolated_write_transactions": "BEGIN IMMEDIATE" in db and "c.close()" in db,
    "decimal_money_inputs": "def money_decimal" in main and "amount: Decimal" in main and "opening_balance: Decimal" in main,
    "attachment_magic_bytes": "detect_attachment_type" in main and "data.startswith(b\"%PDF-\")" in main,
    "attachment_storage_limits": "MAX_ATTACHMENT_TOTAL_BYTES" in main and "MAX_ATTACHMENTS_PER_TX" in main,
    "audit_hash_chain": "def audit_append" in main and "def audit_verify" in main and "prev_hash" in db,
    "backup_rotation_verify": "rotate_internal_backups" in main and "verify_latest_internal_backup" in main,
    "docker_resource_limits": "mem_limit: 512m" in compose and "cpus: 1.0" in compose,
    "docker_loopback_default": "HAUSHALTPRO_BIND_IP:-127.0.0.1" in compose,
    "pinned_base_image": "python:3.12-slim-bookworm@sha256:" in dockerfile,
    "updated_fastapi": "fastapi==0.141.1" in requirements and "starlette==1.6.0" in requirements,
    "updated_uvicorn": "uvicorn[standard]==0.52.4" in requirements,
    "updated_multipart": "python-multipart==0.0.32" in requirements,
    "updated_cryptography": "cryptography==50.0.1" in requirements,
    "public_fail_closed": "Public-Modus erfordert SECURE_COOKIES=true" in main and "ALLOWED_HOSTS" in main,
    "trusted_host_public": "TrustedHostMiddleware" in main,
    "https_enforcement": "HTTPS erforderlich" in main and "Strict-Transport-Security" in main,
    "public_registration_off": "ALLOW_SELF_REGISTRATION" in main and "Selbstregistrierung ist deaktiviert" in main,
    "public_setup_token": "PUBLIC_SETUP_TOKEN" in main and "Ungültiger Setup-Token" in main,
    "request_body_limit": "RequestBodyLimitMiddleware" in main and "MAX_REQUEST_BYTES" in main,
    "public_rate_limits": 'rate_limit(request,"setup"' in main and 'rate_limit(request,"login"' in main,
    "server_header_disabled": "--no-server-header" in dockerfile,
    "uvicorn_limits": "--limit-concurrency" in dockerfile and "--limit-max-requests" in dockerfile,
    "security_scan_script": (root / "scripts/security-scan.sh").exists(),
}

failed = []
for name, ok in checks.items():
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not ok:
        failed.append(name)
if failed:
    print("FAILED:", ", ".join(failed), file=sys.stderr)
    raise SystemExit(1)
print(f"ALL {len(checks)} STATIC SECURITY CHECKS PASSED")
