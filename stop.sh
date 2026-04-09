#!/bin/bash

echo "🛑 Shutting down ADEO System..."

# Stop Services
docker-compose -f services/ui/docker-compose.yml down
docker-compose -f services/ingestion/docker-compose.yml down
docker-compose -f services/agent/docker-compose.yml down
docker-compose -f services/api_gateway/docker-compose.yml down

# Stop Infrastructure
docker-compose -f infra/neo4j/docker-compose.yml down
docker-compose -f infra/chromadb/docker-compose.yml down
docker-compose -f infra/redis/docker-compose.yml down
docker-compose -f infra/rabbitmq/docker-compose.yml down

echo "🧹 Cleaning up unused Docker resources..."
# Optional: docker network rm adeo_network

echo "💤 System stopped."