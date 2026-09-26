# ReserveX — Learning Guide

> **Single source of truth** for WHAT / WHY / HOW / WHERE for every component.
> VIVA_GUIDE.md and README.md link here instead of repeating explanations.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Flask & REST APIs](#flask--rest-apis)
3. [PostgreSQL & Transactions](#postgresql--transactions)
4. [Concurrency Safety](#concurrency-safety)
5. [Docker & Docker Compose](#docker--docker-compose)
6. [Kubernetes](#kubernetes)
7. [HPA & Scaling](#hpa--scaling)
8. [Prometheus & Grafana](#prometheus--grafana)
9. [AWS Infrastructure](#aws-infrastructure)
10. [Terraform](#terraform)
11. [CI/CD & GitHub Actions](#cicd--github-actions)
12. [Component Reference Table](#component-reference-table)

---

## Architecture Overview

ReserveX is a **microservices-based event reservation platform**. The central technical problem:

> "How can a distributed cloud-native reservation system process a sudden burst of concurrent booking requests while maintaining inventory correctness, automatically scaling under load, and providing real-time observability?"

### Three Microservices

| Service | Port | Owns | Role |
|---|---|---|---|
| User Service (SA1) | 5001 | `users` table | Create/retrieve users |
| Event Service (SA2) | 5002 | `events` table | Manage events, **authoritative inventory owner** |
| Booking Service (SA3) | 5003 | `bookings` table | Orchestrator — calls SA1 and SA2 via REST |

### Key Rule: Services communicate via REST APIs, never direct database access

```
Client → Booking Service → User Service (validate user)
                         → Event Service (reserve slot atomically)
                         → Create booking record
                         → Lambda notification (async, non-blocking)
```

---

## Flask & REST APIs

### WHAT
Flask is a lightweight Python web framework. It turns Python functions into HTTP endpoints.

### WHY
- Minimal boilerplate — easy for a student to understand every line
- No magic — you see exactly how requests map to functions
- Widely used in the industry

### HOW
```python
@app.post("/bookings")
def create_booking():
    data = request.get_json()  # Read JSON body
    # ... process ...
    return jsonify(result), 201  # Return JSON response
```

### Key Files

| File | Purpose | Depends On |
|---|---|---|
| `services/user-service/app.py` | User REST API | `db.py` |
| `services/event-service/app.py` | Event REST API + atomic reservation | `db.py` |
| `services/booking-service/app.py` | Booking orchestrator | `db.py`, User Service, Event Service |

---

## PostgreSQL & Transactions

### WHAT
PostgreSQL is a relational database. It stores data in tables with rows and columns, enforced by a schema.

### WHY (not in-memory dicts)
- **Persistence**: Data survives restarts
- **Transactions**: ACID guarantees for concurrent access
- **Constraints**: Database enforces rules (unique email, non-negative slots)
- **Scalability**: Works the same locally, in Docker, and in Kubernetes

### Schema Design

```sql
-- users: owned by User Service
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- events: owned by Event Service
CREATE TABLE events (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(255) NOT NULL,
    total_slots      INTEGER NOT NULL CHECK (total_slots > 0),
    available_slots  INTEGER NOT NULL CHECK (available_slots >= 0),
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT slots_within_bounds CHECK (available_slots <= total_slots)
);

-- bookings: owned by Booking Service
CREATE TABLE bookings (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    event_id    INTEGER NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED',
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Database Constraints Explained

| Constraint | What It Does | What Breaks Without It |
|---|---|---|
| `PRIMARY KEY` | Unique identifier for each row | No way to reference specific records |
| `NOT NULL` | Prevents empty values | Incomplete data enters the system |
| `UNIQUE (email)` | One account per email | Duplicate registrations |
| `CHECK (available_slots >= 0)` | Database-level safety net | Negative inventory possible |
| `CHECK (available_slots <= total_slots)` | Can't exceed capacity | Released slots could over-fill |

### Connection Pooling (db.py)

```python
pool = psycopg_pool.ConnectionPool(DATABASE_URL, min_size=2, max_size=10)
```

**WHY**: Opening a new database connection per request is slow (~50ms). A pool keeps connections ready, reusing them across requests.

---

## Concurrency Safety

### The Problem: Overselling

If two requests check availability at the same time:
```
Request A: SELECT available_slots → 1    (sees 1 slot)
Request B: SELECT available_slots → 1    (also sees 1 slot)
Request A: UPDATE SET available_slots = 0  (reserves it)
Request B: UPDATE SET available_slots = -1 (OVERSOLD!)
```

### The Solution: Atomic UPDATE

```sql
UPDATE events
SET available_slots = available_slots - 1
WHERE id = ? AND available_slots > 0
RETURNING id, available_slots
```

**WHY this works**: PostgreSQL's UPDATE acquires a **row-level lock**. Even with 1000 simultaneous requests:
- Request A locks the row, decrements, commits
- Request B waits for the lock, then sees the updated value
- No overselling possible

### Tested Result
```
50 slots → 200 concurrent requests → exactly 50 succeeded
0 overselling. 0 negative inventory.
```

### Compensation Pattern

If the booking record fails to save after a slot was reserved:
```
Booking Service → Event Service POST /events/{id}/release
```
This is NOT a distributed transaction. It's a simple compensation pattern. If the release also fails, a slot is "leaked" — acknowledged limitation for this academic project.

---

## Docker & Docker Compose

### WHAT
- **Docker**: Packages an application into a container (isolated environment with its own filesystem, network, processes)
- **Docker Compose**: Runs multiple containers together with shared networking

### WHY
- **Consistency**: Same environment locally, in CI, and in production
- **Isolation**: Each service runs independently
- **Reproducibility**: Anyone can run `docker compose up` and get the full system

### Dockerfile Explained

```dockerfile
FROM python:3.12-slim          # Base image (small, ~150MB)
WORKDIR /app                   # Set working directory
COPY requirements.txt .        # Copy deps first (layer caching!)
RUN pip install -r requirements.txt  # Install deps (cached if unchanged)
COPY . .                       # Copy app code
EXPOSE 5001                    # Document the port
CMD ["gunicorn", ...]          # Production WSGI server
```

### WHY gunicorn instead of Flask dev server
Flask's `app.run(debug=True)` is **single-threaded**. Gunicorn spawns multiple worker processes, enabling real concurrent request handling.

### Networking Change: localhost → service names

| Environment | User Service URL | Why |
|---|---|---|
| Local | `http://localhost:5001` | Everything runs on your machine |
| Docker | `http://user-service:5001` | Each container has its own network; Docker DNS resolves service names |
| Kubernetes | `http://user-service:5001` | Kubernetes Service DNS works the same way |

### Docker Compose Services
```
postgres (PostgreSQL 16) → port 5432
user-service → port 5001
event-service → port 5002
booking-service → port 5003
```

---

## Component Reference Table

| Component | What | Why | Input | Output | Depends On |
|---|---|---|---|---|---|
| Flask | Python web framework | Lightweight, explicit | HTTP requests | JSON responses | Python |
| REST API | Communication pattern | Standard, stateless | HTTP + JSON | HTTP + JSON | Flask |
| PostgreSQL | Relational database | ACID, persistence, constraints | SQL queries | Query results | — |
| psycopg3 | Python PostgreSQL driver | Direct SQL, no ORM hiding | Python calls | DB results | PostgreSQL |
| Connection Pool | Reuses DB connections | Performance (~50ms saved/request) | Config | Connections | psycopg3 |
| Prometheus | Metrics collection | Observe system behavior | Scrape /metrics | Time-series data | Application |
| prometheus_client | Python metrics library | Expose counters/histograms | Code instrumentation | /metrics endpoint | Prometheus |
| gunicorn | Production WSGI server | Multi-worker concurrency | HTTP requests | Flask app | Flask |
| Docker | Container runtime | Consistency, isolation | Dockerfile | Container image | — |
| Docker Compose | Multi-container orchestration | Run full system | docker-compose.yml | Running services | Docker |
| Kubernetes | Container orchestration | Scaling, self-healing | YAML manifests | Running pods | Docker images |
| HPA | Horizontal Pod Autoscaler | Auto-scale on load | CPU metrics | Pod count changes | Metrics Server |
| k6 | Load testing tool | Generate traffic | JavaScript script | Performance report | — |
| Grafana | Visualization | See metrics visually | Prometheus data | Dashboard | Prometheus |
| Terraform | Infrastructure as Code | Reproducible AWS | .tf files | AWS resources | AWS |
| EKS | Managed Kubernetes | AWS-hosted K8s | Terraform | K8s cluster | AWS, Terraform |
| Lambda | Serverless function | Async notification | Booking event | CloudWatch log | AWS |

---

## Kubernetes

### WHAT
Kubernetes (K8s) is a container orchestration platform. It manages running Docker containers across a cluster of machines.

### WHY
While Docker Compose is great for local development on one machine, Kubernetes is built for production:
- **Self-healing**: If a pod crashes, K8s restarts it automatically.
- **Scaling**: K8s can run many copies (replicas) of a service and load balance traffic between them.
- **Service Discovery**: Built-in DNS (`http://user-service:5001`) works cluster-wide.

### Key Concepts Used

| Concept | Purpose in ReserveX |
|---|---|
| **Pod** | The smallest deployable unit. One instance of our Flask app container. |
| **Deployment** | Manages stateless Pods (User, Event, Booking services). Ensures X replicas are always running. |
| **StatefulSet** | Manages stateful Pods (PostgreSQL). Ensures stable network ID and persistent storage across restarts. |
| **Service (ClusterIP)** | Internal networking. Allows Booking Service to talk to User/Event services safely. |
| **Service (NodePort/LoadBalancer)** | External networking. Exposes Booking Service to the outside world. |
| **ConfigMap** | Stores non-secret config like `USER_SERVICE_URL`. |
| **Secret** | Stores base64-encoded sensitive data like `DATABASE_URL`. |

---

## HPA & Scaling

### WHAT
Horizontal Pod Autoscaler (HPA) automatically updates a workload resource (like a Deployment) with the aim of automatically scaling the workload to match demand.

### WHY
Traffic is spiky. You don't want to pay for 100 servers at 3 AM when traffic is low, but you need them at 10 AM during a ticket release.

### HOW (Booking Service HPA)
```yaml
metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
```
1. **Metrics Server** constantly monitors CPU usage of all pods.
2. We use `k6` to send thousands of requests to the Booking Service.
3. CPU utilization spikes above 60%.
4. HPA notices this and tells the Deployment to create more pods (up to our max of 5).
5. Kubernetes routes incoming traffic across all 5 pods.
6. When the load test stops, CPU drops, and HPA scales back down to 1 pod.

---

## Prometheus & Grafana

### WHAT
- **Prometheus** is a time-series database and monitoring system. It "scrapes" metrics from your applications periodically.
- **Grafana** is a visualization tool that queries Prometheus and draws beautiful dashboards.

### WHY
You can't fix what you can't see. When traffic spikes or errors occur, you need to know immediately.

### HOW IT WORKS
1. **Application Code**: We added the `prometheus_client` library to our Flask apps.
2. **Metrics Endpoint**: Each app exposes `/metrics` with raw data.
3. **Annotations**: We added `prometheus.io/scrape: "true"` to our Kubernetes Deployments.
4. **Auto-Discovery**: Prometheus uses the Kubernetes API to find any pods with those annotations and starts scraping them automatically.
5. **Grafana Dashboards**: We configured Grafana to query Prometheus and visualize:
   - Total/Successful/Failed Bookings (Business Metrics)
   - HTTP Request Duration P99 (Performance Metrics)
   - HPA Replicas (Infrastructure Metrics, using `kube_deployment_status_replicas_available`)

---

## AWS & Terraform

### WHAT
- **AWS (Amazon Web Services)** is our cloud provider.
- **Terraform** is an Infrastructure as Code (IaC) tool. It uses declarative configuration files to create and manage cloud resources.

### WHY Terraform
Instead of clicking through the AWS console to create a VPC, subnets, and an EKS cluster (which is error-prone and hard to reproduce), we write code. If we need to tear down the environment to save costs, we just run `terraform destroy`. To bring it back, `terraform apply`.

### Infrastructure Components
- **VPC (Virtual Private Cloud)**: Our private network in AWS.
- **Subnets**: We use 3 public and 3 private subnets across 3 Availability Zones for high availability.
- **NAT Gateway**: Allows pods in private subnets to reach the internet (e.g., to pull Docker images or call external APIs) without being exposed to incoming traffic.
- **EKS (Elastic Kubernetes Service)**: AWS's managed Kubernetes service. AWS manages the control plane (the master nodes), and we manage the worker nodes.
- **EBS CSI Driver**: Needed so Kubernetes can provision actual AWS EBS volumes when we ask for a `PersistentVolumeClaim` (used by our PostgreSQL StatefulSet).

### The EKS PostgreSQL Decision
As noted in the prompt's `Correction #2`, we are deploying PostgreSQL as a StatefulSet inside EKS using an EBS volume, rather than using AWS RDS.
- **Why?** It's significantly cheaper for an academic project, while still demonstrating persistent state management in Kubernetes. Production systems typically use managed databases like RDS.

---

## AWS Lambda & Async Architecture

### WHAT
AWS Lambda is a serverless compute service. It runs code in response to events without provisioning servers.

### WHY
In Phase 16, we configured the Booking Service to trigger a webhook when a booking is confirmed. If this was a synchronous (blocking) call, our Booking Service would have to wait for the webhook to finish before telling the user "Success!". If the webhook server crashed, the booking might fail even though it was already saved in PostgreSQL.

### HOW (Fire-and-Forget)
We use a background thread (`threading.Thread`) in the Flask app to make the HTTP POST request to the Lambda webhook URL. If the webhook fails or times out, we catch the exception and log it, but the main thread has already returned a `201 Created` to the user. This enforces the hard rule: **Lambda failures must never roll back an already-successful booking.**

---

## CI/CD (GitHub Actions)

### WHAT
Continuous Integration / Continuous Deployment. Automates the testing and deployment of our code every time we push to GitHub.

### WHY
We don't want to manually run tests or manually build Docker images on our laptop. The CI pipeline guarantees that code is tested in a clean environment and images are built consistently.

### The Pipeline (`.github/workflows/ci.yml`)
1. **Test Job**:
   - Spins up a temporary PostgreSQL container (Service Container).
   - Initializes the database with our schema and seed data.
   - Starts all 3 Python microservices in the background.
   - Runs our full integration test suite, including the 200-request concurrency test.
2. **Build and Push Job**:
   - Only runs if tests pass and code is pushed to the `main` branch.
   - Authenticates to AWS securely using **GitHub OIDC** (no hardcoded passwords).
   - Uses `docker buildx` to build multi-architecture images (AMD64 and ARM64).
   - Pushes the images to AWS ECR.

---
**End of Learning Guide**
