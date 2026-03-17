# Backend Setup (FastAPI + PostgreSQL)

## 1. Start API + PostgreSQL containers

```bash
cd backend
docker compose up -d
```

## 2. Configure environment

```bash
cp .env.example .env
```

Update `SECRET_KEY` and `ENCRYPTION_KEY` for non-dev usage.

## 3. Install dependencies and run API

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

On startup, tables are created automatically and `backend/uploads` is created.

## Auth Flow

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me` (Bearer token)

## User Settings

- `GET /api/v1/settings/me`
- `PUT /api/v1/settings/me`

## Data Sources

- `GET /api/v1/data-sources` (list current user sources)
- `POST /api/v1/data-sources/upload` (multipart file upload)
- `POST /api/v1/data-sources/db-connection` (store DB credentials securely)
- `DELETE /api/v1/data-sources/{data_source_id}`

Uploaded files are stored on disk at:

- In container: `/app/uploads/<user_id>/<uuid>_<original_name>`
- On your host (bind mount): `backend/uploads/<user_id>/<uuid>_<original_name>`

The absolute file path is saved in PostgreSQL (`data_sources.file_path`).
