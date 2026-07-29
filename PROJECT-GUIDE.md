# Project & Interview Guide (Beginner → Confident)

Everything you need to **understand this project** and **defend it in an interview**.
Read top to bottom once; then use Part 7 (Q&A) the night before.

---

## Part 1 — The Big Picture: what is this project?

**The story (the scenario in the assignment):** You joined **Dodo Payments**, a company that
processes credit-card payments worldwide. A team rushed out a small service called
**`ledger-api`** that touches card data. It was shipped **insecurely** — it ran as the
all-powerful *root* user, had passwords written in plain text, and had no network protection.
Card-payment systems must follow a security standard called **PCI DSS**, and an **audit is
coming**. Your job: **make it secure end-to-end, prove the security works, then act as an
attacker to test it.**

**What is "DevSecOps"?** DevOps = building + shipping software quickly. **DevSecOps = baking
security into every step of that process** instead of bolting it on at the end. This project
is a tour of DevSecOps: secure the app, secure the delivery pipeline, secure the network, then
attack it to verify.

**The 4 missions (tasks):**
1. **Harden the workload** — lock down the app so it can't be abused.
2. **Secure CI/CD** — make the build/ship pipeline automatically catch security problems.
3. **Zero-trust networking** — make services prove *who they are* before they can talk.
4. **Recon & pen-test** — attack the app like a hacker, write a professional report.

**One-line summary you can say out loud:**
> "I took an insecure payments microservice and hardened it across four layers — the container,
> the CI/CD pipeline, and the service-mesh network — then I pen-tested it to prove the controls
> actually stop real attacks."

---

## Part 2 — What was GIVEN vs. what I BUILT

**Given to me (the starter materials):**
- The **assignment PDF** (the 4 tasks + rules).
- A **starter code repo** for `ledger-api` containing:
  - `app.py` — a tiny **Python/Flask** web app with 5 endpoints (`/health`, `/tokenize`,
    `/transactions`, `/import`, `/fetch`).
  - `Dockerfile` — recipe to package the app (built on an **old, end-of-life** Python 3.6).
  - `requirements.txt` — the app's libraries, all **old versions with known security holes**.
  - `deploy/` — Kubernetes files that ran the app **as root with plaintext secrets**.
  - A **neighbour service** called `reporting` (a helper container).

**The catch — the app was broken *on purpose*.** These same flaws are what I *harden* (Tasks
1–3) and *exploit* (Task 4):

| The flaw (given) | What's wrong |
|---|---|
| `/import` runs `yaml.load()` on user input | Lets an attacker run **any command** = Remote Code Execution |
| `/fetch?url=` fetches any URL | **SSRF** — attacker makes the server call internal systems |
| `/transactions` returns full card numbers | **Card data exposure** — breaks PCI DSS |
| `/tokenize` uses plain unsalted SHA-256 | Weak — a token can be reversed back to the card |
| Deploy file has `STRIPE_API_KEY` + `DB_PASSWORD` in plain text | **Secrets leaked** in git |
| Runs as **root**, no limits, no health checks | Container is dangerously over-privileged |

**Built by me:** everything else — hardened container + Kubernetes manifests, encrypted secrets,
admission policies, a full CI/CD pipeline, the Istio zero-trust setup, and the pen-test report.
Organised as one folder per task.

---

## Part 3 — The Tools (what each is, in plain English, + why used)

Think of these in groups.

### Group A — Running the app (the platform)
- **Docker** — packages an app + its dependencies into a **container** (a lightweight box that
  runs the same everywhere). *Why:* to build and run `ledger-api`.
- **Colima** — runs the Docker engine on a Mac (Docker needs a small Linux VM under the hood).
- **Kubernetes (k8s)** — the "operating system for containers"; runs, restarts, and connects
  many containers across machines. *Why:* the app is deployed here, like in a real company.
- **kind** — "**K**ubernetes **in D**ocker" — runs a whole practice Kubernetes cluster on your
  laptop for **free**, no cloud needed.
- **kubectl** — the command you type to talk to Kubernetes (`kubectl get pods` = "show me my apps").
- **Helm** — a "package installer" for Kubernetes (like an app store). *Why:* to install Kyverno.

### Group B — Hardening the workload (Task 1)
- **securityContext** — Kubernetes settings that lock a container down: run as a **non-root**
  user, make the filesystem **read-only**, **drop all Linux capabilities** (special powers),
  and turn on **seccomp** (limits which system calls it can make).
- **ServiceAccount + RBAC** — an **identity** for the app and **rules** for what it's allowed to
  do in the cluster. We gave it the *bare minimum* ("least privilege").
