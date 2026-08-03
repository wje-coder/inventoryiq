# InventoryIQ

## Overview

InventoryIQ is an agentic AI platform that helps organizations analyze inventory, sales, pricing, and operational data. Users can upload business datasets, ask natural language questions, generate SQL queries, forecast revenue, detect pricing and inventory anomalies, and receive evidence based recommendations through specialized AI agents.

This project is being developed as a production quality portfolio application demonstrating modern AI engineering, business intelligence, and full stack software development.

## Objectives

InventoryIQ is designed to:

* Validate uploaded business data
* Generate safe SQL from natural language
* Calculate business KPIs
* Detect pricing and inventory anomalies
* Forecast future revenue
* Produce executive reports
* Demonstrate production ready agentic AI workflows

## Planned Features

* Multi agent AI architecture using LangGraph
* FastAPI backend
* React frontend
* PostgreSQL database
* Docker deployment
* Authentication and user management
* Business KPI dashboard
* Natural language to SQL
* Revenue forecasting
* Interactive data visualizations
* Executive report generation
* Audit logging
* Automated testing

## Technology Stack

### Backend

* Python
* FastAPI
* LangGraph
* PostgreSQL
* SQLAlchemy
* Alembic

### Frontend

* React
* TypeScript
* Tailwind CSS

### AI & Analytics

* OpenAI API
* Pandas
* scikit learn
* Plotly

### Infrastructure

* Docker
* GitHub Actions
* GitHub

## Project Status

🚧 Currently under active development.

The project is being built in multiple phases, beginning with infrastructure and progressing toward a production ready AI powered business intelligence platform.

## Roadmap

- [x] Project foundation
- [x] Authentication
- [x] Dataset upload
- [ ] Data quality analysis
- [ ] AI agent workflows
- [ ] Natural language SQL
- [ ] KPI dashboard
- [ ] Revenue forecasting
- [ ] Executive reporting
- [ ] Testing
- [ ] Deployment

## Local Setup

### Prerequisites

* Docker and Docker Compose
* Node.js 20+ and npm (for running the frontend outside Docker)
* Python 3.11+ (for running the backend outside Docker)

### 1. Configure environment variables

Copy the root env template and adjust values as needed:

```bash
cp .env.example .env
```

This file sets PostgreSQL credentials, service ports, the frontend's
backend API URL, JWT/auth configuration, and dataset upload settings
(`MAX_UPLOAD_SIZE_BYTES`, `DATASET_PREVIEW_ROW_LIMIT`). Do not commit
your real `.env` file.

`SECRET_KEY` is required — Docker Compose will refuse to start the
backend without it. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 2. Run the full stack with Docker Compose

```bash
docker compose up --build
```

This starts three services:

* `db` — PostgreSQL 16, with a healthcheck gating startup of the backend
* `backend` — FastAPI app on `http://localhost:8000` (docs at `/docs`, health at `/health`)
* `frontend` — Vite dev server on `http://localhost:5173`

Stop the stack with `Ctrl+C`, or `docker compose down` to also remove containers.

### 3. Run services locally without Docker (optional)

**Backend:**

