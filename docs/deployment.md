# Deployment

## Docker

```bash
docker build -t tpems .
docker run --env-file .env -p 8501:8501 tpems
```

For a Linux VPS, place Nginx or another HTTPS reverse proxy in front of port 8501, restrict the Streamlit port to localhost, and use a systemd or container restart policy.

## Streamlit Cloud

Push the repository to GitHub, create an app pointing at `app.py`, and configure secrets equivalent to `.env.example` in the Streamlit Cloud settings. Use a managed MySQL instance reachable from the deployment network; SQLite is for local development only.

## Operations

Run database migrations through Alembic in CI/CD. Schedule reminders and backups outside the Streamlit process. Monitor application logs, failed SMTP deliveries, database connection health, and audit-log volume. Restore backups into a staging database before relying on them.