- **SOPS + age** — encrypt secrets so only encrypted text goes into git. **age** makes the
  encryption key; **SOPS** does the encrypting. *Why:* the plaintext Stripe key had to disappear.
- **Kyverno** — a **policy guard** at the cluster door (an "admission controller"). It **rejects**
  any container that tries to run as root, uses a `:latest` image tag, or isn't hardened.
- **Pod Security Standards (PSS) "restricted"** — Kubernetes' built-in strict security profile,
  turned on for the namespace as a second guard.

### Group C — Secure delivery / supply chain (Task 2)
- **GitHub Actions** — automation that runs steps every time you push code (the "**pipeline**").
- **gitleaks** — scans for **secrets** accidentally committed (passwords, keys).
- **Semgrep** — **SAST** = Static Application Security Testing = reads your **code** for bugs.
- **Trivy** — scans your **dependencies and container image** for known vulnerabilities (**CVEs**).
- **Cosign** — **signs** the built image so you can prove it's genuine ("keyless" = no password to
  manage; it uses GitHub's identity). **SLSA provenance / SBOM** = a signed record of *how* and
  *from what* the image was built.
- **GHCR** — GitHub Container Registry — where the finished image is stored.
- **ArgoCD (GitOps)** — keeps the cluster **exactly matching git**; if someone changes something
  by hand, ArgoCD **puts it back** ("self-heal").

### Group D — Zero-trust network (Task 3)
- **Istio (service mesh)** — puts a tiny **proxy ("sidecar")** next to every app; those proxies
  encrypt and control all traffic. *Why:* to enforce identity-based security between services.
- **mTLS STRICT** — **mutual TLS** = both sides prove identity + encrypt. STRICT = plaintext is
  **refused**.
- **PeerAuthentication / AuthorizationPolicy** — Istio rules: "require mTLS" and "**deny everyone
  except the `reporting` service**".
- **SPIFFE identity** — each service gets a cryptographic **ID card** (e.g.
  `spiffe://.../sa/ledger-api`) that rotates automatically (~every 24h). Access is based on this
  **identity, not IP address**.
- **NetworkPolicy** — a simpler firewall at the network layer (defense-in-depth underneath Istio).

### Group E — Attacking (Task 4)
- **subfinder / crt.sh / httpx / testssl** — **passive recon** tools: find a company's public
  websites and check their setup **without attacking** (only reading public info).
- **nuclei / ffuf / sqlmap / curl** — active testing tools for the **authorized** target.
- **CVSS v3.1** — the industry scoring system (0–10) to rate how severe a finding is.

---

## Part 4 — How I approached each task (problem → approach → proof)

### Task 1 — Harden the workload
- **Problem:** app ran as root, plaintext secrets, no limits, no guardrails.
- **Approach:**
  1. Rewrote the **Dockerfile** to run as a non-root user (UID 10001) on a supported Python.
  2. Wrote hardened **Kubernetes manifests**: `securityContext` (non-root, read-only filesystem,
     drop-ALL capabilities, seccomp), CPU/memory **limits**, **health probes**, a dedicated
     **ServiceAccount** with a tiny **RBAC** role, plus Service + ConfigMap + Ingress.
  3. **Encrypted the secret** with SOPS+age — only ciphertext in git.
  4. Installed **Kyverno** + turned on **PSS restricted** so the cluster **refuses** insecure pods.
- **Proof (live):** the app runs as `uid=10001`, can't write files, can't read secrets; and
  applying the *original* insecure deployment gets **blocked** with a policy error.

### Task 2 — Secure CI/CD pipeline
- **Problem:** no automated security in the build/ship process.
- **Approach:** built a **GitHub Actions** pipeline with **gates in order** — gitleaks (secrets)
  → Semgrep (code) → Trivy (dependencies) → build → Trivy (image) → **Cosign sign + SLSA
  provenance** → push to GHCR. **If any gate fails, the build is blocked.**
- **Fail policy (say this in the interview):** hard-block on Critical/High that have a fix;
  vulnerabilities with **no fix yet** are logged + tracked (not silently passed).
- **Proof:** a green pipeline run on GitHub Actions, and `cosign verify` proving the published
  image is genuinely signed by the workflow. (ArgoCD GitOps documented for drift/self-heal.)

### Task 3 — Zero-trust mesh (Istio)
- **Problem:** any pod could talk to the app; traffic wasn't authenticated.
- **Approach:** installed **Istio**, turned on **mTLS STRICT**, wrote a **default-deny** policy
  plus an explicit allow for **only the `reporting` identity** (by SPIFFE ID, not IP). Added a
  **NetworkPolicy** underneath for defense-in-depth.
