import json
import pika
import logging
import os
import time
import requests
from llama_index.core import StorageContext, PropertyGraphIndex, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.groq import Groq
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.llms import ChatMessage, MessageRole

# Web Search Client
from tavily import TavilyClient

# Import the shared database utility
from services.shared_utils.db_manager import get_vector_store, get_graph_store

# --- NEW: Create logs directory and configure file logging ---
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(), # Keeps logs flowing to Docker stdout
        logging.FileHandler(os.path.join(log_dir, "agent.log")) # Saves to file
    ]
)

logger = logging.getLogger("ADEO.AgentWorker")

logging.getLogger("llama_index").setLevel(logging.DEBUG)  # Shows top-k retrieval
logging.getLogger("chromadb").setLevel(logging.INFO)      # ChromaDB connection status
logging.getLogger("neo4j").setLevel(logging.INFO)         # Neo4j cypher logs (Change to DEBUG for raw queries)
# -------------------------------------------------------------     # Neo4j cypher logs (Change to DEBUG for raw queries)

os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"
global_index = None

def initialize_index():
    global global_index
    if global_index is not None:
        return global_index

    logger.info("Initializing HuggingFace Embeddings and Groq LLM...")
    Settings.embed_model = HuggingFaceEmbedding(
        model_name="intfloat/multilingual-e5-small",
        cache_folder="/app/hf_cache"
    )
    
    Settings.llm = Groq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))

    logger.info("Connecting to Microservice Databases...")
    global_index = PropertyGraphIndex.from_existing(
        property_graph_store=get_graph_store(),
        vector_store=get_vector_store(),
    )
    return global_index

