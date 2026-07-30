# Zero → Hero: Every Command, Every Problem, Every "Why"

This is the deep-dive. It explains **what this project is really for**, **every terminal command
you ran (what/why/how)**, **every problem we hit and how we solved it** (this part is interview
gold), and **why each task matters for security**. Read it slowly, once. You'll come out
understanding the whole thing.

---

# 0. What is this project *really* for?

**The real-world situation it simulates:** A payments company (Dodo Payments) handles credit-card
data. A developer shipped a service (`ledger-api`) fast and **left it insecure** — running as the
most powerful user (root), with passwords written in plain text, and no walls between services.
Companies that touch card data must follow **PCI DSS** (a legal-ish security standard), and an
**audit** is coming. If this went to production as-is, one bug could leak thousands of card
numbers — that's fines, lawsuits, and lost trust.

**Why "DevSecOps" exists:** In the old way, developers built software and a separate security team
checked it *at the end* — too late and too slow. **DevSecOps means security is built into every
step automatically**, so problems are caught in seconds, not months. This is now how serious
companies ship software. Real breaches that DevSecOps controls would have stopped: **SolarWinds**
(poisoned build pipeline), **Codecov** (leaked secrets via CI), **Capital One** (SSRF + over-broad
permissions). Every task in this project maps to a control that stops one of those.

**The mental model — 4 layers of defense, then attack to prove it:**
1. **Task 1** – lock down the *container* (the app itself).
2. **Task 2** – lock down the *pipeline* (how the app is built and shipped).
3. **Task 3** – lock down the *network* (who can talk to whom).
4. **Task 4** – *attack* it to prove the locks hold.

---

# 1. Foundation concepts (so the commands make sense)

- **Container** – a lightweight box holding an app + everything it needs, so it runs the same
  everywhere. **Image** = the frozen template; **container** = a running copy of it.
- **Docker** – the tool that builds images and runs containers.
- **Colima** – on a Mac, Docker actually needs a tiny Linux virtual machine to run in. Colima *is*
  that VM. If Colima is off, Docker is off.
- **Kubernetes (k8s)** – the "conductor" that runs and connects *many* containers across machines.
  Real companies run apps on Kubernetes.
  - **Pod** = the smallest unit (one or more containers together).
  - **Node** = a machine in the cluster. **Namespace** = a folder to group things (ours is
    `payments`). **Cluster** = the whole thing.
- **kind** – "Kubernetes IN Docker": runs a practice Kubernetes cluster on your laptop, free.
- **kubectl** – the remote control you type to tell Kubernetes what to do.
- **Helm** – an "app store installer" for Kubernetes (we used it to install Kyverno).

Think of it as nesting dolls: **Colima (VM) → Docker → kind (cluster of node-containers) →
pods → your app**.

---

# 2. Every command, phase by phase (what / why / how)

### Phase 1 — Build the cluster

| Command | What it does & why |
|---|---|
| `colima start --cpu 4 --memory 8` | Starts the Linux VM that Docker runs inside, with 4 CPUs / 8 GB RAM. **Why those numbers:** Kubernetes + Kyverno + Istio together are heavy; less RAM and things crash. |
| `kind delete cluster --name dodo` | Deletes any old/broken cluster so we start clean. **Why:** a half-broken cluster gives confusing errors; a clean build is predictable. |
| `kind create cluster --config kind-config.yaml` | Creates a fresh 3-node practice cluster using our config file. **Why a config file:** it maps ports 80/443 and labels a node for ingress, so the setup is repeatable. |
| `docker build -t ghcr.io/abdulnafih2002/ledger-api:0.1.0 task1-harden/app` | Packages our *hardened* app into an image. `-t` = tag/name it. **Why:** Kubernetes runs images, not raw code. |
| `kind load docker-image ...` | Copies that image *into* the cluster. **Why:** the cluster can't see images on your laptop by default; this hands it over without needing an internet registry. |
| `kubectl get nodes` | Lists the cluster machines. **Why:** a checkpoint — all `Ready` means the cluster is healthy before we build on it. |

### Phase 2 — Install the admission guard

| Command | What it does & why |
|---|---|
| `helm repo add kyverno https://kyverno.github.io/kyverno` + `helm repo update` | Tells Helm where to download Kyverno from, and refreshes the list. |
| `helm install kyverno kyverno/kyverno -n kyverno --create-namespace --wait` | Installs **Kyverno**, the policy "bouncer". `--wait` makes the command pause until it's fully ready. **Why Kyverno:** it inspects every new pod and can *reject* insecure ones at the door. |
| `kubectl -n kyverno get pods` | Confirms Kyverno's 4 components are `Running`. |

### Phase 3 — Deploy the hardened app (Task 1)

