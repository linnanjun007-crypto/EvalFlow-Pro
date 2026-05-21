# EvalFlow Pro Backend

FastAPI backend for EvalFlow Pro.

## Database

This project is configured to connect to PostgreSQL:

- Database: `agent_king`
- Username: `postgres`
- Password: `123456`
- Host: `localhost`
- Port: `5432`

Connection string:

```text
postgresql+psycopg://postgres:123456@localhost:5432/agent_king
```

## SQL schema

The full PostgreSQL schema is available in:

- `database_schema.sql`

You can execute it directly in Navicat to create all required tables.

## Structure

- `app/api`: HTTP route layer
- `app/services`: business logic layer
- `app/integrations`: integrations with LangGraph and external systems
- `app/models`: database models
- `agent/`: LangGraph workflow implementation

## Run

```bash
uvicorn app.main:app --reload
```
