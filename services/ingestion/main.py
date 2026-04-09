import os
import json
import logging
import hashlib
import shutil
from fastapi import FastAPI, BackgroundTasks, UploadFile, File
from llama_parse import LlamaParse
from llama_index.core import (
    StorageContext, 
    PropertyGraphIndex,
    VectorStoreIndex,
    Settings,
    Document
)
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.groq import Groq

# Import the shared database utility
from services.shared_utils.db_manager import get_vector_store, get_graph_store

app = FastAPI(title="ADEO Ingestion Service")

# --- NEW: Create logs directory and configure file logging ---
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(), # Keeps logs flowing to Docker stdout
        logging.FileHandler(os.path.join(log_dir, "ingestion.log")) # Saves to file
    ]
)
logger = logging.getLogger("ADEO.Ingestion")
# -------------------------------------------------------------

INGESTION_CACHE_FILE = "/app/services/ingestion/ingestion_cache.json"

def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_cache():
    if os.path.exists(INGESTION_CACHE_FILE):
        with open(INGESTION_CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(INGESTION_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def run_ingestion_logic(input_dir="/app/source_docs"):
    if not os.path.exists(input_dir):
        logger.error(f"Directory '{input_dir}' not found!")
        return

    logger.info(f"--- Starting Smart Ingestion from '{input_dir}' ---")
    
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"

    # 1. Setup Global Settings (Stable HuggingFace + Groq)
    logger.info("Initializing Local Embedding Model (HuggingFace)...")
    Settings.embed_model = HuggingFaceEmbedding(
        # model_name="BAAI/bge-m3",
        model_name="intfloat/multilingual-e5-small",
        cache_folder="/app/hf_cache"
    )

    logger.info("Initializing LLM for Graph Extraction (Groq)...")
    Settings.llm = Groq(
        model="llama-3.3-70b-versatile", 
        api_key=os.getenv("GROQ_API_KEY")
    )

    # 2. Check for new or modified files
    cache = load_cache()
    files_in_dir = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
    
    new_files = []
    for filename in files_in_dir:
        file_path = os.path.join(input_dir, filename)
        current_hash = get_file_hash(file_path)
        
        if filename not in cache or cache[filename] != current_hash:
            new_files.append(file_path)
            cache[filename] = current_hash 
        else:
            logger.info(f"Skipping '{filename}' - already indexed and unchanged.")

    if not new_files:
        logger.info("No new/modified documents found. Ingestion skipped.")
        return

    # 3. Setup Database Connections using Shared Utils
    logger.info("Connecting to Microservice Databases...")
    vector_store = get_vector_store()
    graph_store = get_graph_store()

    # 4. Load, Parse, and Chunk 
    logger.info("Parsing files with LlamaParse...")
    parser = LlamaParse(result_type="markdown", api_key=os.getenv("LLAMA_CLOUD_API_KEY"), premium_mode = True)

    documents = []
    for file_path in new_files:
        logger.info(f"Processing {file_path}...")
        docs = parser.load_data(file_path)
        base_file_name = os.path.basename(file_path)
        
        if len(docs) == 1 and "\n---\n" in docs[0].text:
            pages = docs[0].text.split("\n---\n")
            for page_idx, page_text in enumerate(pages, start=1):
                new_doc = Document(
                    text=page_text.strip(),
                    metadata={**docs[0].metadata, "page_label": str(page_idx), "file_name": base_file_name}
                )
                documents.append(new_doc)
        else:
            for i, doc in enumerate(docs):
                p_num = doc.metadata.get('page') or doc.metadata.get('page_number') or (i+1)
                doc.metadata['page_label'] = str(p_num)
                doc.metadata['file_name'] = base_file_name
                documents.append(doc)

    node_parser = TokenTextSplitter(chunk_size=512, chunk_overlap=50)
    nodes = node_parser.get_nodes_from_documents(documents)

    # 5. Storage & Indexing
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    logger.info(f"Pushing {len(nodes)} nodes to ChromaDB...")
    VectorStoreIndex(nodes, storage_context=storage_context)
    
    logger.info("Extracting entities and pushing to Neo4j using Groq...")
    PropertyGraphIndex(nodes=nodes, property_graph_store=graph_store, show_progress=True)

    save_cache(cache)
    logger.info("--- Ingestion Sync Complete ---")

@app.post("/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks):
    logger.info("Ingestion triggered via API")
    background_tasks.add_task(run_ingestion_logic)
    return {"message": "Ingestion process started in background. Check Docker logs."}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Saves file to source_docs only if it doesn't already exist."""
    try:
        os.makedirs("/app/source_docs", exist_ok=True)
        file_location = f"/app/source_docs/{file.filename}"
        
        # --- DUPLICACY CHECK ---
        if os.path.exists(file_location):
            logger.warning(f"Upload blocked: {file.filename} already exists in repository.")
            return {
                "status": "duplicate", 
                "message": f"File '{file.filename}' already exists in the repository."
            }
        
        # Save the file
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
            
        logger.info(f"Successfully saved to repository: {file.filename}")
        return {"status": "success", "filename": file.filename}
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/health")
def health():
    return {"status": "ready"}