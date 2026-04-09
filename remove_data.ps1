Write-Host "🗑️ Removing ADEO databases and cache..." -ForegroundColor Yellow

Write-Host "Stopping and removing database containers..." -ForegroundColor Cyan
# Suppress errors if the containers are already stopped or removed
docker stop adeo_neo4j 2>$null
docker rm adeo_neo4j 2>$null
docker stop adeo_chromadb 2>$null
docker rm adeo_chromadb 2>$null

Write-Host "Wiping persistent volumes and cache files..." -ForegroundColor Cyan
# Force remove directories and their contents
Remove-Item -Path "infra\neo4j\neo4j_data" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "infra\chromadb\chroma_data" -Recurse -Force -ErrorAction SilentlyContinue

# Remove the ingestion cache file
Remove-Item -Path "services\ingestion\ingestion_cache.json" -Force -ErrorAction SilentlyContinue

Write-Host "✅ Data successfully removed! You are ready for a clean ingestion." -ForegroundColor Green