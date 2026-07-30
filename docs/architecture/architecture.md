# Architecture

**Rendered image:** ![Architecture](architecture.png)
**Editable source:** [`architecture.drawio`](architecture.drawio) (open in draw.io / diagrams.net) ·
Mermaid sources below render on GitHub.

## End-to-end: build → admit → run → mesh

```mermaid
flowchart TB
    subgraph Dev["Developer / GitHub"]
      SRC[app source] --> GHA
    end
    subgraph GHA["GitHub Actions — secure supply chain (Task 2)"]
      direction LR
      GL[gitleaks] --> SG[Semgrep SAST] --> TR[Trivy fs/image] --> BLD[buildx] --> SIGN[cosign keyless + SLSA + SBOM] --> GHCR[(GHCR)]
    end
    GHCR -->|image + signature| ARGO
    subgraph Cluster["kind cluster"]
      ARGO[ArgoCD - GitOps source of truth\nauto-sync + self-heal] -->|apply manifests| ADM
      ADM{Admission\nKyverno + PSS restricted\nTask 1} -->|reject root/:latest/unsigned/weak SC| REJECT[(blocked)]
      ADM -->|admit hardened| NS
      subgraph NS["namespace: payments (PCI CDE) — istio-injection"]
        direction LR
        REP[reporting SA\n+ Envoy sidecar] ==>|mTLS STRICT\nSPIFFE identity| LED[ledger-api\nnon-root, RO-rootfs,\ndrop-ALL, seccomp\n+ Envoy sidecar]
        NP[[NetworkPolicy\ndefault-deny L3/L4]] -.underlies.- REP
        NP -.underlies.- LED
        SEC[(SOPS-encrypted Secret\nenvFrom)] --> LED
      end
    end
    ISTIOD[istiod = mesh CA\nissues/rotates SPIFFE SVIDs] -. certs .-> REP
    ISTIOD -. certs .-> LED
```

## Zero-trust layers (Task 3) — what each catches

```mermaid
flowchart LR
    ATT[caller] --> L1
    subgraph L1["NetworkPolicy (CNI / L3-L4)"]
      d1{reachable?}
    end
    d1 -->|no| X1[(dropped:\nsidecar-less pod,\nport scan, lateral)]
    d1 -->|yes| L2
    subgraph L2["Istio AuthorizationPolicy (Envoy / L7)"]
      d2{SPIFFE identity\n== reporting SA?}
    end
    d2 -->|no| X2[(403 RBAC:\nspoofed / wrong identity)]
    d2 -->|yes, mTLS| OK[ledger-api]
```

## Attack → control mapping (Task 4 retest)

```mermaid
flowchart LR
    F1[F1 YAML RCE] --> C1[safe_load + PyYAML6\nnon-root + RO-rootfs + drop-ALL]
    F2[F2 SSRF] --> C2[host allow-list + private-IP block\n+ egress NetworkPolicy]
    F3[F3 PAN exposure] --> C3[PAN masking]
    F4[F4 secrets in git] --> C4[SOPS+age encrypted Secret]
    F5[F5 vulnerable deps] --> C5[Trivy gate + upgraded deps]
    F6[F6 weak token] --> C6[keyed HMAC]
    F7[F7 misconfig] --> C7[gunicorn + security headers]
```

Render: paste into <https://mermaid.live> or view on GitHub (native Mermaid).
