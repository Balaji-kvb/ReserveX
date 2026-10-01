# ReserveX — Cloud-Native High-Concurrency Reservation and Booking Platform

ReserveX is a cloud-native, microservices-based reservation platform designed to demonstrate **safe high-concurrency booking**, **containerized deployment**, **Kubernetes orchestration**, **automatic scaling**, and **application monitoring** on AWS.

The project models a limited-inventory reservation problem: when many users try to book the same event at nearly the same time, the system must prevent overselling and return a clear response when capacity is exhausted.

---

## 📌 Problem Statement

Traditional booking systems can encounter race conditions when many users attempt to reserve the last few available slots simultaneously.

ReserveX addresses this problem by:

- separating responsibilities into independent microservices;
- keeping event inventory ownership inside the **Event Service**;
- using an **atomic database update** to decrement available slots only when capacity exists;
- coordinating booking creation from the **Booking Service**;
- using Kubernetes **Horizontal Pod Autoscaler (HPA)** for CPU-based scaling;
- exposing Prometheus metrics and visualizing them with Grafana; and
- validating concurrency behavior with **k6**.

---

## 🎯 Objectives

1. Build a modular microservices-based reservation system.
2. Prevent overselling under concurrent booking requests.
3. Containerize the services and deploy them on AWS EKS.
4. Use PostgreSQL for persistent application data.
5. Use Kubernetes persistent storage backed by AWS EBS.
6. Implement CPU-based horizontal autoscaling.
7. Collect application metrics with Prometheus.
8. Visualize operational metrics with Grafana.
9. Perform reproducible high-concurrency testing with k6.
10. Provision AWS infrastructure and supporting Kubernetes components with Terraform.

---

## 🏗️ Architecture

```text
                           Client / Load-Test Traffic
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │    Booking Service   │
                           │       Flask :5003    │
                           └──────────┬───────────┘
                                      │
                     ┌────────────────┴────────────────┐
                     │                                 │
                     ▼                                 ▼
           ┌─────────────────┐               ┌─────────────────┐
           │   User Service  │               │  Event Service  │
           │   Flask :5001   │               │  Flask :5002    │
           └─────────────────┘               └────────┬────────┘
                                                       │
                                                       ▼
                                             ┌──────────────────┐
                                             │   PostgreSQL     │
                                             │   + EBS-backed   │
                                             │      PVC         │
                                             └──────────────────┘

                    Application Monitoring

          Service /metrics
                 │
                 ▼
          ┌───────────────┐
          │  Prometheus   │
          └───────┬───────┘
                  │
                  ▼
          ┌───────────────┐
          │    Grafana    │
          └───────────────┘

                    Autoscaling

          CPU utilization > target
                  │
                  ▼
          ┌───────────────┐
          │      HPA      │
          └───────┬───────┘
                  │
                  ▼
      Booking Service replicas increase
```

### Kubernetes placement

The workloads run in an AWS **EKS** cluster. The current cluster uses two worker nodes, with application and monitoring pods distributed across the nodes.

---

## 🧩 Microservices

| Service | Port | Responsibility | Kubernetes Service Type |
|---|---:|---|---|
| User Service | 5001 | Create and retrieve users | ClusterIP |
| Event Service | 5002 | Create events, check inventory, reserve/release slots | ClusterIP |
| Booking Service | 5003 | Orchestrate booking workflow and persist bookings | LoadBalancer |
| PostgreSQL | 5432 | Persistent relational data | Headless/ClusterIP |

### User Service

Main responsibilities:

- create users;
- retrieve users by ID;
- provide user validation for booking requests.

Example endpoints:

```text
POST /users
GET  /users/<user_id>
```

### Event Service

Main responsibilities:

- create events;
- expose availability;
- reserve a slot;
- release a previously reserved slot when compensation is required.

Example endpoints:

```text
POST /events
GET  /events/<event_id>
GET  /events/<event_id>/availability
POST /events/<event_id>/reserve
POST /events/<event_id>/release
```

### Booking Service

Main responsibilities:

- validate booking input;
- validate the user through User Service;
- request inventory reservation from Event Service;
- create the booking record in PostgreSQL;
- compensate by releasing the event slot if booking persistence fails;
- expose application metrics.

Example endpoints:

