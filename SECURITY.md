# Security Policy

## Supported Versions

Security updates are actively applied to the main development branch of Zhenyi.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

---

## Reporting a Vulnerability

We take the security of Zhenyi and its users seriously. If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public GitHub issue** for undisclosed security vulnerabilities.
2. Please submit your disclosure via a **[GitHub Private Vulnerability Report](https://github.com/ShamalLakshan/zhenyi/security/advisories/new)** or contact the repository maintainers directly.
3. Include detailed steps to reproduce the issue, proof-of-concept scripts or requests, and the impact of the vulnerability.

### Response Timeline
- **Initial acknowledgment**: Within 48 hours.
- **Triage & validation**: Within 5 business days.
- **Remediation & patch release**: Depending on severity, patches are released as high-priority hotfixes.

---

## Security Model & Threat Considerations

### 1. API Keys and Secret Handling
- **Environment Separation**: API keys (`GEMINI_KEY_*`, `GROQ_KEY_*`, etc.) must reside solely in your local `.env` file or host environment variables.
- **Indirect Configuration**: `agents.yaml` references environment variable *names*, not the actual key secrets.
- **Zero Secret Leakage**: The runtime `KeyPool` loads keys directly from environment memory at dispatch time. Keys are strictly forbidden from being written to `zhenyi.db`, output logs, or broadcast across WebSocket/REST endpoints.
- **Git Exclusions**: The root `.gitignore` ignores `.env*`, `*key*.json`, `*.pem`, `*.token`, and local database files. Always verify that no secrets appear in staged commits:
  ```bash
  git status
  ```

### 2. Untrusted Web Content & Prompt Injection
- Zhenyi scrapes external sources (HackerNews, web pages, arXiv, Wikipedia, etc.). This data is untrusted input.
- **Sanitization & Chunk Limits**: The triage layer truncates chunks to a maximum character and token length before passing them to analyst prompts, mitigating context window exploitation.
- **Structured Schema Enforcement**: Agent responses are parsed into structured schemas (JSON findings, scores, and confidence levels) rather than executed directly.
- **Circuit Breakers**: Scrapers implement circuit breaker thresholds to prevent accidental denial-of-service against third-party endpoints.

### 3. Database & Local Storage
- Local storage (`zhenyi.db`) contains query text, agent thoughts, scraper findings, and citations.
- The database is intended for local developer or single-tenant research use. Keep file permissions restricted to the host user:
  ```bash
  chmod 600 zhenyi.db
  ```

### 4. Deployment & Network Exposure
By default, the backend binds to `127.0.0.1:8000` or `0.0.0.0:8000` without authentication.
- **Localhost Only**: When running locally, do not expose port 8000 to public networks without an authentication layer.
- **Production Exposure**: When deploying to remote servers, place Zhenyi behind a hardened reverse proxy (such as Nginx, Caddy, or Cloudflare Tunnel) with HTTPS/TLS, strict CORS headers, and an authentication layer (OAuth2 / HTTP Basic Auth / API Gateway tokens).
