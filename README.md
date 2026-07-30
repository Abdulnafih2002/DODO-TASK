# Dodo Payments — Security & DevOps Assessment

Harden a deliberately-insecure PCI-scope payments microservice (`ledger-api`) end-to-end,
prove the controls work, then attack it. Everything runs **locally and free** — a `kind`
cluster + GitHub Actions. No cloud account.

> **The through-line:** the same intentional flaws in `ledger-api` are *hardened* in Tasks 1–3
> and *exploited* in Task 4 — and Task 4's retest proves each control actually closes the
> finding. Defense and offense reference the same evidence.

## Tasks

| Task | Folder | What it delivers |
|---|---|---|
| **1 — Deploy & Harden** | [`task1-harden/`](task1-harden/) | Non-root/RO-rootfs/drop-ALL/seccomp workload + neighbour; probes & limits; least-priv SA + RBAC personas; **SOPS+age** secrets (no plaintext in git); **Kyverno** admission + **PSS restricted**; rejects the insecure deploy. |
| **2 — Secure CI/CD** | [`task2-cicd/`](task2-cicd/) | GitHub Actions with **gitleaks / Semgrep / Trivy** gates, **Cosign keyless** signing + **SLSA** provenance + SBOM, SARIF → Security tab; **ArgoCD** GitOps with drift + self-heal. |
| **3 — Mesh & Zero-Trust** | [`task3-mesh/`](task3-mesh/) | **Istio** mTLS **STRICT**; **default-deny** AuthorizationPolicy keyed on **SPIFFE identity**; cert issuance/rotation write-up; **NetworkPolicy** defense-in-depth; ingress-gateway TLS + canary (bonus). |
| **4 — Recon & Pentest** | [`task4-recon-pentest/`](task4-recon-pentest/) | Passive recon playbook + full **pen-test report** ([`REPORT.md`](task4-recon-pentest/REPORT.md)): 7 findings (1 Critical, 3 High) with CVSS v3.1, PoCs, an RCE→secret chain, and a **retest** proving closure. |

## Architecture
See [`docs/architecture/`](docs/architecture/): **[`architecture.drawio`](docs/architecture/architecture.drawio)**
(editable draw.io), `architecture.png` (rendered image), and `architecture.md` (Mermaid, renders on GitHub).

## Screenshots / evidence
Working proof for each task lives in the per-task `screenshots/` folders, plus the live GitHub
**Actions** pipeline run (see [`task2-cicd/`](task2-cicd/)). Task 4 PoCs are documented in
[`REPORT.md`](task4-recon-pentest/REPORT.md).

## The target
`ledger-api` (Python/Flask) — endpoints `/health`, `/tokenize`, `/transactions`, `/import`,
`/fetch`. As shipped it runs as **root** with **plaintext secrets**, no securityContext, no
limits/probes, the default ServiceAccount, and no network policy. Flaws: **YAML-deserialization
RCE** (`/import`), **SSRF** (`/fetch`), **plaintext PAN exposure** (`/transactions`), **weak
tokenization**, and **outdated CVE-ridden dependencies**.

## Quick start (full local bring-up)
```bash
# 0. tooling (macOS/Homebrew) + cluster
brew install kubectl kind helm istioctl sops age cosign trivy gitleaks semgrep argocd
kind create cluster --config kind-config.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# 1. hardened image
docker build -t ghcr.io/abdulnafih2002/ledger-api:0.1.0 task1-harden/app
kind load docker-image ghcr.io/abdulnafih2002/ledger-api:0.1.0 --name dodo

# 2. Task 1 — Kyverno + namespace + secret + workload
helm install kyverno kyverno/kyverno -n kyverno --create-namespace --wait
kubectl apply -f task1-harden/manifests/00-namespace.yaml -f task1-harden/policies/kyverno-policies.yaml
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d task1-harden/secrets/ledger-api-secrets.enc.yaml | kubectl apply -f -
kubectl apply -f task1-harden/manifests/ -f task1-harden/rbac/personas.yaml

# 3. Task 3 — mesh
istioctl install --set profile=demo -y
kubectl -n payments rollout restart deploy/ledger-api deploy/reporting
kubectl apply -f task3-mesh/istio/ -f task3-mesh/networkpolicy/

# 4. Task 4 — pentest (authorised local target)
cd task4-recon-pentest/pentest/target && docker build -t ledger-api:starter . && \
  docker run -d -p 8080:8080 ledger-api:starter
```

## Evidence
Screenshots for each control live in the per-task `screenshots/` folders — hardened pod
securityContext, Kyverno rejecting the insecure deploy, mTLS STRICT with authorized-200-vs-403,
and the pen-test PoCs + retest. The Task 2 pipeline is independently verifiable from its live
GitHub Actions run.

## Secrets hygiene
Only the **SOPS-encrypted** secret ciphertext is committed. The age private key lives at
`~/.config/sops/age/keys.txt` (and would be a CI/GitHub secret) — never in the repo.
`_original/` keeps the **insecure** starter manifests on purpose (the "before" baseline and the
artifact Kyverno rejects); the `sk_live_…REDACTED` string there is the starter's own placeholder.

## What I'd do with more time
Wire the ArgoCD Vault/KSOPS plugin to decrypt secrets at sync; add a v2 deployment to run the
canary live; push real SARIF to the Security tab via a merged PR; expand recon into a scored
attack-surface inventory; add policy unit tests (Kyverno CLI `test`) and Conftest in CI.
