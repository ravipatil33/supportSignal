import os
import re
from pypdf import PdfReader
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_ibm import WatsonxLLM # Assuming IBM Cloud MaaS for Granite

# --- Configuration & Initialization ---
# Replace with your actual MaaS credentials/endpoint
granite_llm = WatsonxLLM(
    model_id="ibm/granite-7b-instruct",
    url="https://us-south.ml.cloud.ibm.com",
    params={"decoding_method": "greedy", "max_new_tokens": 500}
)

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# --- Agent 1: Log-Analyst ---
class LogAnalyst:
    def __init__(self, must_gather_path):
        self.path = must_gather_path
        self.error_patterns = [r"level=error", r"Failed", r"Panic", r"Back-off"]

    def extract_critical_logs(self):
        # Focus on operator and event logs in must-gather
        logs = ""
        for root, dirs, files in os.walk(self.path):
            for file in files:
                if "log" in file or "events" in file:
                    with open(os.path.join(root, file), 'r') as f:
                        content = f.read()
                        # Simple regex filtering to reduce token count for Granite-7b
                        matches = [line for line in content.split('\n') 
                                   if any(re.search(p, line, re.IGNORECASE) for p in self.error_patterns)]
                        logs += "\n".join(matches[-20:]) # Get last 20 errors per file
        return logs

    def identify_exact_error(self, log_snippet):
        prompt = f"""[INST] Analyze the following OpenShift AI logs. 
        Identify the exact root error message and the component failing.
        LOGS: {log_snippet}
        ERROR: [/INST]"""
        return granite_llm.invoke(prompt)

# --- Agent 2: Knowledge Agent ---
class KnowledgeAgent:
    def __init__(self, vector_db_path):
        # In production, this would be your pre-indexed Red Hat Docs/Jira
        self.db = FAISS.load_local(vector_db_path, embeddings)

    def search_solutions(self, error_query):
        docs = self.db.similarity_search(error_query, k=2)
        return "\n".join([d.page_content for d in docs])

# --- Agent 3: Synthesis Agent ---
class SynthesisAgent:
    def generate_report(self, case_text, logs, knowledge, versions):
        prompt = f"""[INST] You are a Red Hat Senior Support Engineer. 
        Based on the data below, provide a professional diagnosis.
        
        CASE CONTEXT: {case_text}
        LOG ERRORS: {logs}
        RELATED KCS/JIRA: {knowledge}
        SYSTEM INFO: {versions}

        FORMAT:
        1. Diagnosis: (What is happening)
        2. Root Cause: (Why it is happening)
        3. Action Plan: (Step-by-step resolution)
        [/INST]"""
        return granite_llm.invoke(prompt)

# --- Main Orchestrator ---
def run_support_signal(pdf_path, must_gather_dir):
    # 1. Parse Case PDF
    reader = PdfReader(pdf_path)
    case_context = " ".join([page.extract_text() for page in reader.pages])

    # 2. Run Log-Analyst
    analyst = LogAnalyst(must_gather_dir)
    raw_errors = analyst.extract_critical_logs()
    refined_error = analyst.identify_exact_error(raw_errors)

    # 3. Run Knowledge Search
    knowledge_base = KnowledgeAgent("vector_db_rh_kcs")
    solutions = knowledge_base.search_solutions(refined_error)

    # 4. Run Synthesis
    # Mocking version extraction for brevity
    versions = "OCP 4.14, RHOAI 2.5, NVIDIA GPU Operator v23.9"
    synthesis = SynthesisAgent()
    
    final_report = synthesis.generate_report(case_context, refined_error, solutions, versions)
    return final_report

# execution = run_support_signal("case_12345.pdf", "./must-gather-output")
# print(execution)