```text
POST /bookings
GET  /bookings/<booking_id>
POST /bookings/<booking_id>/cancel
GET  /health
GET  /metrics
```

---

## 🔄 Booking Workflow

A booking request follows this sequence:

```text
1. Client sends POST /bookings
             │
             ▼
2. Booking Service validates request
             │
             ▼
3. Booking Service validates user
   through User Service
             │
             ▼
4. Booking Service asks Event Service
   to reserve a slot
             │
             ▼
5. Event Service performs an atomic
   inventory update
             │
       ┌─────┴─────┐
       │           │
     slot       sold out
   available        │
       │            ▼
       │           409
       ▼
6. Booking Service inserts booking
   into PostgreSQL
       │
       ├── success → 201
       │
       └── DB failure → release slot
                         through Event Service
```

This is a **compensating transaction pattern**, not a distributed XA transaction.

---

## 🔒 Preventing Overselling

The Event Service owns the event inventory.

The reservation operation uses an atomic database statement conceptually equivalent to:

```sql
UPDATE events
SET available_slots = available_slots - 1
WHERE id = %s
  AND available_slots > 0
RETURNING id, available_slots;
```

### Why this matters

The condition:

```sql
available_slots > 0
```

is evaluated as part of the same update operation that decrements the count.

Therefore, concurrent requests cannot successfully decrement the inventory below zero through this operation.

When no row is returned, the Event Service responds with a **409 Conflict** indicating that no slot is available.

---

## 🧪 Concurrency Test with k6

The project includes:

```text
load-testing/concurrency-test.js
```

The test creates:

- **1 event** with exactly **50 slots**;
- **200 test users**;
- **200 virtual users (VUs)**;
- **1 booking attempt per VU**.

Expected result:

```text
200 booking attempts
50 successful bookings
150 sold-out responses
0 unexpected responses
```

### Verified result

The in-cluster test produced the expected business outcome:

```text
booking_attempts = 200
booking_successes = 50
booking_sold_out = 150
booking_unexpected = 0
```

The test was executed from inside the Kubernetes environment so traffic reached the Booking Service through cluster networking instead of relying on a local `kubectl port-forward` as the load-test path.

Representative observed performance from the successful in-cluster run:

```text
Average HTTP request duration ≈ 1.04 s
P95 HTTP request duration     ≈ 1.96 s
Throughput                     ≈ 91.7 req/s
```

> Note: k6's generic `http_req_failed` rate counts non-2xx responses as failed HTTP requests. ReserveX intentionally returns **409** for expected sold-out requests, so the project's custom k6 counters/thresholds are the authoritative business-result checks for this experiment.

---

## 🐳 Containerization and Amazon ECR

The three application services are containerized and stored in Amazon ECR.

Images currently referenced by Kubernetes:

```text
667747481883.dkr.ecr.ap-south-1.amazonaws.com/reservex-user-service:v1
667747481883.dkr.ecr.ap-south-1.amazonaws.com/reservex-event-service:v1
667747481883.dkr.ecr.ap-south-1.amazonaws.com/reservex-booking-service:v1
```

Kubernetes uses:

```yaml
imagePullPolicy: IfNotPresent
```

This allows EKS nodes to use an already-pulled image while still supporting normal ECR image retrieval.

---

## ☸️ Kubernetes / Amazon EKS

The application is deployed into the Kubernetes namespace:

```text
reservex
```

The cluster includes:

- Amazon EKS;
- EKS managed worker nodes;
- Kubernetes Deployments and Services;
- StatefulSet for PostgreSQL;
- PersistentVolumeClaim for PostgreSQL;
- HPA for Booking Service;
- Metrics Server;
- Prometheus and Grafana;
- AWS Load Balancer Controller configuration.

### Current core workload state

The final verified cluster snapshot showed:

- `reservex` namespace: **Active**;
- application and monitoring pods: **Running**;
- two EKS worker nodes: **Ready**;
- PostgreSQL PVC: **Bound**;
- HPA: **1–5 replicas**, CPU target **60%**;
- Prometheus and Grafana: **Running**.

---

## 📈 Horizontal Pod Autoscaler (HPA)

The Booking Service is configured with an HPA using CPU utilization.

Configuration:

```text
Minimum replicas: 1
Maximum replicas: 5
CPU target: 60%
```

### Verified scaling experiment

