# Eventive — AI-Powered Event Companion

Eventive is a modern event companion platform designed to enhance the attendee experience before, during, and after events. Built with **Flutter**, **FastAPI**, **LangChain**, and **SQLite**, the platform combines AI-powered recommendations, event discovery, networking, and conversational assistance into a single application.

---

# Overview

Eventive complements an existing event management platform by providing intelligent attendee-focused experiences.

The application consists of three primary modules:

- **Feels** — Community-created short event reels.
- **EventiveConnect** — AI-powered networking and event discovery.
- **Ask Eventive** — Conversational AI assistant capable of answering questions about events, schedules, recommendations, and user-specific information.

Additional features include:

- AI-powered recommendations
- Personalized onboarding
- Event discovery
- Saved & liked events
- Connections & messaging
- Interest-based networking
- Notifications
- Admin dashboard
- Content management
- Analytics support

---

# Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | Flutter (Web & Android) |
| Backend | FastAPI |
| Language | Python 3.10+, Dart |
| Database | SQLite + sqlite-vec |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| AI | LangChain, Groq, Gemini, RAG, NL2SQL |
| Authentication | JWT |
| Infrastructure | Docker |

---

# Repository Structure

```
eventive/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── domain/
│   │   ├── infra/
│   │   ├── models/
│   │   └── schemas/
│   ├── tests/
│   ├── alembic/
│   └── seed/
│
├── frontend/
│   ├── lib/
│   ├── assets/
│   ├── android/
│   ├── ios/
│   └── web/
│
├── docker/
├── run_all.sh
├── README.md
└── .gitignore
```

---

# Features

## AI Assistant

- Conversational event assistant
- Personalized recommendations
- Schedule queries
- Event search
- User profile queries
- Retrieval-Augmented Generation (RAG)
- Natural language database querying
- Automatic fallback when LLM APIs are unavailable

---

## Event Discovery

- Browse upcoming events
- Save events
- Like events
- Personalized recommendations
- Category filtering
- Search functionality

---

## Networking

- Discover attendees
- Send and manage connection requests
- Direct messaging
- Interest-based matching
- Recommended connections

---

## Event Content

- Community-created event reels
- Event highlights
- Featured content

---

## Notifications

- Event reminders
- Connection updates
- Personalized notifications

---

# Local Development

## Prerequisites

Install the following tools:

- Flutter
- Python 3.10+
- uv
- Docker
- Git

---

## Running the Application

From the repository root:

```bash
./run_all.sh
```

This script automatically:

- Starts the backend
- Starts the frontend
- Applies database migrations
- Seeds demo data
- Frees occupied development ports
- Generates log files

Backend:

```
http://localhost:8000
```

Swagger UI:

```
http://localhost:8000/docs
```

Frontend:

```
http://localhost:3000
```

---

# Backend Setup

```bash
cd backend

cp .env.example .env

uv sync

uv run alembic upgrade head

uv run python -m app.scripts.seed

uv run python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload
```

To generate additional demo data:

```bash
uv run python -m app.scripts.seed_bulk
```

---

# Frontend Setup

```bash
cd frontend

flutter pub get

flutter run \
    -d web-server \
    --web-port 3000 \
    --dart-define=API_BASE_URL=http://localhost:8000
```

---

# Environment Variables

Create a `.env` file using `.env.example`.

| Variable | Purpose |
| --- | --- |
| JWT_SECRET | JWT signing secret |
| ADMIN_EMAIL | Initial administrator account |
| ADMIN_INITIAL_PASSWORD | Initial administrator password |
| GROQ_API_KEY | Primary language model |
| GEMINI_API_KEY | Fallback language model |
| MEDIA_SIGNING_SECRET | Media URL signing |
| FRONTEND_WEB_DIR | Flutter build directory |

If no LLM API keys are configured, Ask Eventive automatically switches to the built-in RAG and database retrieval pipeline.

---

# Building the Android APK

```bash
cd frontend

flutter build apk --release
```

Generated APK:

```
build/app/outputs/flutter-apk/app-release.apk
```

---

# Docker

Build:

```bash
docker build \
    -f docker/Dockerfile \
    -t eventive .
```

Run:

```bash
docker run \
    --rm \
    -p 8000:8000 \
    eventive
```

The backend and Flutter web application are served from:

```
http://localhost:8000
```

---

# Deployment

The application is fully containerized and can be deployed on any platform supporting Docker containers, including:

- Azure Container Apps
- Azure App Service
- AWS ECS
- Google Cloud Run
- Kubernetes
- Self-hosted Docker

Configure the required environment variables before deployment.

---

# Database

SQLite is used for local development.

Apply migrations:

```bash
uv run alembic upgrade head
```

Generate a migration:

```bash
uv run alembic revision --autogenerate -m "migration_name"
```

---

# Testing

Run backend tests:

```bash
cd backend

uv run pytest
```

Run AI tests:

```bash
uv run pytest tests/unit/domain/ai
```

Analyze the Flutter application:

```bash
cd frontend

flutter analyze
```

---

# API Documentation

Swagger documentation is available at:

```
http://localhost:8000/docs
```

---

# Additional Documentation

- `backend/README.md`
- `frontend/README.md`

---