```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head    # apply database migrations (needs Postgres reachable)
uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

### 4. Run tests, linting, and type checks

**Backend:**

```bash
cd backend
pytest              # tests
ruff check .         # lint
ruff format --check . # format check
mypy app             # type check
```

**Frontend:**

```bash
cd frontend
npm test             # tests (vitest)
npm run lint          # lint (eslint)
npm run format:check  # format check (prettier)
npm run typecheck     # type check (tsc)
```

These same checks run automatically in GitHub Actions on every push and
pull request against `main` (see `.github/workflows/ci.yml`).

## Authentication

### Model

* **Access tokens** are short-lived JWTs (default 30 minutes, `ACCESS_TOKEN_EXPIRE_MINUTES`), returned in the JSON response body and kept by the frontend in memory only — never in `localStorage`/`sessionStorage`.
* **Refresh tokens** are longer-lived JWTs (default 7 days, `REFRESH_TOKEN_EXPIRE_DAYS`) delivered exclusively as an **httpOnly, SameSite=Lax cookie** scoped to `/auth`. JavaScript can never read this cookie; the browser sends it automatically on requests to the API.
* Every protected request re-verifies the user against the database (not just the JWT signature), so deactivating or changing a user's role takes effect on their very next request, not just after their token expires.
* The **first user ever registered is automatically made `admin`**; every user after that registers as `viewer`. An admin can promote other users via `PATCH /users/{id}/role`. There's no separate seed script or admin env var — this bootstrap rule is what gets you your first admin account on a fresh database.
* Logout clears the refresh cookie server-side. There is no server-side access-token revocation list yet, so an already-issued access token stays valid until it naturally expires (at most `ACCESS_TOKEN_EXPIRE_MINUTES`) even after logout — a documented trade-off for this phase.

### Roles

| Role | Intended use |
|---|---|
| `admin` | Full access, including user management (`GET /users`, `PATCH /users/{id}/role`) |
| `analyst` | Reserved for future data/analysis endpoints (Phase 3+) |
| `viewer` | Default role for self-registered users |

### API endpoints

| Method | Path | Auth required | Description |
|---|---|---|---|
| POST | `/auth/register` | No | Create an account (`email`, `password`, `full_name`) |
| POST | `/auth/login` | No | Form-encoded (`username`=email, `password`) login |
| POST | `/auth/refresh` | Refresh cookie | Issue a new access token; rotates the refresh cookie |
| POST | `/auth/logout` | No | Clear the refresh cookie |
| GET | `/auth/me` | Bearer token | Current user's profile |
| GET | `/users` | Bearer token, `admin` only | List all users |
| PATCH | `/users/{id}/role` | Bearer token, `admin` only | Change a user's role |

### Example

```bash
# Register (first user on a fresh DB becomes admin)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"correct horse battery","full_name":"Your Name"}'

# Login (note: form-encoded, not JSON)
curl -X POST http://localhost:8000/auth/login \
  -d "username=you@example.com&password=correct horse battery" \
  -c cookies.txt