A temporary in-cluster load generator was used to create CPU pressure on the Booking Service.

Observed scaling:

```text
1 replica
   ↓
4 replicas
   ↓
5 replicas
```

Kubernetes reported rescaling events because CPU utilization exceeded the configured target.

After the load was removed, the HPA later scaled the deployment back down according to the normal stabilization/scale-down behavior.

---

## 💾 PostgreSQL and Persistent Storage

PostgreSQL is deployed as a Kubernetes StatefulSet.

The database stores application entities such as:

```text
users

events

bookings
```

PostgreSQL uses a persistent volume claim backed by AWS EBS through the CSI driver.

Storage configuration includes:

```text
StorageClass: ebs-sc
Capacity:      1Gi
Access mode:   RWO
```

### PostgreSQL data-directory fix

The database volume initially exposed the common filesystem `lost+found` directory at the mounted path. PostgreSQL rejected the root data directory because it was not an empty directory.

The deployment was corrected with:

```yaml
env:
  - name: PGDATA
    value: /var/lib/postgresql/data/pgdata
```

PostgreSQL then initialized successfully inside the dedicated subdirectory while retaining the persistent mount.

---

## 📊 Prometheus Monitoring

Prometheus scrapes Kubernetes pods based on Prometheus annotations.

The application exposes metrics including:

```text
http_requests_total
http_request_duration_seconds
booking_requests_total
successful_bookings_total
failed_bookings_total
```

Example scrape annotations used by application deployments:

```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "5003"
prometheus.io/path: "/metrics"
```

Prometheus is deployed inside the `reservex` namespace and uses Kubernetes RBAC permissions for pod discovery.

---

## 📉 Grafana Dashboard

Grafana is provisioned with a Prometheus datasource and a ReserveX dashboard.

Dashboard panels include:

- Total Booking Requests
- Successful Bookings
- Failed Bookings
- HTTP Request Duration (P99)
- Booking Service Replicas / HPA visibility
- Request Rate by Endpoint

The dashboard is provisioned from Kubernetes ConfigMaps rather than manually rebuilding the dashboard after every deployment.

---

## 🌐 AWS Load Balancer Controller

ReserveX includes Terraform configuration for the AWS Load Balancer Controller using:

- IAM policy;
- IAM role;
- EKS OIDC / web identity trust;
- Kubernetes ServiceAccount;
- Helm release.

The Booking Service is configured as:

```yaml
spec:
  type: LoadBalancer
```

with AWS load-balancer annotations for an internet-facing NLB and HTTP health checking on:

```text
/health
```

### Known AWS limitation

During validation, the AWS account returned an account-level restriction when AWS attempted to create the load balancer:

```text
OperationNotPermitted:
This AWS account currently does not support creating load balancers.
```

Therefore, the AWS Load Balancer Controller configuration is part of the project and deployed, but an external NLB could not be provisioned in the current account.

The application's internal Kubernetes networking, port-forwarding, concurrency test, autoscaling, and monitoring were used to validate the system without depending on the unavailable external NLB.

---

## 🏗️ Infrastructure as Code with Terraform

Terraform is used to define AWS infrastructure and supporting providers/resources.

The project includes configuration for components such as:

- VPC and networking;
- EKS cluster;
- managed node groups;
- ECR repositories;
- Lambda notification function;
- Elastic Beanstalk resources;
- EBS CSI integration;
- Metrics Server;
- Kubernetes provider;
- Helm provider;
- AWS Load Balancer Controller resources.

Terraform validation was performed successfully with:

```bash
terraform fmt -check
terraform validate
```

---

## 📁 Project Structure

```text
ReserveX/
├── kubernetes/
│   ├── booking-service/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── hpa.yaml
│   ├── event-service/
│   │   └── deployment.yaml
│   ├── user-service/
│   │   └── deployment.yaml
│   ├── config/
│   │   └── configmap.yaml
│   ├── monitoring/
│   │   ├── prometheus.yaml
│   │   └── grafana.yaml
│   └── postgres.yaml
│
├── load-testing/
│   └── concurrency-test.js
│
├── terraform/
│   ├── eks.tf
│   ├── providers.tf
│   ├── lbc.tf
│   └── lbc-iam-policy.json
│
└── README.md
```

> The repository contains additional application/source and Terraform files beyond the condensed structure shown above.