def process_query(ch, method, properties, body):
    data = json.loads(body)
    request_id = data.get("request_id")
    query_str = data.get("query")
    history_data = data.get("history", [])
    
    logger.info(f"[*] Picked up request {request_id}")

    # --- DEBUG LOG 1: Check the raw UI payload ---
    logger.info(f"--- DEBUG: RAW HISTORY LENGTH ---: {len(history_data)}")
    logger.info(f"--- DEBUG: RAW HISTORY DATA ---:\n{json.dumps(history_data, indent=2)}")
    #
    gateway_url = os.getenv("API_GATEWAY_URL", "http://adeo_api_gateway:8000")
    
    try:
        index = initialize_index()
        
        # 1. Format Memory
        chat_history = [ChatMessage(role=msg.get("role"), content=msg.get("content")) for msg in history_data]
        
        chat_engine = index.as_chat_engine(
            chat_mode="condense_plus_context",
            memory=ChatMemoryBuffer.from_defaults(chat_history=chat_history, token_limit=3000),
            system_prompt="You are a helpful AI assistant. Use the context and chat history to answer the user."
        )
        
        # 2. Query Local Database First
        response = chat_engine.chat(query_str)
        
        # --- NEW: EXPLICITLY LOG RETRIEVED DB NODES ---
        logger.info("\n" + "="*40)
        logger.info("       RETRIEVED DB CHUNKS/NODES")
        logger.info("="*40)
        if not response.source_nodes:
            logger.warning(">>> NO NODES RETRIEVED FROM CHROMADB OR NEO4J <<<")
        else:
            for idx, node in enumerate(response.source_nodes):
                score = getattr(node, 'score', 'No Score')
                file_name = node.node.metadata.get('file_name', 'Unknown')
                page_label = node.node.metadata.get('page_label', 'Unknown')
                snippet = node.node.get_content().replace('\n', ' ')[:100]
                logger.info(f"[{idx+1}] Score: {score} | File: {file_name} (Pg {page_label}) | Text: {snippet}...")
        logger.info("="*40 + "\n")
        # ----------------------------------------------

        # 3. DETERMINISTIC SCORE CHECK
        best_score = 0.5
        if response.source_nodes:
            # Extract valid scores (ignoring pure graph-traversal nodes that might lack a float score)
            valid_scores = [float(n.score) for n in response.source_nodes if getattr(n, 'score', None) is not None]
            if valid_scores:
                best_score = max(valid_scores)
            else:
                best_score = 1.0 # If we found graph nodes without scores, assume it's a direct entity match
                
        # --- THE FALLBACK TRIGGER ---
        SIMILARITY_THRESHOLD = 0.5
        local_match = False
        # Change this value to make it more or less strict!
        
        if best_score >= SIMILARITY_THRESHOLD:
            logger.info(f"Score {best_score:.2f} >= {SIMILARITY_THRESHOLD}. Running LLM Verification...")
            
            # Combine the retrieved text for the LLM to verify
            retrieved_text = "\n\n".join([n.node.get_content() for n in response.source_nodes])
            
            # 2nd Gate: LLM Strict Verification
            verification_prompt = (
                f"You are a strict data evaluator. Read the following question and the retrieved context.\n"
                f"Question: {query_str}\n\n"
                f"Retrieved Context:\n{retrieved_text}\n\n"
                f"Does the retrieved context explicitly contain the necessary information to answer the question? "
                f"Answer ONLY with YES or NO."
            )
            
            # Ask the LLM to verify
            verification_result = Settings.llm.complete(verification_prompt).text.strip().upper()
            
            if "YES" in verification_result:
                logger.info("LLM Verification: YES. Local Knowledge Match confirmed!")
                local_match = True
            else:
                logger.warning(f"LLM Verification: NO. (LLM rejected local context despite score {best_score:.2f})")
                local_match = False
        else:
            logger.warning(f"Low Confidence ({best_score:.2f} < {SIMILARITY_THRESHOLD}). Skipping LLM Verification.")
            local_match = False

        # --- ROUTING BASED ON DUAL MECHANISM ---
        if local_match:
            # We passed BOTH the vector score check AND the LLM verification
            citations = []
            for node in response.source_nodes:
                citations.append({
                    "file_name": node.node.metadata.get('file_name', 'Unknown File'),
                    "page_label": node.node.metadata.get('page_label', 'N/A'),
                    "score": getattr(node, 'score', None)
                })
                
            final_answer = str(response.response)
            
        else:
            logger.warning(f"Low Confidence ({best_score:.2f} < {SIMILARITY_THRESHOLD}). Triggering Tavily Web Search...")
            
            # --- NEW: CONTEXTUALIZE THE SEARCH QUERY FOR TAVILY ---
            search_query = query_str

            if chat_history:
                formatted_history = "\n".join([f"{msg.role.capitalize()}: {msg.content}" for msg in chat_history[-4:]])
                # --- DEBUG LOG 2: Check what the LLM is actually reading ---
                logger.info(f"--- DEBUG: FORMATTED HISTORY FOR LLM ---:\n{formatted_history}")
                # -----------------------------------------------------------
                # Ask Groq to rewrite the question using recent history
                condense_prompt = (
                    "You are an expert search query generator. Your task is to rewrite the user's latest question "
                    "into a highly specific, standalone web search query that can be understood without any prior context.\n\n"
                    "RULES:\n"
                    "1. Analyze the Conversation History to understand the current topic, entities, or concepts being discussed.\n"
                    "2. Resolve ALL pronouns (e.g., 'he', 'it', 'they', 'this', 'that') and relative references (e.g., 'similar ones', 'the previous method', 'why did that happen?') by replacing them with the exact nouns, names, or values from the history.\n"
                    "3. Ensure the final query includes all necessary context (locations, specific subjects, technical terms) so a search engine can find the precise answer.\n"
                    "4. If the user's latest question is already completely standalone, output it as a clean search string without changing its meaning.\n"
                    "5. DO NOT answer the question. ONLY output the optimized standalone search query.\n\n"
                    f"Conversation History:\n{formatted_history}\n\n"
                    f"Latest Question: {query_str}\n\n"
                    "Standalone Search Query:"
                )
                # We use Settings.llm to do a fast, text-only completion
                rewrite_response = Settings.llm.complete(condense_prompt)
                search_query = rewrite_response.text.strip().strip('"').strip("'")
                
                logger.info(f"Contextualized Tavily Search: '{query_str}' -> '{search_query}'")

            # Initialize Tavily
            tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
            
            # Perform Live Web Search
            search_result = tavily.search(query=search_query, search_depth="basic", max_results=3)
            
            web_contexts = []
            citations = []
            
            # Format Tavily output into citations for Streamlit
            for idx, res in enumerate(search_result.get("results", [])):
                web_contexts.append(f"Source {idx+1}: {res.get('content')}")
                citations.append({
                    "file_name": res.get("url", "Web Source"),
                    "page_label": "Web",
                    "score": res.get("score", 1.0)
                })
                
            context_string = "\n\n".join(web_contexts)
            
            # Prompt the LLM using the newly scraped Web Context
            fallback_prompt = (
                f"The internal database did not contain the answer. "
                f"Please answer the user's question using ONLY the following live web search results.\n\n"
                f"Web Results:\n{context_string}\n\n"
                f"Question: {query_str}"
            )
            
            # Use Groq to synthesize the web data (preserving history context)
            temp_history = chat_history.copy()
            temp_history.append(ChatMessage(role=MessageRole.USER, content=fallback_prompt))
            
            web_response = Settings.llm.chat(temp_history)
            final_answer = str(web_response.message.content)

        # 4. Package and Send Payload
        result_payload = {
            "status": "completed",
            "answer": final_answer,
            "citations": citations
        }
        
        resp = requests.post(f"{gateway_url}/internal/result/{request_id}", json=result_payload)
        resp.raise_for_status() 
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"CRITICAL ERROR processing {request_id}: {str(e)}")
        try:
            requests.post(f"{gateway_url}/internal/result/{request_id}", json={"status": "error", "message": str(e)})
        except:
            pass
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_worker():
    time.sleep(10)

    params = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "adeo_rabbitmq"),
        heartbeat=0, 
        blocked_connection_timeout=3600
    )

    connection = pika.BlockingConnection(params)
    # connection = pika.BlockingConnection(pika.ConnectionParameters(host=os.getenv("RABBITMQ_HOST", "adeo_rabbitmq")))
    channel = connection.channel()
    channel.queue_declare(queue='query_tasks', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='query_tasks', on_message_callback=process_query)
    
    logger.info("Agent Worker started. Waiting for messages...")
    channel.start_consuming()

if __name__ == "__main__":
    start_worker()