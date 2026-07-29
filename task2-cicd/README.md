# Task 2 — Secure CI/CD Pipeline & Supply Chain

Security is enforced by the **pipeline**, not by good intentions. Every path to
production runs through gating scans, and only a **scanned + signed + attested**
image is published to GHCR. GitOps (ArgoCD) is the single source of truth in-cluster.

Pipeline: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) · GitOps: [`argocd/application.yaml`](argocd/application.yaml)

## Pipeline stages & fail policy

| Stage | Tool | Fail policy |
|---|---|---|
| Secrets scan | **gitleaks** | **Hard-block** on any verified secret. |
| SAST | **Semgrep** (`p/python`, `p/flask`, `p/security-audit`) | **Hard-block** on ERROR severity; medium/low warn. SARIF → Security tab. |
| Dependency / CVE | **Trivy fs** | **Hard-block** CRITICAL/HIGH **with a fix**; unfixed → warn + tracked (see below). |
| Image scan | **Trivy image** | **Hard-block** CRITICAL/HIGH (fixed) in the built image, *before* push. |
| Build | docker buildx → GHCR | Build loaded locally first so it is scanned **before** publishing. |
| Sign + provenance | **Cosign keyless** (OIDC) + `attest-build-provenance` (SLSA) + SBOM | Required — non-optional. |
| Verify (bonus) | `cosign verify` | Proof artifact uploaded; identity pinned to this workflow. |

### "CVE with no fix yet" policy
`ignore-unfixed: true` removes unfixed findings from the **gate** (we can't patch what has no
patch), but they are still reported in the SARIF. If we must temporarily accept a *fixable*
finding, it goes in [`.trivyignore`](../.trivyignore) **with a justification and expiry date**
and a tracking ticket — never a silent pass. Default posture: zero suppressions (the hardened
image upgrades every starter dependency).

### Why keyless signing
No long-lived keys to leak. Cosign gets a short-lived cert from Fulcio bound to the workflow's
OIDC identity; the signature + provenance are logged in the Rekor transparency log. Kyverno's
`verify-image-signature` policy (Task 1) checks exactly this identity — closing the loop from
build to admission.

## GitOps — ArgoCD (drift detection + self-heal)

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -f task2-cicd/argocd/application.yaml
```
`syncPolicy.automated { selfHeal: true, prune: true }` makes Git authoritative. Demo:
```bash
# introduce drift by hand:
kubectl -n payments scale deploy/ledger-api --replicas=1
# ArgoCD detects OutOfSync and self-heals back to the Git-declared 3 replicas.
argocd app get ledger-api ; kubectl -n payments get deploy ledger-api -w
```
Evidence in `screenshots/` (OutOfSync → Synced/Healthy after self-heal).

## Bonus delivered
- **SARIF** upload for Semgrep + Trivy (fs & image) → repo **Security** tab.
- **`cosign verify`** output uploaded as a build artifact (proves this workflow signed it).
- **Canary/blue-green** strategy documented and wired via Istio `VirtualService`+`DestinationRule`
  (Task 3, [`istio/40-canary.yaml`](../task3-mesh/istio/40-canary.yaml)).

## Notes for local reproduction
The workflow targets GitHub-hosted runners + GHCR (no cloud account). To run the gates locally:
```bash
gitleaks detect --source .
semgrep scan --config p/python --config p/flask task1-harden/app
trivy fs --severity CRITICAL,HIGH --ignore-unfixed task1-harden/app
trivy image --severity CRITICAL,HIGH --ignore-unfixed ghcr.io/abdulnafih2002/ledger-api:0.1.0
```
