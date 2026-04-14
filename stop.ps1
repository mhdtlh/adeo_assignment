Write-Host "🛑 Shutting down ADEO System..." -ForegroundColor Red

# Stop Services
docker-compose -f services/ui/docker-compose.yml down
docker-compose -f services/ingestion/docker-compose.yml down
docker-compose -f services/agent/docker-compose.yml down
docker-compose -f services/api_gateway/docker-compose.yml down
docker-compose -f services/evaluation/docker-compose.yml down

# Stop Infrastructure
docker-compose -f infra/neo4j/docker-compose.yml down
docker-compose -f infra/chromadb/docker-compose.yml down
docker-compose -f infra/redis/docker-compose.yml down
docker-compose -f infra/rabbitmq/docker-compose.yml down

Write-Host "🧹 Cleaning up unused Docker resources..." -ForegroundColor Yellow
# Optional: docker network rm adeo_network

Write-Host "💤 System stopped." -ForegroundColor DarkGray