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

## After

All scans re-run on the `security-pipeline` branch on 2026-10-31:

| Tool | Result |
|---|---|
| Gitleaks, full history (`gitleaks git .`, every commit on all refs, including this branch's fix commits) | **No leaks found** |
| Gitleaks, working tree (`gitleaks dir .`, includes untracked files) | **No leaks found** |
| Semgrep `--config auto --error` (494 rules, 190 files) | **0 findings**, exit code 0 |
| pip-audit `-r backend/requirements.txt` | **No known vulnerabilities found** |
| Backend test suite (`pytest`, Python 3.11) | **171 passed** |

### Gitleaks

| Finding | Action taken |
|---|---|
| #1 Gemini API key + MongoDB URI with credentials in `backend/.env` (local stash) | Both credentials were **rotated** by the repo owner (new Gemini key; new Atlas database user password) and updated in Render. The stash was checked first: it held no source-code changes, only added files. The poppler tool and pipeline text output it held were extracted back into their (git-ignored) folders, and then the stash was **dropped** (`git stash drop stash@{0}`). The secrets were already read from environment variables (`ai/gemini.py`, `db/mongo.py`) with placeholders in `backend/.env.example`, so no code change was needed. No history rewrite was needed: the commit was never on a branch or pushed. |
| #2–24 false positives in `backend/.venv/` | Went away with the stash. No allowlist was added, so Gitleaks would still flag similar matches if a `.venv` were ever committed. |
| Root cause | The repo-root `.gitignore` now ignores `.env`, `.env.*` (except `.env.example`), `*.pem`, `*.key`, `.venv/`, `venv/`, `env/`, `__pycache__/`, `*.py[cod]` and `.tools/` in every folder, not only under `backend/`. The CI Gitleaks job also catches secrets that are force-added past `.gitignore`. |

Note: the dropped stash's objects remain in the local `.git` folder as unreachable objects until Git garbage-collects them (by default, after two weeks). They are not on any ref, are never pushed, and Gitleaks no longer sees them. The credentials in them are revoked.

### Semgrep (app code)

| # | Finding | Verdict | Fix |
|---|---|---|---|
| 1 | `frontend/app.html` pdf.js without SRI | Real | Added `integrity="sha512-..."` (the hash published by cdnjs, checked against the downloaded file), `crossorigin="anonymous"` and `referrerpolicy="no-referrer"`. The browser now refuses the script if the CDN serves anything else. |
| 2 | `frontend/app.js` `new RegExp(label + ...)` | False positive | `label` is only ever one of six hard-coded patterns in the same function; the user's PDF text is the string being searched, not the pattern. Marked with an explanatory comment and `nosemgrep`. |
| 3 | `frontend/app.js` `new RegExp(k...)` | False positive | `k` comes from the fixed `PLACES` table of place names in the code, not from input. Marked with an explanatory comment and `nosemgrep`. |
| 4 | `backend/contract/mock-server.js` plain HTTP | False positive | A mock API for local frontend development that serves canned example JSON; it is never deployed (the deployed app is the FastAPI service behind Render's HTTPS). Marked with an explanatory comment and `nosemgrep`. |

### Semgrep (new pipeline config)

| # | Finding | Fix |
|---|---|---|
| 5–6 | Dependabot without cooldown | Added `cooldown: default-days: 7` to both ecosystems. Security updates are not delayed by it. |
| 7–12 | Actions pinned to tags | Pinned every action to its full commit SHA, with the release tag in a comment: `actions/checkout` v7.0.1, `actions/setup-python` v7.1.0, `pypa/gh-action-pip-audit` v1.1.0. The gitleaks binary is pinned to v8.30.1 and its SHA-256 is verified against the release checksums before it runs. |

### pip-audit

| Package | Change | Check |
|---|---|---|
| pymongo | 4.18.2 → **4.18.3** (minimum fixed version) | `pip check` clean; 171 tests pass; app starts and serves `/health`, `/projects`, `/overlaps`, the site and `/config.js`. |
| dnspython | 2.8.0 → **2.9.0** (minimum fixed version) | Same as above. dnspython resolves the `mongodb+srv://` address. |

### Manual review

| Finding | Fix |
|---|---|
| pdf.js 3.11.174, CVE-2024-4367 | `getDocument` is now called with `isEvalSupported: false`, the mitigation documented for this CVE; the font code path that ran attacker-controlled script is no longer used. Checked with the same cdnjs build in Node: it still extracts the full text of `backend/data/samples/sample_contract_hardeeville.pdf`. Upgrading pdf.js to 4.x would remove the vulnerable code entirely, but 4.x ships only as ES modules, which changes how the page loads it, so that upgrade is left as a follow-up. |

### Totals after

| Tool | Before | Fixed | False positive (documented) | Remaining |
|---|---|---|---|---|
| Gitleaks | 24 | 1 (rotated + removed) | 23 | 0 |
| Semgrep (app code) | 4 | 1 | 3 | 0 |
| Semgrep (new pipeline config) | 8 | 8 | 0 | 0 |
| pip-audit | 2 | 2 | 0 | 0 |
| Manual review | 1 | 1 (mitigated) | 0 | 0 |
