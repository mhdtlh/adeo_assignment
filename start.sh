#!/bin/bash

echo "🚀 Starting ADEO Hybrid RAG System..."

# 1. Create network if it doesn't exist
docker network inspect adeo_network >/dev/null 2>&1 || \
    docker network create adeo_network

# 2. Build the lightning-fast base image (No PyTorch!)
echo "📦 Building base image..."
docker build --progress=plain -t adeo-base:latest -f Dockerfile.base .

# 3. Start Infrastructure
echo "🛠️  Starting Infrastructure (Databases & Messaging)..."
docker-compose -f infra/rabbitmq/docker-compose.yml up -d
docker-compose -f infra/redis/docker-compose.yml up -d
docker-compose -f infra/chromadb/docker-compose.yml up -d
docker-compose -f infra/neo4j/docker-compose.yml up -d

# 4. Critical Wait for Neo4j
# As we saw, Neo4j needs time to initialize its Bolt protocol.
echo "⏳ Waiting 2 seconds for Neo4j to warm up..."
sleep 2

# 5. Start Microservices
echo "🤖 Starting Microservices..."
docker-compose -f services/api_gateway/docker-compose.yml up -d --build
docker-compose -f services/agent/docker-compose.yml up -d --build
docker-compose -f services/ingestion/docker-compose.yml up -d --build
docker-compose -f services/ui/docker-compose.yml up -d --build
docker-compose -f services/evaluation/docker-compose.yml up -d --build

echo "✅ All systems are GO!"
echo "👉 UI: http://localhost:8501"
echo "👉 API Gateway: http://localhost:8001"