| Command | What it does & why |
|---|---|
| `kubectl apply -f task1-harden/manifests/00-namespace.yaml` | Creates the `payments` namespace **with strict Pod Security turned on** (labels in the file). |
| `kubectl apply -f task1-harden/policies/kyverno-policies.yaml` | Activates our custom guard rules (no root, no `:latest`, must be hardened, must be signed). |
| `export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt` | Points SOPS at your **private decryption key** (stored outside git). |
| `sops -d ...enc.yaml \| kubectl apply -f -` | **Decrypts** the secret in memory and pipes (`\|`) it straight into Kubernetes. **Why the pipe:** the decrypted plaintext never touches disk or git. |
| `kubectl apply -f task1-harden/manifests/` | Deploys the app, neighbour, service, config, etc. |
| `kubectl apply -f task1-harden/rbac/personas.yaml` | Adds developer/operator/admin roles (least privilege). |
| `kubectl -n payments rollout status deploy/ledger-api` | Waits until the app is fully up. |

**The verification commands (your evidence):**
| Command | Proves |
|---|---|
| `kubectl exec $POD -c ledger-api -- id` | Runs as `uid=10001`, **not root**. |
| `kubectl exec $POD -c ledger-api -- touch /test` → *Read-only file system* | Attacker can't write malware. |
| `kubectl auth can-i get secrets --as=system:serviceaccount:payments:ledger-api` → `no` | The app's identity **can't read secrets** (least privilege). |
| `sed -n '7,9p' ...enc.yaml` → `ENC[AES256_GCM,...]` | The secret is **encrypted** in git. |

### Phase 4 — Prove the guard blocks bad config

| Command | What it does & why |
|---|---|
| `kubectl apply -f _original/deployment.yaml` | Tries to deploy the **original insecure** app (root, no security). It gets a red **"denied / blocked"** — that red error *is* the success: the guard works. |

### Phase 5 — Install the zero-trust network (Task 3)

| Command | What it does & why |
|---|---|
| `istioctl install --set profile=minimal --set components.cni.enabled=true ...` | Installs **Istio** (the service mesh) **with the CNI plugin**. **Why CNI:** see Problem #7 below — without it, our strict Pod Security *blocks* Istio. |
| `kubectl -n payments rollout restart deploy/ledger-api deploy/reporting` | Restarts the apps so each gets an **Envoy sidecar** (the security proxy). That's why pods go from `1/1` to `2/2`. |
| `kubectl apply -f task3-mesh/istio/10-peerauthentication-strict.yaml` | Turns on **mTLS STRICT** — all traffic must be encrypted + identity-verified. |
| `kubectl apply -f task3-mesh/istio/20-authorizationpolicy.yaml` | **Default-deny** + "allow only the `reporting` identity". |
| `kubectl apply -f task3-mesh/networkpolicy/networkpolicies.yaml` | A second, lower-level firewall (defense-in-depth). |

### Phase 6 — Prove zero-trust (Task 3)

| Command | Proves |
|---|---|
| `kubectl exec deploy/reporting -c client -- curl ... /health` → `HTTP 200` | The **allowed** identity gets in. |
| `kubectl delete authorizationpolicy allow-reporting-to-ledger`, wait, curl again → `HTTP 403` | Remove the allow-rule and the **same caller is blocked** — nothing is trusted by default. |
| `kubectl apply -f ...20-authorizationpolicy.yaml` | Restores the allow-rule → back to `200`. |

### Phase 7 — Attack the app (Task 4)

| Command | What it does & why |
|---|---|
| `docker run -d --name ledger-target -p 8080:8080 -e STRIPE... ledger-api:starter` | Runs the **vulnerable** app in a throwaway container (safe, offline). `-p 8080:8080` exposes it locally. |
| `curl -s http://localhost:8080/transactions` | Shows **full card numbers** — a real PCI violation. |
| `cat > /tmp/rce.yaml <<'EOF' ... EOF` | Writes the **attack payload** (a YAML "gadget"). The quoted `'EOF'` keeps it literal. |
| `curl -X POST .../import --data-binary @/tmp/rce.yaml` then `docker exec ledger-target cat /tmp/pwned.txt` → `uid=0(root)` | **Remote Code Execution as root** — the payload ran a command inside the server. |
| `docker run ... ghcr.io/abdulnafih2002/ledger-api:0.1.0` (port 8090) + same attacks | The **hardened** version: cards masked, YAML attack rejected. Proof the fixes work. |
| `docker rm -f ledger-target ledger-hardened` | Cleanup. |

### Phase 8 — Pipeline evidence (Task 2)

| Command / URL | Proves |
|---|---|
| Actions run `.../runs/30436744028` | The pipeline's 4 security jobs pass **green**. |
| Actions run `.../runs/30435629208` | An earlier run where gates **failed and the build was skipped** — gates really block. |
| `cosign verify ghcr.io/abdulnafih2002/ledger-api:0.1.0 ...` | The image is **cryptographically signed** by the pipeline (not tampered). |

