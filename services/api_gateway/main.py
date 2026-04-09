import uuid
import json
import pika
import logging
import os
import redis
from fastapi import FastAPI, HTTPException, Body
from typing import Optional, List, Dict
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="ADEO API Gateway")

# --- NEW: Create logs directory and configure file logging ---
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(), # Keeps logs flowing to Docker stdout
        logging.FileHandler(os.path.join(log_dir, "gateway.log")) # Saves to file
    ]
)
logger = logging.getLogger("ADEO.Gateway")
# -------------------------------------------------------------

# Initialize Redis Client (Gateway is the only one talking to Redis now)
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "adeo_redis"), 
    port=6379, 
    db=0, 
    decode_responses=True
)

class QueryRequest(BaseModel):
    query: str
    history: Optional[List[Dict[str, str]]] = []

class Citation(BaseModel):
    file_name: str
    page_label: str
    score: Optional[float] = None

class ResultPayload(BaseModel):
    status: str
    answer: Optional[str] = ""
    citations: Optional[List[Citation]] = []
    message: Optional[str] = ""

def get_rabbitmq_connection():
    params = pika.ConnectionParameters(host=os.getenv("RABBITMQ_HOST", "adeo_rabbitmq"), heartbeat=600)
    return pika.BlockingConnection(params)

@app.post("/query")
async def create_query(request: QueryRequest):
    request_id = str(uuid.uuid4())
    logger.info(f"Received query request: {request_id}")
    
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        channel.queue_declare(queue='query_tasks', durable=True)
        
        message = {
            "request_id": request_id,
            "query": request.query,
            "history": request.history
        }
        
        channel.basic_publish(
            exchange='',
            routing_key='query_tasks',
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()
        
        # Set initial status in Redis
        redis_client.set(request_id, json.dumps({"status": "processing"}), ex=3600)
        
        return {"request_id": request_id, "status": "queued"}
    except Exception as e:
        logger.error(f"Failed to queue request: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal message broker error")

# --- NEW: Internal Webhook Endpoint for the Agent ---
@app.post("/internal/result/{request_id}")
async def receive_agent_result(request_id: str, payload: ResultPayload):
    logger.info(f"Received result callback for {request_id}")
    # Gateway writes the agent's result into Redis
    redis_client.set(request_id, payload.json(), ex=3600)
    return {"status": "success", "message": "Result stored successfully"}

# --- Existing Polling Endpoint for the UI ---
@app.get("/result/{request_id}")
async def get_result(request_id: str):
    data = redis_client.get(request_id)
    if data:
        return json.loads(data)
    raise HTTPException(status_code=404, detail="Result not found or expired")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "api_gateway"}