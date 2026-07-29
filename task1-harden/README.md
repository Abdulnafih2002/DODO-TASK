# Task 1 — Deploy & Harden the Workload

Turns the insecure `ledger-api` (root container, plaintext secrets, no limits/probes,
default ServiceAccount, no admission control) into a production-grade, PCI-minded
deployment on a local `kind` cluster.

## What's here

| Path | Purpose |
|---|---|
| `app/` | Hardened build: multi-stage **non-root** `Dockerfile`, upgraded pinned `requirements.txt`, remediated `app.py` |
| `manifests/` | `00-namespace` (PSS **restricted** + istio-injection) → `10-serviceaccount-rbac` → `20-configmap` → `30-deployment` (hardened) → `40-service` → `50-ingress` → `60-neighbour` |
| `secrets/` | **SOPS+age** encrypted Secret (`*.enc.yaml`) + age recipient pubkey. No plaintext. |
| `policies/` | **Kyverno** ClusterPolicies (reject root / `:latest` / weak securityContext; verify signature) |
| `rbac/` | Bonus: developer / operator / admin persona Roles, least privilege |

## Hardening applied (maps to the brief)

- **securityContext**: `runAsNonRoot`, `runAsUser: 10001`, `readOnlyRootFilesystem: true`
  (+ `emptyDir` `/tmp`), `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`,
  `seccompProfile: RuntimeDefault` — pod and container level.
- **Resources + probes**: CPU/mem requests+limits and liveness/readiness on **every** container.
- **Identity**: dedicated `ledger-api` ServiceAccount, `automountServiceAccountToken: false`,
  least-privilege Role (read only its own ConfigMap — no Secret/pod/write access).
- **Secrets out of git**: SOPS+age. The age private key lives at `~/.config/sops/age/keys.txt`
  (and as a CI secret), never in the repo. Only ciphertext is committed.
- **Admission guardrails**: Kyverno **Enforce** for non-root, no-`:latest`, drop-ALL/RO-rootfs;
  **Audit** for keyless-cosign signature (flip to Enforce with a registry-backed cluster).
- **Bonus**: PSS `restricted` at the namespace; RBAC personas; and a live demo of the policy
  **rejecting** the original insecure Deployment.

## Run it

```bash
# 0. cluster + ingress (from repo root)
kind create cluster --config kind-config.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# 1. build + load the hardened image
docker build -t ghcr.io/abdulnafih2002/ledger-api:0.1.0 task1-harden/app
kind load docker-image ghcr.io/abdulnafih2002/ledger-api:0.1.0 --name dodo

# 2. Kyverno
helm repo add kyverno https://kyverno.github.io/kyverno && helm repo update
helm install kyverno kyverno/kyverno -n kyverno --create-namespace

# 3. namespace + policies + workload
kubectl apply -f task1-harden/manifests/00-namespace.yaml
kubectl apply -f task1-harden/policies/kyverno-policies.yaml
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d task1-harden/secrets/ledger-api-secrets.enc.yaml | kubectl apply -f -
kubectl apply -f task1-harden/manifests/
kubectl apply -f task1-harden/rbac/personas.yaml
```

## Verify (evidence in `screenshots/`)

```bash
# non-root + read-only rootfs
kubectl -n payments get pod -l app=ledger-api -o jsonpath='{.items[0].spec.containers[0].securityContext}'
# least-privilege SA (expect: can-i get secrets = no)
kubectl auth can-i get secrets --as=system:serviceaccount:payments:ledger-api -n payments
# admission guardrail rejects the ORIGINAL insecure deployment
kubectl apply -f _original/deployment.yaml     # -> blocked by Kyverno (root + :latest-ish + no securityContext)
# no plaintext secret anywhere in tracked files
git grep -n "sk_live_9f3a2b7c" -- ':!_original' || echo "clean"
```