---

# 3. The problems we hit & how we solved them  ⭐ (interview gold)

Interviewers love "tell me about a problem you debugged." Here are the real ones from this build.
For each: **symptom → cause → fix → lesson.**

**1. Docker/Colima kept stopping (`Cannot connect to the Docker daemon`).**
Cause: on a Mac, Docker runs inside the Colima VM, and the VM stopped (restart / resource pressure).
Fix: `colima start`. Lesson: on macOS, "Docker is down" usually means "the VM is down" — restart it,
wait 30s.

**2. `brew install` installed nothing.**
Symptom: the whole install aborted. Cause: one package name (`assetfinder`) didn't exist, and Brew
aborts the *entire* command if any name is invalid. Fix: install packages **individually** so one bad
name can't kill the rest. Lesson: batch commands fail as a unit — isolate risky items.

**3. `kind create cluster` "succeeded" but the cluster was gone.**
Cause: the background command returned exit-0 but the Docker daemon was actually down, so nothing was
created. Fix: bring Docker up first, verify with `docker info`, then recreate. Lesson: always verify
state (`kubectl get nodes`) — don't trust a single exit code.

**4. `kubectl` said "connection refused / context not set".**
Cause: after the VM restarted, kubectl didn't know how to reach the cluster. Fix:
`kind export kubeconfig --name dodo` / `kubectl config use-context kind-dodo`. Lesson: kubectl needs a
"kubeconfig" pointing at the cluster; a restart can lose it.

**5. SOPS wouldn't encrypt ("no matching creation rules").**
Cause: SOPS decides how to encrypt based on the **file path**, and I first wrote to a temp file that
didn't match the rule in `.sops.yaml`. Fix: write the secret to its final path
(`...enc.yaml`) and encrypt **in place**. Lesson: SOPS rules are path-based.

**6. Kyverno rejected its own signature policy ("mutateDigest must be false for Audit").**
Cause: an image-signature rule in "Audit" mode isn't allowed to also rewrite the image digest. Fix:
add `mutateDigest: false`. Lesson: admission tools have internal consistency rules; read the error —
it literally tells you the fix.

**7. ⭐ Strict Pod Security *blocked* Istio's sidecar.**
Symptom: new pods refused to start — `istio-init ... must not include NET_ADMIN`. Cause: the normal
Istio sidecar needs the `NET_ADMIN` Linux power to set up networking, but our Task-1 **Pod Security
"restricted"** forbids exactly that power. **Two security layers collided.** Fix: install the **Istio
CNI plugin**, which moves that networking setup to the *node* so app pods need no special power and
stay locked-down. Lesson: this is a real, well-known tension — and the *correct* answer isn't "weaken
Pod Security", it's "use Istio CNI". **This is a great story to tell an interviewer.**

**8. NetworkPolicies didn't actually block traffic.**
Cause: `kind`'s default network plugin (`kindnet`) **accepts** NetworkPolicy objects but doesn't
*enforce* them. Fix/decision: documented it honestly — in a real cluster you'd use **Calico/Cilium**,
which do enforce. The Istio layer *is* enforced live. Lesson: **know your tools' limits and be honest
about them** — that reads as senior-level, not a weakness.

**9. CI — Semgrep failed on the SSRF code.**
Cause: Semgrep's rule flagged our `/fetch` function even though we *had* added protections it can't
"see". Fix: mark those lines `# nosemgrep` **with a written justification**. Lesson: security tools
have false positives; the professional move is *review + document*, not disable-everything.

**10. CI — `trivy-action@0.24.0` "unable to find version".**
Cause: I referenced a tag that didn't exist (the real tags are `v`-prefixed, e.g. `v0.28.0`), and then
that version pinned a *broken* helper release. Fix: stop using the fragile pre-made action and
**install the Trivy CLI directly** — reliable and reproducible. Lesson: pin to versions that actually
exist, and prefer simple tools over fragile wrappers when they keep breaking.

**11. CI — build failed: "repository name must be lowercase".**
Cause: container registries require **lowercase** names, but the GitHub owner is `Abdulnafih2002`
(mixed case). Fix: hard-code the lowercase image name. Lesson: registries are strict about lowercase.

**12. CI — the SLSA attestation needed a permission.**
Cause: the provenance step needs `attestations: write`, which wasn't granted. Fix: add it to the
workflow's `permissions`. Lesson: CI runs with least privilege by default — grant exactly what each
step needs.

**13. Zero-trust test showed 200 instead of 403.**
Cause: after changing an Istio policy, it takes a few seconds to **propagate** to the sidecars; we
tested too soon. Fix: **wait / poll** until it flips. Lesson: distributed systems are eventually
consistent — build in a wait, don't assume instant.