# Call a protected endpoint
curl http://localhost:8000/auth/me -H "Authorization: Bearer <access_token>"
```

### Frontend routes

* `/login`, `/register` — public
* `/` — protected dashboard (redirects to `/login` if not authenticated); shows the signed-in user's profile and the backend health status

On load, the frontend silently calls `/auth/refresh` using the refresh cookie to restore a session after a page reload, so a logged-in user stays logged in across refreshes without re-entering credentials.

## Dataset Ingestion and Management

Authenticated users can upload CSV or Excel (`.xlsx`) business datasets,
which are validated, profiled, and stored for later analytics and agent
workflows.

### Model

* Each **Dataset** belongs to exactly one owning user (`owner_user_id`).
  Non-admin users can only see and act on their own datasets; admins can
  see all datasets. Authorization is enforced at the service layer, and
  a dataset that doesn't belong to the caller (and isn't visible because
  the caller is an admin) returns `404`, not `403`, so the API never
  confirms another user's dataset exists.
* Uploaded files are never trusted as storage paths. The original
  filename is sanitized and kept only for display; the file is written
  to disk under a random UUID-based name
  (`{DATASET_STORAGE_DIR}/{dataset_id}/{uuid}.{ext}`), outside Git
  tracking (see `.gitignore`'s `backend/var/` rule and the
  `dataset_storage` Docker volume).
* Ingestion is **synchronous** (no background job queue). A row-data CSV
  is small enough, and the parsing/validation work light enough, that a
  queue would add operational complexity without a real benefit at this
  scale — consistent with keeping the app a modular monolith. The
  request blocks until the file is parsed, validated, and either marked
  `ready` (with column metadata persisted) or `failed` (with the reason
  recorded and no orphaned file left behind).
* Row-level data itself is stored as a normalized CSV file on disk, not
  as one row per Postgres record — Postgres holds dataset metadata,
  column schema/mapping, validation findings, and the audit trail only.
  This keeps large uploads from ballooning the database while still
  giving every dataset a fully documented, versioned home for its data.
* Every upload, validation run (pass or fail), display-name change,
  column-mapping change, and deletion is recorded as a
  `DatasetAuditEvent` tied to the dataset and the acting user.

### Dataset status values

`uploaded` → `validating` → `ready` (or `failed`) → `deleted` (soft
delete; a deleted dataset's metadata row is kept for audit purposes but
is no longer returned by any endpoint, and its files are removed from
disk).

### Column mapping and available analyses

Each inferred column can optionally be mapped to one of 20 recognized
business fields (`product_id`, `sku`, `upc`, `product_name`, `category`,
`brand`, `supplier`, `unit_cost`, `retail_price`, `sale_price`,
`quantity_available`, `quantity_sold`, `quantity_returned`, `order_id`,
`order_date`, `return_date`, `customer_id`, `region`, `channel`,
`status`). Not every field needs to be mapped — `GET/PATCH
/datasets/{id}/columns` both report which future analyses (e.g. "Margin
analysis", "Inventory turnover") are unlocked by the fields currently
mapped.

### API endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/datasets/upload` | Upload a CSV/XLSX file (`multipart/form-data`, field `file`, optional `display_name`) |
| GET | `/datasets` | List the caller's datasets (all datasets, for admins) |
| GET | `/datasets/{id}` | Dataset metadata |
| GET | `/datasets/{id}/preview` | A row-limited preview (`DATASET_PREVIEW_ROW_LIMIT`, default 50) |
| GET | `/datasets/{id}/columns` | Inferred columns, current mapping, and available analyses |
| PATCH | `/datasets/{id}` | Rename (`display_name`) |
| PATCH | `/datasets/{id}/columns` | Update column-to-business-field mapping |
| DELETE | `/datasets/{id}` | Soft-delete a dataset and remove its files |
| POST | `/datasets/{id}/validate` | Re-run validation (e.g. after a mapping change) |

All endpoints require a bearer access token. Validation failures (e.g.
duplicate column names, malformed CSV, an unreadable Excel file, an
empty file, a file with no usable rows) return a structured error body
— a machine-readable `code`, a human-readable `message`, and a list of
specific `findings` — never a local file path, database detail, or
stack trace.

### Frontend

* `/datasets` — protected page (same auth/redirect behavior as `/`):
  a drag-and-drop-or-click upload area (showing accepted formats and
  the size limit, with live upload progress and validation errors), a
  dataset list (status, row/column counts, upload date), and a detail
  panel for the selected dataset with a preview table, a column-mapping
  editor (with the resulting available analyses), an editable display
  name, and delete-with-confirmation.

### Synthetic sample data

`tools/synthetic_data/generate.py` is a reproducible (fixed seed `42`),
standard-library-only generator for a realistic ecommerce dataset —
useful for exercising the upload/validation pipeline end to end. See
[`tools/synthetic_data/README.md`](tools/synthetic_data/README.md) for
usage, [`DATA_DICTIONARY.md`](tools/synthetic_data/DATA_DICTIONARY.md)
for the full column reference, and `tools/synthetic_data/sample/` for a
small, committed, ready-to-upload sample (the full generated output is
gitignored — regenerate it rather than expect it in Git). It includes
seasonality, regional demand differences, category-specific margins,
discounts, returns, stockouts, excess inventory, and supplier patterns,
alongside nine intentional data quality problems (missing product IDs,
duplicate rows, malformed UPCs, negative inventory, invalid dates,
inconsistent category names, sale prices below cost, price outliers,
and products with rising return rates) for testing the ingestion
pipeline's validation logic.

```bash
python tools/synthetic_data/generate.py       # writes CSVs to tools/synthetic_data/output/
python -m pytest tools/synthetic_data/test_generate.py -v   # validate the generator itself
```

## Author

Jetwyn Wilson
Master of Engineering in Artificial Intelligence
