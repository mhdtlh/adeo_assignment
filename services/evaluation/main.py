import os
import json
import time
import logging
import requests
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from llama_index.llms.groq import Groq
from llama_index.core import Settings

# Logging Setup
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, "evaluation.log"))
    ]
)
logger = logging.getLogger("ADEO.Evaluator")

app = FastAPI(title="ADEO Evaluation Service")

GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://adeo_api_gateway:8000")
DATASET_PATH = "/app/services/evaluation/eval_dataset.json"
REPORT_PATH = "/app/services/evaluation/evaluation_report.json"

# Initialize Groq as the "Judge"
judge_llm = Groq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))

def run_evaluation_pipeline():
    logger.info("Starting automated RAG evaluation pipeline...")
    
    if not os.path.exists(DATASET_PATH):
        logger.error(f"Dataset not found at {DATASET_PATH}")
        return

    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)

    results = []
    total_scores = {"relevance": 0, "faithfulness": 0, "accuracy": 0}

    for idx, item in enumerate(dataset):
        question = item["question"]
        ground_truth = item["ground_truth"]
        logger.info(f"Evaluating [{idx+1}/{len(dataset)}]: {question}")

        # 1. Ask the system
        try:
            start_time = time.time()
            resp = requests.post(f"{GATEWAY_URL}/query", json={"query": question, "history": []})
            req_id = resp.json().get("request_id")

            # 2. Poll for the answer
            system_answer = ""
            citations_text = ""
            for _ in range(120): # 2 minute timeout per question
                time.sleep(1)
                poll_resp = requests.get(f"{GATEWAY_URL}/result/{req_id}")
                if poll_resp.status_code == 200:
                    data = poll_resp.json()
                    if data.get("status") == "completed":
                        system_answer = data.get("answer", "")
                        citations = data.get("citations", [])
                        citations_text = json.dumps(citations)
                        break
            
            latency = round(time.time() - start_time, 2)

            # 3. Use LLM to Grade the response
            prompt = f"""
            You are an expert RAG evaluation judge. 
            Evaluate the following Generated Answer based on the Question and Ground Truth.
            
            Question: {question}
            Ground Truth (Expected): {ground_truth}
            Generated Answer: {system_answer}
            Retrieved Context (Citations): {citations_text}

            Score the following out of 5 (1=Terrible, 5=Perfect):
            1. relevance: Does the generated answer directly address the question?
            2. faithfulness: Is the generated answer supported by the Retrieved Context? (Score 1 if hallucinating).
            3. accuracy: Does the generated answer factually match the Ground Truth?

            Output ONLY a raw JSON object with no markdown formatting or extra text. Example:
            {{"relevance": 5, "faithfulness": 4, "accuracy": 5, "reasoning": "Short explanation"}}
            """
            
            grade_response = judge_llm.complete(prompt)
            
            # Clean LLM output
            raw_json = grade_response.text.strip().replace("```json", "").replace("```", "")
            try:
                grades = json.loads(raw_json)
            except:
                grades = {"relevance": 0, "faithfulness": 0, "accuracy": 0, "reasoning": "Failed to parse LLM JSON"}

            # Compile result
            eval_record = {
                "question": question,
                "ground_truth": ground_truth,
                "system_answer": system_answer,
                "latency_seconds": latency,
                "scores": grades
            }
            results.append(eval_record)
            
            total_scores["relevance"] += grades.get("relevance", 0)
            total_scores["faithfulness"] += grades.get("faithfulness", 0)
            total_scores["accuracy"] += grades.get("accuracy", 0)

        except Exception as e:
            logger.error(f"Failed to evaluate question '{question}': {str(e)}")

    # 4. Generate Final Report
    num_questions = len(results)
    final_report = {
        "summary": {
            "total_questions_evaluated": num_questions,
            "average_relevance": round(total_scores["relevance"] / max(num_questions, 1), 2),
            "average_faithfulness": round(total_scores["faithfulness"] / max(num_questions, 1), 2),
            "average_accuracy": round(total_scores["accuracy"] / max(num_questions, 1), 2),
        },
        "details": results
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(final_report, f, indent=4)
        
    logger.info(f"Evaluation complete! Report saved to {REPORT_PATH}")

@app.post("/trigger_evaluation")
async def trigger_eval(background_tasks: BackgroundTasks):
    logger.info("Evaluation triggered via API")
    background_tasks.add_task(run_evaluation_pipeline)
    return {"status": "started", "message": "Evaluation running in background. Check evaluation_report.json when complete."}

@app.get("/report")
async def get_report():
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "r") as f:
            return json.load(f)
    return {"status": "pending", "message": "Report has not been generated yet."}