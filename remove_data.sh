docker stop adeo_neo4j
docker rm adeo_neo4j
docker stop adeo_chromadb
docker rm adeo_chromadb
sudo rm -rf infra/neo4j/neo4j_data
sudo rm -rf infra/chromadb/chroma_data
rm services/ingestion/ingestion_cache.json