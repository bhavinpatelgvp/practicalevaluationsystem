# Security and Backup Strategy

- Use bcrypt hashes and never log passwords or SMTP secrets.
- Store secrets in environment variables or a managed secret store; rotate the secret key and credentials.
- Keep authorization checks in server-side service boundaries, not only sidebar visibility.
- SQLAlchemy parameterizes database operations; add Alembic migrations and least-privilege MySQL accounts for production.
- Validate GitHub URLs, enforce HTTPS, add GitHub App API checks with timeouts/rate limits, and treat repository contents as untrusted input.
- Put the app behind HTTPS and a reverse proxy with request-size limits. Add CSRF/session hardening appropriate to the chosen authentication gateway.
- Record actor, action, entity, timestamp, and details in audit logs; restrict audit-log access to administrators.
- Run encrypted daily MySQL backups with tested point-in-time recovery and an off-site retention policy.
- Retain academic records according to institutional policy and provide an export/delete workflow where legally required.
