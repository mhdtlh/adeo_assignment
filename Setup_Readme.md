# 🚀 Getting Started

This section explains how to **set up the repository**, **start services**, **ingest documents**, and **query the system**.

---

# 📦 Repository Setup

## 1. Clone Repository

```bash
git clone https://github.com/mhdtlh/adeo_assignment.git
cd adeo_assignment
```

---

## 2. Configure Environment Variables

Create a `.env` file in the root directory:

```bash
GROQ_API_KEY=
TAVILY_API_KEY=
LLAMA_CLOUD_API_KEY=
NEO4J_URL=
NEO4J_USERNAME=
NEO4J_PASSWORD=
```

---

# 🐳 Start the System

## Option 1 — Using Startup Scripts (Recommended)

### Linux / Mac

```bash
./start.sh
```

### Windows

```powershell
./start.ps1
```

This will:

* Build base Docker image
* Start infrastructure containers
* Start all services
* It will take take about 25 mins for all the containers to build and get up running

---

# 🛠 Manual Setup (Optional)

## 1. Create Docker Network

```bash
docker network create adeo_network
```

## 2. Build Base Docker Image

```bash
docker build -t adeo-base -f Dockerfile.base .
```

## 3. Start Infrastructure

```bash
docker-compose -f infra/rabbitmq/docker-compose.yml up -d

docker-compose -f infra/redis/docker-compose.yml up -d

docker-compose -f infra/chromadb/docker-compose.yml up -d

docker-compose -f infra/neo4j/docker-compose.yml up -d
```

## 4. Start Services

```bash
docker-compose -f services/api_gateway/docker-compose.yml up -d

docker-compose -f services/agent/docker-compose.yml up -d

docker-compose -f services/ingestion/docker-compose.yml up -d

docker-compose -f services/evaluation/docker-compose.yml up -d

docker-compose -f services/ui/docker-compose.yml up -d
```

---

# 📥 Start Ingestion

## Upload Documents

Use the UI or API:

```
POST /upload
```

---

## Trigger Ingestion

```
POST /ingest
```

This will:

* Parse documents
* Generate embeddings
* Store in ChromaDB
* Build Knowledge Graph

---

# 🖥️ Start UI

Once services are running, open:

```
http://localhost:8501
```

From the UI you can:

* Upload documents
* Trigger ingestion
* Query system

---

# 🔍 Query the System

## From UI

1. Open UI
2. Enter query
3. Submit
4. View response

---

## From API

### Submit Query

```
POST /query
```

---

### Get Result

```
GET /result/{request_id}
```

---

# 🔌 API Usage with cURL

This section provides **cURL commands** for interacting with the system.

---

# 📥 Upload Documents

Upload documents to ingestion service:

```bash
curl -X POST http://localhost:8002/upload \
  -F "file=@sample.pdf"
```

---

# 🚀 Trigger Ingestion

```bash
curl -X POST http://localhost:8002/ingest
```

---

# 🔍 Query the System

Submit query:

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{
        "query": "What is the document about?"
      }'
```

---

# 📊 Get Query Result

```bash
curl http://localhost:8001/result/<request_id>
```

---

# 🩺 Health Check — Ingestion Service

```bash
curl http://localhost:8002/health
```

---

# 🩺 Health Check — API Gateway

```bash
curl http://localhost:8001/health
```

---

# 🩺 Health Check — Agent Service

Agent service typically runs as a worker, but if health endpoint is exposed:

```bash
curl http://localhost:8004/health
```

---

# 🐳 Docker Container Status

Check running containers:

```bash
docker ps
```

---

# 📊 Check Logs

## Ingestion Logs

```bash
docker logs -f adeo_ingestion
```

---

## API Gateway Logs

```bash
docker logs -f adeo_api_gateway
```

---

## Agent Logs

```bash
docker logs -f adeo_agent
```

---

# 🔄 End-to-End Flow

```mermaid
sequenceDiagram
    autonumber

    User->>Upload API: Upload file
    Upload API->>Ingestion: Process

    User->>API Gateway: Query
    API Gateway->>Agent: Process

    Agent->>Databases: Retrieve
    Agent->>API Gateway: Response

    API Gateway->>User: Result
```

---

# 🌐 Service URLs

| Service     | URL                                              |
| ----------- | ------------------------------------------------ |
| UI          | [http://localhost:8501](http://localhost:8501)   |
| API Gateway | [http://localhost:8001](http://localhost:8001)   |
| Ingestion   | [http://localhost:8002](http://localhost:8002)   |
| Evaluation  | [http://localhost:8003](http://localhost:8003)   |
| Neo4j       | [http://localhost:7474](http://localhost:7474)   |
| RabbitMQ    | [http://localhost:15672](http://localhost:15672) |

---

# 🧹 Reset / Delete Database Data

This section explains how to **reset the system** by deleting database data.

This is useful when:

* Re-running ingestion
* Testing new documents
* Clearing corrupted data
* Resetting environment

---

# Option 1 — Using Script (Recommended)

Use the provided script:

### Linux / Mac

```bash
./remove_data.sh
```

### Windows

```powershell
./remove_data.ps1
```

This script will:

* Stop containers
* Remove containers
* Delete database data
* Clear ingestion cache

---

# Option 2 — Manual Reset

## Stop Containers

```bash
docker stop adeo_neo4j
docker rm adeo_neo4j

docker stop adeo_chromadb
docker rm adeo_chromadb
```

---

## Delete Database Data

```bash
sudo rm -rf infra/neo4j/neo4j_data
sudo rm -rf infra/chromadb/chroma_data
```

---

## Clear Ingestion Cache

```bash
rm services/ingestion/ingestion_cache.json
```

---

# ⚠️ Warning

This will permanently delete:

* Vector database (ChromaDB)
* Graph database (Neo4j)
* Ingestion cache

This reset is needed when you want to upload data again from scratch
---

