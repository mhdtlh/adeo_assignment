Write-Host "🚀 Starting ADEO Hybrid RAG System..." -ForegroundColor Cyan

# 1. Create network if it doesn't exist
$networkExists = docker network ls -q -f name="^adeo_network$"
if (-not $networkExists) {
    Write-Host "Creating adeo_network..."
    docker network create adeo_network
}

# 2. Build the lightning-fast base image (No PyTorch!)
Write-Host "📦 Building base image..." -ForegroundColor Yellow
docker build --progress=plain -t adeo-base:latest -f Dockerfile.base .

# 3. Start Infrastructure
Write-Host "🛠️  Starting Infrastructure (Databases & Messaging)..." -ForegroundColor Yellow
docker-compose -f infra/rabbitmq/docker-compose.yml up -d
docker-compose -f infra/redis/docker-compose.yml up -d
docker-compose -f infra/chromadb/docker-compose.yml up -d
docker-compose -f infra/neo4j/docker-compose.yml up -d

# 4. Critical Wait for Neo4j
# As we saw, Neo4j needs time to initialize its Bolt protocol.
Write-Host "⏳ Waiting 2 seconds for Neo4j to warm up..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

# 5. Start Microservices
Write-Host "🤖 Starting Microservices..." -ForegroundColor Yellow
docker-compose -f services/api_gateway/docker-compose.yml up -d --build
docker-compose -f services/agent/docker-compose.yml up -d --build
docker-compose -f services/ingestion/docker-compose.yml up -d --build
docker-compose -f services/ui/docker-compose.yml up -d --build

Write-Host "✅ All systems are GO!" -ForegroundColor Green
Write-Host "👉 UI: http://localhost:8501" -ForegroundColor Cyan
Write-Host "👉 API Gateway: http://localhost:8001" -ForegroundColor Cyan