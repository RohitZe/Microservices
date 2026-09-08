# 🐳 UserVault — A Tale of Two Databases

> *A microservices project that teaches PostgreSQL and Redis to work as a team, not competitors.*

---

## 📖 The Story

Every application has two very different kinds of moments in its life.

The **rare moment**: someone signs up. It happens once per user, it needs to be durable, and it can never be lost. This is a job for a database that lives on disk, honors transactions, and never forgets — **PostgreSQL**.

The **constant moment**: someone logs in, refreshes their profile, checks if they exist. This happens hundreds of times more often than signup ever will. Hitting the disk every single time for something this repetitive is wasteful. This is a job for a database that lives in memory and answers in microseconds — **Redis**.

UserVault is built around this simple but powerful idea: **write rarely, read constantly — so store on disk, but serve from memory.**

To keep that idea clean and honest in code, the project doesn't cram this logic into one bloated service. Instead, it's split into two purpose-built microservices, each with one job, each running in its own container, each replaceable, scalable, and testable on its own.

---

## 🏗️ The Architecture

```
                         ┌─────────────────────────┐
                         │        Docker Compose     │
                         │   (orchestrates it all)   │
                         └─────────────┬─────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
┌───────▼────────┐            ┌─────────▼─────────┐           ┌─────────▼────────┐
│  User Service   │            │   Data Service      │           │   PostgreSQL       │
│  (Flask)        │            │   (Flask)            │           │   Port 5432        │
│  Port 5000      │            │   Port 5001          │           │                     │
│                 │            │                       │           │  init.sql runs on  │
│  Registers new  │───writes──▶│  Reads user data      │──cache──▶ │  first boot, auto-  │
│  users          │            │  cache-first          │   miss    │  creates `users`    │
│                 │            │                       │──fallback▶│  table via volume   │
└─────────────────┘            └──────────┬────────────┘           └─────────────────────┘
                                            │
                                    cache hit│cache miss → write-through
                                            │
                                   ┌────────▼─────────┐
                                   │      Redis         │
                                   │      Port 6379      │
                                   │  (in-memory cache)  │
                                   └─────────────────────┘
```

**Four containers. One `docker-compose.yml`. Zero manual setup.**

---

## 🧩 The Cast of Services

| Service | Role | Port | Why it exists |
|---|---|---|---|
| **PostgreSQL** | Source of truth | `5432` | Durable, disk-backed storage for user records. Writes are infrequent but permanent. |
| **Redis** | Cache layer | `6379` | In-memory store for frequently-read user data. Sits in front of Postgres to absorb read traffic. |
| **User Service** (Flask) | Write path | `5000` | Handles user registration. Inserts new users into PostgreSQL. |
| **Data Service** (Flask) | Read path | `5001` | Handles user lookups. Implements the cache-aside pattern described below. |

---

## 🔁 The Cache-Aside Flow (the heart of this project)

When the **Data Service** receives a request to fetch a user, it doesn't go straight to PostgreSQL. It follows this logic every time:

1. **Check Redis first.**
   - ✅ **Cache hit** → return the data immediately from memory. Fast, cheap, no disk I/O. Response flagged with `cached: true`.
2. **If not in Redis (cache miss):**
   - Query **PostgreSQL** for the record.
   - If found, **write it into Redis** so the *next* read is a cache hit.
   - Return the data with `cached: false`.

This is the classic **cache-aside (lazy-loading) pattern** — Redis is never the source of truth, it's a fast mirror of it. If Redis restarts or the cache is cold, nothing is lost; it simply gets repopulated from PostgreSQL on the next read.

```
Request → Redis? ──hit──► return (cached: true)
             │
            miss
             │
             ▼
        PostgreSQL ──found──► write to Redis ──► return (cached: false)
             │
          not found
             │
             ▼
        404 Not Found
```

---

## 📦 Project Structure

```
uservault/
├── docker-compose.yml
├── .env                        # local environment variables (never committed)
├── user-service/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── data-service/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
└── postgres/
    └── init.sql                # auto-run on first container start, creates `users` table
```

---

## ⚙️ How the Pieces Are Wired

- Each service (**User Service**, **Data Service**) has its **own `Dockerfile`**, so each is built as an independent, minimal, single-purpose image.
- **`docker-compose.yml`** brings all four containers up together for local development, on a shared Docker network, so services can reach each other by container name (e.g. `postgres`, `redis`) instead of hardcoded IPs.
- On the **first boot of the PostgreSQL container**, an `init.sql` file is mounted in as a **volume** into Postgres's docker-entrypoint-initdb directory. Postgres automatically executes it once, creating the `users` table — no manual migration step needed.
- Configuration (DB host, DB credentials, Redis host, etc.) is injected via a **`.env`** file for local development.
- In **production**, secrets are not read from `.env` — they're pulled from a proper secrets manager like **AWS SSM Parameter Store** or **HashiCorp Vault**, keeping credentials out of source control and out of plaintext files entirely.

---

## 🚀 Getting Started (Local Development)

### Prerequisites
- Docker
- Docker Compose

### 1. Clone the repo
```bash
git clone https://github.com/RohitZe/Microservices.git
cd uservault
```

### 2. Set up environment variables
Create a `.env` file in the root directory:

```env
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin123
POSTGRES_DB=userdb
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

REDIS_HOST=redis
REDIS_PORT=6379

USER_SERVICE_PORT=5000
DATA_SERVICE_PORT=5001
```

### 3. Spin everything up
```bash
docker-compose up --build
```

This single command will:
- Build the **User Service** and **Data Service** images from their Dockerfiles
- Pull and start **PostgreSQL** and **Redis**
- Mount `init.sql` into PostgreSQL and auto-create the `users` table
- Start all four containers on a shared network

### 4. Verify it's running
```bash
docker ps
```
You should see 4 containers: `postgres`, `redis`, `user-service`, `data-service`.

---

## 🔌 API Endpoints

### User Service — `http://localhost:5000`
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/register` | Registers a new user in PostgreSQL |

### Data Service — `http://localhost:5001`
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/user/<id>` | Fetches a user — Redis first, PostgreSQL on cache miss |

---

## 🔐 Production Notes

For production deployments, this project intentionally avoids `.env` files. Instead:

- Secrets (DB credentials, Redis auth, API keys) should be pulled from **AWS SSM Parameter Store** or **HashiCorp Vault** at container startup or via your orchestrator's secret injection (ECS task definitions, Kubernetes Secrets, etc.).
- The same Docker images built for local development are meant to be reused in production — only the *configuration source* changes, not the code.

---

## 🧠 Why This Design Matters

This isn't just "an app with a database and a cache" — it's a deliberate demonstration of a real-world scaling pattern:

- **Separation of concerns** → write path and read path are two different services, so each can be scaled independently. If reads spike, scale the Data Service and Redis, not the whole stack.
- **Right tool for the right job** → PostgreSQL for durability, Redis for speed.
- **Infrastructure as part of the codebase** → the database schema (`init.sql`) and the environment are versioned right alongside the application code.
- **Local-to-production parity** → the same containers that run on a laptop via Docker Compose are the containers that ship to production.

---

## 🛠️ Tech Stack

- **Python (Flask)** — User Service & Data Service
- **PostgreSQL** — persistent storage
- **Redis** — caching layer
- **Docker & Docker Compose** — containerization & orchestration
- **AWS SSM / HashiCorp Vault** — production secrets management

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).