- **Nice detail to mention:** the strict Pod Security profile (Task 1) initially **blocked**
  Istio's sidecar; the correct fix is the **Istio CNI plugin** — shows I understand how the
  layers interact.
- **Proof (live):** the allowed service gets **200**, an unauthorized identity gets **403**, a
  plaintext (non-encrypted) request is **refused**, and the app has a rotating SPIFFE certificate.

### Task 4 — Recon & pen-test
- **Approach:** ran the vulnerable app locally (authorized), attacked it, and wrote a
  professional report with **CVSS scores, proof-of-concept, impact, and fixes**, ranked by risk.
- **Highlights:** proved **Remote Code Execution as root** via the YAML endpoint; **chained** it
  to steal the live Stripe key + DB password in one request; then **retested against the hardened
  build and every attack failed** — directly proving Tasks 1–3 work.

---

## Part 5 — How to run it again from a cold start (you turned everything off)

When you shut down, the Docker VM stops and the practice cluster is deleted. Rebuild it once
(~10–15 min). Open **Terminal** and paste each block, top to bottom.

```bash
cd ~/Documents/GitHub/DODO-TASK
colima start --cpu 4 --memory 8          # start the Docker engine
```
```bash
# 1) Create the cluster + build/load the app image
kind create cluster --config kind-config.yaml
docker build -t ghcr.io/abdulnafih2002/ledger-api:0.1.0 task1-harden/app
kind load docker-image ghcr.io/abdulnafih2002/ledger-api:0.1.0 --name dodo
```
```bash
# 2) Install the admission guard (Kyverno)
helm repo add kyverno https://kyverno.github.io/kyverno && helm repo update
helm install kyverno kyverno/kyverno -n kyverno --create-namespace --wait
```
```bash
# 3) Task 1 — namespace, policies, secret, app
kubectl apply -f task1-harden/manifests/00-namespace.yaml -f task1-harden/policies/kyverno-policies.yaml
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d task1-harden/secrets/ledger-api-secrets.enc.yaml | kubectl apply -f -
kubectl apply -f task1-harden/manifests/ -f task1-harden/rbac/personas.yaml
```
```bash
# 4) Task 3 — the Istio mesh
istioctl install --set profile=minimal --set components.cni.enabled=true \
  --set values.cni.cniBinDir=/opt/cni/bin --set values.cni.cniConfDir=/etc/cni/net.d -y
kubectl -n payments rollout restart deploy/ledger-api deploy/reporting
kubectl -n payments rollout status deploy/ledger-api
kubectl apply -f task3-mesh/istio/10-peerauthentication-strict.yaml \
              -f task3-mesh/istio/20-authorizationpolicy.yaml \
              -f task3-mesh/networkpolicy/networkpolicies.yaml
```
**Then test everything** using **[RUN-AND-TEST.md](RUN-AND-TEST.md)** (the step-by-step "what you
should see" guide). Task 2 (the pipeline) runs on GitHub, not your laptop — just open the Actions
tab in the browser.

**To shut it all down again:** `kind delete cluster --name dodo` then `colima stop`.

> **The one error you'll hit:** `connection refused`. It means the Docker VM is off — run
> `colima start`, wait 30 seconds, retry.

---

## Part 6 — The single most important sentence per task (memorize these)

- **Task 1:** "I enforced least privilege — non-root, read-only filesystem, dropped capabilities,
  encrypted secrets with SOPS, and an admission controller that *rejects* anything insecure."
- **Task 2:** "Security is a **gate**, not a suggestion — secrets, code, and CVE scans must pass
  before we build, then we **sign** the image so its origin is provable."
- **Task 3:** "**Zero trust** — services authenticate by cryptographic identity with mutual TLS,
  and everything is **denied by default** unless explicitly allowed."
- **Task 4:** "I proved the flaws are real with working exploits, then **retested to prove my own
  defenses close them** — defense and offense reference the same evidence."

---

## Part 7 — Interview Q&A (practice these out loud)

**General**

**Q: Explain this project in 30 seconds.**
A: "A payments microservice was shipped insecurely — root container, plaintext secrets, no network
policy, and in PCI scope. I hardened it end to end: locked the container down with a strict
securityContext and admission policies, moved secrets into encrypted storage, built a CI/CD
pipeline that scans and signs every image, and enforced zero-trust networking with Istio mTLS. Then
I switched to attacker mode, found a critical remote-code-execution bug, and proved my hardening
closes it on retest."

**Q: What is DevSecOps and where is it in this project?**
A: "Shifting security *left* — into every stage. Here: workload security (Task 1), pipeline
security (Task 2), network security (Task 3), and verification by pen-testing (Task 4)."

**Q: What is PCI DSS and why does it matter here?**
A: "The security standard for handling card data. It's why card numbers must be masked, secrets
encrypted, traffic encrypted (mTLS), and access restricted to need-to-know."

**Task 1**

**Q: What does `readOnlyRootFilesystem` actually protect against?**
A: "If an attacker gets in, they can't write malware or modify the app — I proved this: even after
a successful exploit, the container couldn't write a file."

**Q: Why non-root?** A: "If the app is compromised, root inside the container is far more dangerous
— it eases container escape and tampering. Running as UID 10001 limits the blast radius."

**Q: How did you get the secret out of git?** A: "SOPS with an age key encrypts only the secret
*values*; the encrypted file goes in git, the private key never does. At deploy time I decrypt and
apply it. I proved no plaintext exists in the repo."

**Q: What's the difference between Kyverno and Pod Security Standards?** A: "Both block insecure
pods. PSS is Kubernetes' built-in profile; Kyverno is a flexible policy engine where I can write
custom rules — like *reject `:latest` tags* or *require image signatures*. I use both as layers."

**Task 2**

**Q: A CVE has no fix yet — what do you do?** A: "I don't silently pass it. I record it with a
justification and an expiry in a tracking file, keep it visible in the scan report, and re-check
when a fix lands. Only *fixable* Critical/High hard-block the build."

**Q: What is keyless signing and why is it better?** A: "Cosign signs the image using the CI's
short-lived GitHub identity instead of a long-lived private key I'd have to store and could leak.
The signature is recorded in a public transparency log; `cosign verify` proves the image came from
my exact workflow."

**Q: What is GitOps / self-heal?** A: "Git is the source of truth. ArgoCD continuously compares the
cluster to git and reverts any manual change — so drift can't linger."

**Task 3**

**Q: Why identity instead of IP for access control?** A: "IPs are reused and spoofable in a
cluster. Istio gives each workload a cryptographic SPIFFE identity tied to its service account, so
policy is based on *who* the caller is, and it rotates automatically."

**Q: You have Istio authz *and* a NetworkPolicy — isn't that redundant?** A: "No — different
layers. NetworkPolicy is L3/L4 in the network plugin and stops traffic that never even reaches the
proxy (a compromised or sidecar-less pod). Istio is L7 identity per request. Each catches what the
other can't."

**Task 4**

**Q: Walk me through your most severe finding.** A: "The `/import` endpoint ran `yaml.load` on
untrusted input. I sent a crafted YAML payload that executed a shell command — I confirmed code
execution as **root**. I then chained it to read the environment and exfiltrate the live Stripe key
and DB password in a single request. CVSS 9.8, Critical."

**Q: How did you keep scope disciplined?** A: "Active testing only against the authorized local
target. Recon of the company domain was **passive only** — public certificate logs and DNS, no
scanning — exactly as the rules required."

**Q: How do your defenses stop that RCE?** A: "Three ways: the code now uses safe YAML parsing;
even if exploited, the container is non-root with a read-only filesystem and dropped capabilities;
and the secret is no longer plaintext in the environment. I retested — the exploit fails."

**Gotcha / honesty questions**

**Q: What *didn't* fully work, and why?** A: "NetworkPolicies are applied and correct, but kind's
default network plugin doesn't *enforce* them — in a real cluster with Calico/Cilium they would. I
documented this honestly rather than pretend. Istio's L7 policy *is* enforced live."

**Q: What would you improve with more time?** A: "Wire ArgoCD to decrypt SOPS secrets at sync,
run a live canary deployment, add Calico so NetworkPolicies enforce locally, and expand the recon
into a scored attack-surface inventory."

---

## Part 8 — Glossary flashcards (quick recall)

- **Container / image** — a packaged app; the image is the template, the container is the running copy.
- **Kubernetes / pod / namespace** — the container platform; a pod is one running unit; a namespace is a folder to group them.
- **Root vs non-root** — root = full power (dangerous); non-root = limited (safe).
- **Secret** — a password/key; must be encrypted, never in plain git.
- **Admission controller (Kyverno)** — the bouncer that rejects insecure pods at the door.
- **SAST (Semgrep)** — scans your code. **CVE scan (Trivy)** — scans your dependencies/image.
- **Signing (Cosign)** — a tamper-proof stamp proving the image is genuine.
- **mTLS** — both sides prove identity + encrypt traffic.
- **Zero trust** — never trust by default; verify every request by identity.
- **CVSS** — 0–10 severity score for a vulnerability.
- **RCE / SSRF** — Remote Code Execution (run any command) / Server-Side Request Forgery (make the server fetch things it shouldn't).

You've got this. Read Part 7 out loud twice and you'll be ready. 🚀
