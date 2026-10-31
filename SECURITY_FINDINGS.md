# Security Findings

Results of the first run of the security pipeline (`.github/workflows/security.yml`) against ContractMap, run locally on 2026-10-31 before any fixes. Nothing below has been removed or filtered.

| Tool | Version | What was scanned | Findings |
|---|---|---|---|
| Gitleaks | 8.30.1 | Full git history, all local refs (`gitleaks git .`) | **24** (1 real, 23 false positives) |
| Semgrep | 1.183.0 | Tracked files, `--config auto` (494 rules) | **4** in the app code, plus **8** in the new pipeline config itself |
| pip-audit | 2.10.1 | `backend/requirements.txt` | **2** vulnerable packages |
| Manual review | – | Third-party JS loaded by the frontend (not covered by pip-audit) | **1** |
| Trivy | – | Not run: there is no Dockerfile (Render builds a native Python service) | – |

Gitleaks does not grade severity; real secrets are graded Critical here. Semgrep severities are Semgrep's own. Dependency severities come from the GitHub advisory for each CVE.

## Before

### Gitleaks: 24 findings (1 real secret, 23 false positives)

All 24 were in commit `345d79d`, a **local-only GitHub Desktop stash** (`stash@{0}: On backend: !!GitHub_Desktop<backend>`, created 2026-10-31). That commit was not reachable from any branch, tag or remote ref and was never pushed; Gitleaks found it because it scans `refs/stash` too. The stash held 11,942 added files: a whole `backend/.venv/`, `backend/.env`, a local poppler install (`backend/.tools/`), `__pycache__` files and pipeline text output. It contained no changes to source code.

| # | Rule | File | Severity | Verdict |
|---|---|---|---|---|
| 1 | generic-api-key | `backend/.env` (line 1, `GEMINI_API_KEY`) | Critical | **Real secret.** A live Gemini API key. The same file also held a `MONGO_URI` with an Atlas username and password, which **Gitleaks did not flag** (counted here as part of this finding). |
| 2–3 | generic-api-key | `backend/.venv/.../cryptography/hazmat/bindings/_rust/openssl/hpke.pyi` (77, 101) | – | False positive: type stub parameter names (`private_key: ...`). |
| 4–7 | generic-api-key | `backend/.venv/.../dns/dnssecalgs/eddsa.py` (56, 57, 68, 69) | – | False positive: class attributes naming key types. |
| 8 | private-key | `backend/.venv/.../google/auth/crypt/_python_rsa.py` (38) | – | False positive: the PEM header string the library matches against. |
| 9 | generic-api-key | `backend/.venv/.../google/genai/pagers.py` (143) | – | False positive: docstring example `page_token`. |
| 10–11 | private-key | `backend/.venv/.../google/auth/transport/_mtls_helper.py` (41, 44) | – | False positive: PEM header regex patterns. |
| 12–17 | generic-api-key | `backend/.venv/.../numpy/random/tests/test_generator_mt19937.py` (29, 30, 35, 36, 41, 42) | – | False positive: SHA-256 test vectors. |
| 18 | generic-api-key | `backend/.venv/.../playwright/.../xtermModule-DywYcAf8.js` (5) | – | False positive: minified identifier (`FourKeyMap`). |
| 19 | generic-api-key | `backend/.venv/.../pyasn1_modules/rfc4490.py` (33) | – | False positive: ASN.1 type definition. |
| 20 | generic-api-key | `backend/.venv/.../pyasn1_modules/rfc8017.py` (110) | – | False positive: ASN.1 type definition (`RSAPrivateKey`). |
| 21 | generic-api-key | `backend/.venv/.../pyasn1_modules/rfc7906.py` (119) | – | False positive: ASN.1 object identifier. |
| 22 | generic-api-key | `backend/.venv/.../pypdfium2/internal/consts.py` (11) | – | False positive: constant name mapping. |
| 23 | generic-api-key | `backend/.venv/.../playwright/.../coreBundle.js` (39220) | – | False positive: the fixed `Sec-WebSocket-Key` example from the WebSocket RFC. |
| 24 | generic-api-key | `backend/.venv/.../setuptools/_distutils/msvccompiler.py` (45) | – | False positive: Windows registry API name (`RegEnumKey`). |

Root cause: `backend/.gitignore` already ignored `.env` and `.venv/`, but these files were staged explicitly, so the stash recorded them anyway. The repo-root `.gitignore` only contained `config.js`, so a `.env` or `.venv` at the root (or in `frontend/`) was not ignored at all.

### Semgrep: 4 findings in the app code

| # | Rule | File | Severity | Description |
|---|---|---|---|---|
| 1 | `html.security.audit.missing-integrity` | `frontend/app.html:14` | WARNING | pdf.js is loaded from cdnjs without a Subresource Integrity hash, so a compromised CDN could serve any script into the app. |
| 2 | `javascript...detect-non-literal-regexp` | `frontend/app.js:228` | WARNING | `new RegExp(label + ...)` built from a function argument (possible ReDoS). |
| 3 | `javascript...detect-non-literal-regexp` | `frontend/app.js:343` | WARNING | `new RegExp(k...)` built from a variable (possible ReDoS). |
| 4 | `problem-based-packs.insecure-transport.js-node.using-http-server` | `backend/contract/mock-server.js:399` | WARNING | Node server uses plain HTTP instead of HTTPS. |

### Semgrep: 8 findings in the new pipeline config

These are in files added by this change (they were not in the repo before), and are recorded so the count is complete.

| # | Rule | File | Severity | Description |
|---|---|---|---|---|
| 5–6 | `dependabot-missing-cooldown` | `.github/dependabot.yml:5, 14` | MEDIUM | No cooldown, so Dependabot proposes a release minutes after it is published, before a malicious or broken release can be spotted and pulled. |
| 7–12 | `github-actions-mutable-action-tag` | `.github/workflows/security.yml:24, 48, 49, 61, 62, 65` | WARNING | Actions pinned to version tags (`@v7.0.1`), which the action owner can move to different code. |

### pip-audit: 2 vulnerable packages

| # | Package | Installed | Advisory | Severity | Fixed in | Description |
|---|---|---|---|---|---|---|
| 1 | pymongo | 4.18.2 | CVE-2026-106435 / GHSA-98qm-wvgf-w4cf | High | 4.18.3 | Out-of-bounds read in the C BSON decoder on a malformed Regex element; can crash the process (availability). |
| 2 | dnspython | 2.8.0 | CVE-2026-114605 / GHSA-45c3-73f7-pv4m | High (CVSS 7.5) | 2.9.0 | Crafted DNS message causes excessive CPU in name decompression (DoS). The app uses dnspython to resolve the `mongodb+srv://` Atlas address. |

### Manual review: 1 finding

| # | Component | File | Severity | Description |
|---|---|---|---|---|
| 1 | pdf.js 3.11.174 (CDN) | `frontend/app.html:14`, `frontend/app.js:243` | High | CVE-2024-4367: with the default `isEvalSupported: true`, a crafted PDF can run arbitrary JavaScript in the page. The app opens user-uploaded contract PDFs with `getDocument({data})`, so the default applies. pip-audit only checks Python packages, so no scanner caught this. |

### Totals before

| Tool | Critical | High | Medium | Warning / Low | False positive | Total |
|---|---|---|---|---|---|---|
| Gitleaks | 1 | – | – | – | 23 | 24 |
| Semgrep (app code) | – | – | – | 4 | – | 4 |
| Semgrep (new pipeline config) | – | – | 2 | 6 | – | 8 |
| pip-audit | – | 2 | – | – | – | 2 |
| Manual review | – | 1 | – | – | – | 1 |