---

## 🚀 Deployment Overview

### 1. Configure AWS authentication

Use an AWS profile that has permission to access the EKS cluster and related AWS resources.

### 2. Initialize and validate Terraform

```bash
cd terraform
terraform init
terraform fmt
terraform validate
terraform plan
```

### 3. Provision / update infrastructure

```bash
terraform apply
```

### 4. Configure kubectl for the EKS cluster

```bash
aws eks update-kubeconfig \
  --region ap-south-1 \
  --name <cluster-name>
```

### 5. Apply Kubernetes resources

Example deployment sequence:

```bash
kubectl apply -f kubernetes/config/configmap.yaml
kubectl apply -f kubernetes/postgres.yaml
kubectl apply -f kubernetes/user-service/
kubectl apply -f kubernetes/event-service/
kubectl apply -f kubernetes/booking-service/
kubectl apply -f kubernetes/monitoring/prometheus.yaml
kubectl apply -f kubernetes/monitoring/grafana.yaml
```

### 6. Verify workloads

```bash
kubectl get pods -n reservex
kubectl get svc -n reservex
kubectl get pvc -n reservex
kubectl get hpa -n reservex
```

### 7. Verify resource metrics

```bash
kubectl top nodes
kubectl top pods -n reservex
```

### 8. Access Prometheus locally

```bash
kubectl port-forward -n reservex svc/prometheus 9090:9090
```

Open:

```text
http://127.0.0.1:9090
```

### 9. Access Grafana locally

```bash
kubectl port-forward -n reservex svc/grafana 3000:3000
```

Open:

```text
http://127.0.0.1:3000
```

### 10. Run the k6 concurrency test

The test can be executed against the appropriate service URLs depending on the environment. For the validated EKS run, the test traffic was placed inside the Kubernetes network so it could access:

```text
http://booking-service:5003
http://user-service:5001
http://event-service:5002
```

---

## 🧪 Functional Test Cases

### Health check

```text
GET /health
```

Expected result:

```text
HTTP 200
```

### Successful booking

```text
POST /bookings
```

Expected result for available inventory:

```text
HTTP 201
```

### Sold-out booking

When event inventory reaches zero:

```text
HTTP 409
```

with an error indicating that no slots are available.

### Concurrency correctness

For a 50-slot event receiving 200 concurrent booking attempts:

```text
Expected: 50 success + 150 sold out
Observed: 50 success + 150 sold out
```

---

## 🔐 Configuration and Secrets

Sensitive values such as the PostgreSQL password are stored in Kubernetes Secrets and are **not committed as plaintext credentials** to the repository.

Repository manifests should contain references to Kubernetes Secrets, not the actual secret value.

Example pattern:

```yaml
valueFrom:
  secretKeyRef:
    name: reservex-db-secret
    key: POSTGRES_PASSWORD
```

---

## 🔍 Observability Flow

```text
Application request
       │
       ├── booking logic
       │
       └── Prometheus instrumentation
                 │
                 ▼
              /metrics
                 │
                 ▼
             Prometheus
                 │
                 ▼
              Grafana
```

Useful PromQL examples:

```promql
sum(booking_requests_total)
```

```promql
sum(successful_bookings_total)
```

```promql
sum(failed_bookings_total)
```

```promql
sum(rate(http_requests_total[5m])) by (endpoint, method, status)
```

```promql
histogram_quantile(
  0.99,
  sum(rate(http_request_duration_seconds_bucket[5m]))
  by (le, endpoint)
)
```

---

## ⚙️ Failure Handling

### Event service reports no inventory

The Booking Service returns the sold-out response instead of creating a booking.

### Booking database insert fails after inventory reservation

The Booking Service attempts a compensating release through:

```text
POST /events/<event_id>/release
```

This avoids leaving an inventory slot permanently consumed by a booking that was never persisted.

### PostgreSQL pod restarts

The database uses persistent storage, so data is stored on the EBS-backed PVC rather than only in the container filesystem.

### High Booking Service CPU

The HPA increases the number of Booking Service replicas, up to the configured maximum.

### External AWS Load Balancer cannot be created

The current AWS account returned an account-level restriction. Internal Kubernetes networking remains available for application testing and validation.

---

## 📌 Important Design Decisions

### Why microservices?

