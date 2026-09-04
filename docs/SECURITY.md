# Security and Operational Boundaries

- Authorized devices, accounts, applications, and workflows only.
- Do not store passwords, session tokens, API keys, cookies, or proxy credentials in Git.
- Use local environment variables or an ignored `.env` file for secrets.
- Keep `.env.example` limited to key names and non-secret examples.
- Evidence must be sanitized before sharing.
- Avoid destructive device actions unless explicitly required and approved.
- Scale only after the single-device workflow is stable and observable.
