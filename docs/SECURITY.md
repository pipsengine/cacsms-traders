# Security baseline

- Passwords are PBKDF2-HMAC-SHA256 hashed with per-user salts.
- Bearer session tokens are random and only SHA-256 hashes are persisted.
- Session revocation and expiry are enforced server-side.
- Tenant access is checked for every tenant-scoped endpoint.
- Permissions are server-side RBAC claims, not UI visibility rules.
- Live/autonomous account toggles are independently controlled and audited.
- Secrets belong in environment variables; never in React bundles or source control.
- Audit events store actor, tenant, action, entity, correlation ID and before/after snapshots.
- Production deployment should terminate TLS at the reverse proxy and use secure secret storage.