To separate user management, inventory ownership, and booking orchestration so each responsibility can evolve and scale independently.

### Why does Event Service own inventory?

The component that owns the inventory is the natural place to enforce the atomic reservation operation and prevent overselling.

### Why PostgreSQL?

The project requires durable relational data for users, events, and bookings, including transactional updates and persistent storage.

### Why Kubernetes?

Kubernetes provides service discovery, deployment management, health management, scaling, and workload orchestration.

### Why EKS?

It provides managed Kubernetes control-plane capabilities on AWS while allowing the project to demonstrate real cloud infrastructure.

### Why HPA?

To automatically adjust Booking Service capacity according to CPU demand instead of relying on manual replica changes.

### Why Prometheus + Grafana?

Prometheus collects time-series metrics and Grafana turns those metrics into dashboards that are useful for operational monitoring.

### Why k6?

k6 provides reproducible load/concurrency experiments and custom counters/thresholds for validating the business behavior of the booking system.

---

## ✅ Verified Outcomes

```text
Microservices                              ✅
PostgreSQL persistence                     ✅
EBS-backed PVC                             ✅
ECR images on EKS                          ✅
Metrics Server                             ✅
HPA configuration                          ✅
HPA scaling experiment 1 → 4 → 5         ✅
Prometheus scraping                        ✅
Grafana dashboard                          ✅
200-user concurrency experiment            ✅
50 successful / 150 sold-out               ✅
0 unexpected booking responses             ✅
Terraform validation                       ✅
Git repository synchronized                ✅
AWS Load Balancer Controller configured     ✅
External AWS NLB provisioning              ⚠️ Account restriction
```

---

## 🚧 Known Limitations

1. The current AWS account does not permit creation of the requested external load balancer, so the Booking Service's `LoadBalancer` Service remains without an external address.
2. PostgreSQL is currently a single database instance rather than a highly available PostgreSQL cluster.
3. The compensation mechanism is application-level rather than a distributed transaction coordinator.
4. The monitoring stack is intentionally lightweight and can be extended with persistent Prometheus storage and richer Kubernetes state metrics.

---

## 🔮 Future Improvements

- Use a managed PostgreSQL service such as Amazon RDS/Aurora for production-grade database availability.
- Add Redis or another distributed coordination mechanism where appropriate for broader rate-limiting/caching use cases.
- Add authentication and authorization with JWT/OAuth2.
- Add centralized logging using CloudWatch, OpenSearch, or an equivalent stack.
- Add distributed tracing with OpenTelemetry.
- Add service-level latency/error-rate SLOs and alerting.
- Add CI/CD workflows for image build, test, ECR push, and Kubernetes deployment.
- Add Kubernetes NetworkPolicies and stronger pod security controls.
- Persist Prometheus data on durable storage for longer-term analysis.
- Add more comprehensive integration and failure-injection testing.

---

## 🎓 Viva Focus Areas

Be prepared to explain each component using five questions:

### WHAT?
What is the technology or component?

### WHY?
Why was it selected for ReserveX?

### HOW?
How does it work in this implementation?

### WHERE?
Which Kubernetes manifest, Terraform file, service, endpoint, or directory implements it?

### WHAT IF IT FAILS?
What happens when the dependency, pod, database, or network path fails?

Recommended viva topics:

```text
Microservices
REST APIs
Flask
PostgreSQL
Atomic SQL updates
Race conditions
Compensating transactions
Docker
Amazon ECR
Kubernetes Deployments
StatefulSets
Services / ClusterIP / LoadBalancer
EKS
EBS CSI
PersistentVolumeClaims
HPA
Metrics Server
Prometheus
Grafana
k6
Terraform
Helm
IAM
OIDC / IRSA
AWS Load Balancer Controller
Health checks
Service discovery
Monitoring and observability
```

---

## 📦 Repository

GitHub:

https://github.com/Balaji-kvb/ReserveX

The finalized project state was committed to `main` as:

```text
8fb6968 feat: finalize EKS deployment monitoring and load testing
```

---

## 👨‍💻 Project

**ReserveX — Cloud-Native High-Concurrency Reservation and Booking Platform**

Built to demonstrate practical cloud-native engineering concepts including microservices, containerization, Kubernetes orchestration, AWS infrastructure, concurrency safety, autoscaling, monitoring, and load testing.
