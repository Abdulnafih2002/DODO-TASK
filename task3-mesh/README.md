# Task 3 — Service Mesh & Zero-Trust (Istio)

Identity-based zero-trust between `ledger-api` and its neighbour `reporting`, with a
Kubernetes NetworkPolicy layer underneath for defense-in-depth.

## Install & enrol

> **Design note — PSS `restricted` × Istio (defense-in-depth done right).** The
> default sidecar uses an `istio-init` container that needs `NET_ADMIN`/`NET_RAW` to
> program iptables — which the Task 1 namespace (Pod Security Standards **restricted**)
> correctly **rejects**. The production-grade fix is the **Istio CNI plugin**: it moves
> traffic-redirection setup into a node-level DaemonSet, so application pods need **no**
> elevated capabilities and remain PSS-`restricted` compliant. This is exactly the
> Task 1 ↔ Task 3 interaction a real CDE hits, and CNI is the right answer.

```bash
# istiod + CNI so sidecars need no NET_ADMIN (PSS restricted compliant)
istioctl install --set profile=minimal --set components.cni.enabled=true \
  --set values.cni.cniBinDir=/opt/cni/bin --set values.cni.cniConfDir=/etc/cni/net.d -y
kubectl label namespace payments istio-injection=enabled --overwrite   # (already set in 00-namespace)
kubectl -n payments rollout restart deploy/ledger-api deploy/reporting  # inject sidecars
```

## 1. mTLS STRICT — [`istio/10-peerauthentication-strict.yaml`](istio/10-peerauthentication-strict.yaml)
Namespace-wide `PeerAuthentication: STRICT` — sidecars refuse plaintext.
```bash
kubectl apply -f task3-mesh/istio/10-peerauthentication-strict.yaml
istioctl authn tls-check $(kubectl -n payments get pod -l app=reporting -o name | head -1) ledger-api.payments.svc.cluster.local
# a plaintext (non-mesh) request is refused:
kubectl -n payments run naked --image=curlimages/curl --restart=Never -- sleep 1  # no sidecar
kubectl -n payments exec naked -- curl -s http://ledger-api:8080/health   # -> connection reset (no mTLS)
```

## 2. Zero-trust AuthorizationPolicy — [`istio/20-authorizationpolicy.yaml`](istio/20-authorizationpolicy.yaml)
`default-deny` (empty spec) + an explicit allow keyed on **workload identity** (SPIFFE / service
account `cluster.local/ns/payments/sa/reporting`), never on IP.
```bash
# authorised: reporting SA -> ledger-api = 200
kubectl -n payments exec deploy/reporting -- curl -s -o /dev/null -w '%{http_code}\n' http://ledger-api:8080/health
# unauthorised: any other identity -> 403 RBAC: access denied
kubectl -n payments exec deploy/ledger-api -c ledger-api -- curl ...   # from a non-reporting SA => 403
```

## 3. Certificate issuance, rotation, trust root
- **istiod** runs the mesh CA. Each workload's Envoy requests a certificate over the **SDS**
  API; istiod validates the pod's ServiceAccount token and issues an X.509 **SVID** whose
  SAN is the SPIFFE ID `spiffe://cluster.local/ns/<ns>/sa/<sa>`.
- Certs are **short-lived (~24h)** and **auto-rotated** by Envoy via SDS well before expiry —
  no pod restart, no secrets on disk.
- **Trust root:** istiod's self-signed root CA by default (can be replaced with a plugged-in
  intermediate from an enterprise PKI / cert-manager). All sidecars trust that root, which is
  what makes identity-based mTLS possible.

## 4. NetworkPolicy defense-in-depth — [`networkpolicy/networkpolicies.yaml`](networkpolicy/networkpolicies.yaml)
`default-deny` ingress+egress, then explicit allows (DNS; reporting→ledger:8080; ingress→ledger).

**What each layer catches that the other doesn't:**
| Layer | Enforced at | Catches | Blind to |
|---|---|---|---|
| **NetworkPolicy** | CNI / kernel (L3-L4) | packets that never reach Envoy: sidecar-less/compromised pods, port scans, lateral movement | *who* is calling (no identity) |
| **Istio AuthzPolicy** | Envoy (L7) | spoofed source lacking the right SA cert; per-method/path rules | traffic that bypasses the sidecar |
Together: NetworkPolicy shrinks reachability; Istio authenticates the caller cryptographically.
Neither alone is sufficient — e.g. a pod that disables its sidecar is still boxed in by the CNI.

> **kind caveat (transparency):** kind's default `kindnet` CNI does **not enforce**
> NetworkPolicy — the objects are accepted and correct but not enforced here. On a
> policy-capable CNI (**Calico / Cilium**, standard in a real CDE cluster) these enforce
> as written. The Istio L7 authz above **is** enforced live (200 vs 403). To demo L3/L4
> enforcement locally: `kind create cluster` with `disableDefaultCNI: true` + install Calico.

## Bonus
- **Istio Ingress Gateway + TLS termination** — [`istio/30-gateway-tls.yaml`](istio/30-gateway-tls.yaml).
- **Canary** via `VirtualService`+`DestinationRule` 90/10 — [`istio/40-canary.yaml`](istio/40-canary.yaml).
- **PCI CDE tie-in:** the mesh boundary *is* the cardholder-data-environment boundary. mTLS
  STRICT satisfies "encrypt cardholder data in transit" (PCI Req 4); default-deny authz enforces
  "need-to-know" access (Req 7); SPIFFE identities give per-workload attribution (Req 10). Only
  the `reporting` identity may enter the ledger-api trust zone — everything else is denied by
  default, keeping the CDE small and auditable.
