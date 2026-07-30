# Screenshots & Evidence Checklist

The brief asks for **screenshots / recordings** and an **architecture diagram**. This page tells
you exactly what to capture, the command or URL for each, and what the shot should show. Real
screenshots you take on your own machine are the most convincing — this makes them a 10-minute job.

> **How to screenshot on macOS:** `Cmd + Shift + 4` → drag a box around the area (saves to Desktop).
> For a short screen **recording**, `Cmd + Shift + 5` → Record Selected Portion.
> Save each into the matching `task*/screenshots/` folder using the filename in the table.

> **Already captured for you:** every command's raw output is saved as text in the
> `screenshots/` and `evidence/` folders (e.g. `task1-harden/screenshots/task1-verification.txt`).
> Those prove the same thing; the images below just make it visual for the reviewer.

First, make sure the cluster is up (see `RUN-AND-TEST.md` if not):
```bash
cd ~/Documents/GitHub/DODO-TASK && kubectl get nodes
```

---

## Task 1 — Hardening

| # | Capture | Run this / open this | Should show | Save as |
|---|---------|----------------------|-------------|---------|
| 1 | Hardened pods running | `kubectl -n payments get pods` | `ledger-api` + `reporting` pods `2/2 Running` | `task1-harden/screenshots/01-pods-running.png` |
| 2 | Non-root + read-only proof | `POD=$(kubectl -n payments get pod -l app=ledger-api -o jsonpath='{.items[0].metadata.name}'); kubectl -n payments exec $POD -c ledger-api -- id; kubectl -n payments exec $POD -c ledger-api -- touch /x` | `uid=10001(app)` and `Read-only file system` | `task1-harden/screenshots/02-nonroot-readonly.png` |
| 3 | Least-privilege SA | `kubectl auth can-i get secrets --as=system:serviceaccount:payments:ledger-api -n payments` | `no` | `task1-harden/screenshots/03-sa-cannot-read-secrets.png` |
| 4 | **Guardrail blocks bad deploy** | `kubectl apply -f _original/deployment.yaml` | red `denied the request` / `blocked due to the following policies` | `task1-harden/screenshots/04-kyverno-reject.png` |
| 5 | Secret encrypted in git | `sed -n '7,9p' task1-harden/secrets/ledger-api-secrets.enc.yaml` | `ENC[AES256_GCM,...]` (no plaintext) | `task1-harden/screenshots/05-sops-encrypted.png` |

## Task 2 — CI/CD pipeline (evidence lives on GitHub)

| # | Capture | Open this | Should show | Save as |
|---|---------|-----------|-------------|---------|
| 6 | Green pipeline | https://github.com/Abdulnafih2002/DODO-TASK/actions/runs/30436744028 | 4 jobs green ✓ (gitleaks, Semgrep, Trivy, Build+sign) | `task2-cicd/screenshots/06-pipeline-green.png` |
| 7 | A gate blocking (bonus) | https://github.com/Abdulnafih2002/DODO-TASK/actions/runs/30435629208 | SAST/CVE red, Build **skipped** | `task2-cicd/screenshots/07-gate-blocks-build.png` |
| 8 | Signed image proof | `cosign verify ghcr.io/abdulnafih2002/ledger-api:0.1.0 --certificate-identity-regexp "https://github.com/Abdulnafih2002/DODO-TASK/.github/workflows/.*" --certificate-oidc-issuer "https://token.actions.githubusercontent.com"` | `cosign claims were validated` | `task2-cicd/screenshots/08-cosign-verify.png` |
| 9 | Package in GHCR | https://github.com/Abdulnafih2002?tab=packages | `ledger-api` package published | `task2-cicd/screenshots/09-ghcr-package.png` |

## Task 3 — Zero-trust mesh

| # | Capture | Run this | Should show | Save as |
|---|---------|----------|-------------|---------|
| 10 | Sidecars injected | `kubectl -n payments get pods` | pods `2/2` (app + istio-proxy) | `task3-mesh/screenshots/10-sidecars.png` |
| 11 | mTLS is STRICT | `kubectl -n payments get peerauthentication` | `MODE: STRICT` | `task3-mesh/screenshots/11-mtls-strict.png` |
| 12 | **Allowed vs blocked** | `kubectl -n payments exec deploy/reporting -c client -- curl -s -o /dev/null -w 'reporting: HTTP %{http_code}\n' http://ledger-api:8080/health` | `HTTP 200` (allowed) | `task3-mesh/screenshots/12-authz-200-403.png` |
| 13 | SPIFFE identity | `kubectl -n payments get authorizationpolicy` | `default-deny` + `allow-reporting-to-ledger` | `task3-mesh/screenshots/13-authz-policies.png` |

> For the "blocked" half of #12, the exact intruder command is in `RUN-AND-TEST.md` section 2b
> (it returns `HTTP 403`). Capture both 200 and 403 in one shot if you can.

## Task 4 — Pen-test (safe, offline)

| # | Capture | Run this (see `RUN-AND-TEST.md` §3 for full commands) | Should show | Save as |
|---|---------|--------------------------------------------------------|-------------|---------|
| 14 | Card data exposed | `curl -s http://localhost:8080/transactions` | full card numbers `4242...` | `task4-recon-pentest/pentest/14-pan-exposed.png` |
| 15 | **RCE as root** | the `/import` YAML payload, then `docker exec ledger-target cat /tmp/pwned.txt` | `uid=0(root)` | `task4-recon-pentest/pentest/15-rce-root.png` |
| 16 | Attacks closed (retest) | hit the hardened app on port 8090 | masked card + `{"error":"invalid yaml"}` | `task4-recon-pentest/pentest/16-retest-closed.png` |

---

## Architecture diagram (the brief asks for draw.io / Excalidraw / similar)

Three formats are provided in [`docs/architecture/`](docs/architecture/):

| File | What it is | How to open |
|------|-----------|-------------|
| `architecture.drawio` | **Editable draw.io** diagram | Open at <https://app.diagrams.net> (File → Open) or with the **Draw.io Integration** VS Code extension |
| `architecture.png` | Rendered **image** of the diagram | Double-click; drop it straight into your README / slides |
| `architecture.md` | **Mermaid** source (3 diagrams) | Renders automatically on GitHub |

To turn the diagram into a PNG yourself (if you edit the `.drawio`): open it at diagrams.net →
**File → Export as → PNG**.

---

### Fastest path (if you're short on time)
Capture the **five bold rows** (#4 Kyverno reject, #6 green pipeline, #8 cosign verify, #12 authz
200/403, #15 RCE-as-root) plus the architecture PNG. Those five screenshots tell the whole story:
guardrails block bad config, the pipeline gates + signs, zero-trust enforces identity, and the
attack is real — everything else is backed by the committed `.txt` evidence.