**14. The "intruder" pod test was flaky.**
Cause: a brand-new pod's sidecar needs ~20–30s to receive its certificates before mTLS works, and on a
loaded laptop that timing varied. Fix: use a **more reliable demo** — toggle the allow-rule on an
already-warmed pod. Lesson: pick the demonstration that's robust, not just the first one you thought of.

**15. Your shell printed `command not found: #`.**
Cause: your zsh doesn't treat `#` as a comment when typed interactively. Fix: don't paste comment
lines. Lesson: small environment differences matter — comments in copy-paste can bite.

---

# 4. Why each task matters for security (the DevOps angle)

**Task 1 — Harden the workload → limit the blast radius.**
Assume a bug *will* be exploited someday. If the container runs as root with a writable disk and full
powers, one bug = total takeover (and easy escape to the host). Non-root + read-only + dropped
capabilities means even a successful exploit is boxed in. The **admission controller** makes this
non-optional — a developer *can't* accidentally ship a root container. This is **defense-in-depth**
and **least privilege**, the two most important ideas in security.

**Task 2 — Secure the pipeline → stop supply-chain attacks.**
Most teams protect the running app but not *how it's built*. Attackers noticed: **SolarWinds** poisoned
a build pipeline and shipped malware to 18,000 orgs; **Codecov** stole secrets from CI. Scanning
(secrets/code/dependencies) catches problems in seconds; **signing** the image means you can *prove* it
came from your pipeline and wasn't swapped. Security becomes an automated **gate**, not a human
afterthought.

**Task 3 — Zero-trust network → stop lateral movement.**
Old model: hard shell, soft inside — once an attacker is in, they roam freely. That's how one hacked
service becomes a full breach. **Zero trust** flips it: every service must prove its cryptographic
identity for every request, and everything is **denied by default**. So a compromised pod can't just
call the payments service — it isn't on the allow-list. **mTLS** also encrypts card data in transit
(PCI requirement).

**Task 4 — Pen-test → verify, don't assume.**
Controls you never test are hope, not security. Putting on the attacker hat proves the flaws are real
(RCE as root!) and, on retest, proves your defenses actually close them. It also builds the **attacker
mindset** — thinking about how something breaks, which makes you build it stronger.

---

# 5. Deeper glossary

- **PCI DSS** – the security standard for handling payment-card data (mask card numbers, encrypt,
  restrict access, log everything).
- **Least privilege** – give every user/app the *minimum* access it needs, nothing more.
- **Defense-in-depth** – multiple independent layers, so one failure isn't fatal.
- **Blast radius** – how much damage one compromise can cause; hardening shrinks it.
- **Admission controller** – a gate that inspects/rejects resources as they're created (Kyverno, PSS).
- **SAST / SCA** – scanning your *source code* (Semgrep) / your *dependencies* (Trivy) for problems.
- **CVE** – a publicly catalogued known vulnerability, with an ID like `CVE-2024-47081`.
- **Supply chain** – everything that goes into building your software (code, libraries, build steps).
- **Signing / provenance / SBOM** – a tamper-proof stamp / a signed record of how it was built / a
  list of ingredients. Together they prove an image is genuine.
- **Service mesh / sidecar** – a network layer (Istio) that adds a proxy (Envoy) beside each app to
  encrypt and control traffic.
- **mTLS** – mutual TLS: both sides prove identity *and* encrypt.
- **Zero trust** – never trust by default; verify every request by identity.
- **SPIFFE** – a standard cryptographic identity issued to each workload.
- **RCE / SSRF / IDOR** – Remote Code Execution / Server-Side Request Forgery / Insecure Direct Object
  Reference — common attack classes.
- **CVSS** – a 0–10 score for how severe a vulnerability is.
- **GitOps** – git is the single source of truth; a controller (ArgoCD) keeps the cluster matching it.

---

# 6. The whole thing in one paragraph (say this and you sound senior)

> "I took an insecure, PCI-scope payments microservice and applied defense-in-depth. At the workload
> layer I enforced least privilege — non-root, read-only filesystem, dropped capabilities, encrypted
> secrets — and made it non-optional with admission policies. At the delivery layer I built a pipeline
> that gates on secret/code/dependency scans and signs every image, so the supply chain is provable.
> At the network layer I enforced zero-trust with Istio mutual TLS and default-deny identity-based
> authorization. Then I pen-tested it, found a critical RCE, and proved on retest that my controls
> close it. Along the way I resolved real integration issues — like Pod Security blocking the Istio
> sidecar, which I fixed correctly with the Istio CNI plugin rather than weakening security."

You're not zero anymore. Read this once more tonight and you'll be able to defend every line. 🚀
