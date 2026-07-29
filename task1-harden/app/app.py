"""
ledger-api — hardened / remediated build.

This is the version that runs in the Kubernetes cluster (Tasks 1-3). It is the
same service as the vulnerable starter, but with the application-layer flaws
remediated so that the Task 4 pen-test findings are demonstrably closed on retest:

  * /import   -> yaml.safe_load (no arbitrary object construction => no RCE)
  * /fetch    -> strict scheme + host allow-list + block of link-local/private
                 ranges (SSRF neutralised; cloud metadata unreachable)
  * /transactions -> PANs masked to first6+last4 (PCI DSS Req 3.3)
  * /tokenize -> salted HMAC-SHA256 instead of a bare unsalted digest
  * secrets   -> still read from the environment, but the environment is now
                 populated from a SOPS-encrypted Kubernetes Secret, not plaintext git

The pristine vulnerable copy lives in task4-recon-pentest/pentest/target/ and is
the authorised pen-test target.
"""
import hashlib
import hmac
import ipaddress
import os
import socket
from urllib.parse import urlparse

import requests
import yaml
from flask import Flask, jsonify, request

app = Flask(__name__)

# Secrets are injected from a SOPS-encrypted K8s Secret via envFrom. They are
# never logged or returned. TOKEN_SALT gives tokenisation a keyed HMAC.
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
TOKEN_SALT = os.environ.get("TOKEN_SALT", "").encode()

# SSRF allow-list: /fetch may only reach these hosts. Everything else is refused.
FETCH_ALLOWED_HOSTS = {
    h.strip()
    for h in os.environ.get("FETCH_ALLOWED_HOSTS", "api.dodopayments.example").split(",")
    if h.strip()
}

LEDGER = [
    {"id": "txn_1001", "pan": "4242424242424242", "amount": 4200, "currency": "USD", "status": "captured"},
    {"id": "txn_1002", "pan": "5555555555554444", "amount": 1899, "currency": "EUR", "status": "refunded"},
]


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = "default-src 'none'"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers.pop("Server", None)
    return resp


def _mask_pan(pan: str) -> str:
    """PCI DSS Req 3.3 — show at most first-6 / last-4."""
    if len(pan) < 10:
        return "*" * len(pan)
    return f"{pan[:6]}{'*' * (len(pan) - 10)}{pan[-4:]}"


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/tokenize", methods=["POST"])
def tokenize():
    payload = request.get_json(silent=True) or {}
    pan = str(payload.get("pan", ""))
    if not pan.isdigit() or not (12 <= len(pan) <= 19):
        return jsonify(error="invalid pan"), 400
    # Keyed HMAC — a bare SHA-256 of a 16-digit PAN is brute-forceable.
    digest = hmac.new(TOKEN_SALT or b"dev-only-salt", pan.encode(), hashlib.sha256).hexdigest()
    return jsonify(token="tok_" + digest[:24], last4=pan[-4:])


@app.route("/transactions")
def transactions():
    masked = [{**t, "pan": _mask_pan(t["pan"])} for t in LEDGER]
    return jsonify(transactions=masked)


@app.route("/import", methods=["POST"])
def import_config():
    # safe_load cannot construct arbitrary Python objects -> YAML RCE closed.
    try:
        config = yaml.safe_load(request.data)
    except yaml.YAMLError as exc:
        return jsonify(error="invalid yaml", detail=str(exc)), 400
    return jsonify(loaded=str(config))


def _is_public_host(hostname: str) -> bool:
    """Resolve and reject loopback / link-local / private / reserved targets."""
    try:
        for res in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(res[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
    except socket.gaierror:
        return False
    return True


@app.route("/fetch")
def fetch():
    url = request.args.get("url", "")  # nosemgrep: python.django.security.injection.ssrf.ssrf-injection-requests.ssrf-injection-requests
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return jsonify(error="scheme not allowed"), 400
    if parsed.hostname not in FETCH_ALLOWED_HOSTS:
        return jsonify(error="host not allowed"), 403
    if not _is_public_host(parsed.hostname):
        return jsonify(error="target resolves to a non-public address"), 403
    # SSRF mitigated above (scheme+host allow-list, private-IP block, no redirects);
    # Semgrep's taint rules can't see the runtime allow-list — reviewed & accepted.
    resp = requests.get(url, timeout=5, allow_redirects=False)  # nosemgrep: python.flask.security.injection.ssrf-requests.ssrf-requests
    return jsonify(status_code=resp.status_code, body=resp.text[:2048])


if __name__ == "__main__":
    # Dev-only entrypoint. Production runs under gunicorn (see Dockerfile CMD),
    # not this server. Binding 0.0.0.0 is required inside a container; debug is off.
    # nosemgrep: python.flask.security.audit.app-run-param-config.avoid_app_run_with_bad_host
    app.run(host="0.0.0.0", port=8080, debug=False)  # noqa: S104
