import os
import logging
from llama_index.vector_stores.chroma import ChromaVectorStore
# Use the newer PropertyGraphStore for Neo4j
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
import chromadb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ADEO.DBManager")

def get_vector_store():
    """Returns a ChromaVectorStore connected via HttpClient"""
    chroma_host = os.getenv("CHROMA_HOST", "adeo_chromadb")
    chroma_port = int(os.getenv("CHROMA_PORT", 8000))
    
    logger.info(f"Connecting to Chroma at {chroma_host}:{chroma_port}")
    remote_db = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    chroma_collection = remote_db.get_or_create_collection("adeo_collection")
    
    return ChromaVectorStore(chroma_collection=chroma_collection)

def get_graph_store():
    """Returns a Neo4jPropertyGraphStore with environment-based config"""
    url = os.getenv("NEO4J_URL", "bolt://adeo_neo4j:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD")
    db_name = os.getenv("NEO4J_DATABASE", "neo4j")

    # DEBUG LOGGING: This will tell us if the password is empty
    if not pwd:
        logger.error("!!! NEO4J_PASSWORD is empty in the environment !!!")
    else:
        logger.info(f"Connecting to Neo4j at {url} as user '{user}'")

    return Neo4jPropertyGraphStore(
        username=user,
        password=pwd,
        url=url,
        database=db_name
    )