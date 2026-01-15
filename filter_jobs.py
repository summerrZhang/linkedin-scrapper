import os
import json
import re
import pandas as pd
from thefuzz import process
from google import genai

# --- CONFIGURATION ---
CV_TXT_PATH = "my_cv.txt"
CV_ANALYSIS_PATH = "cv_analyze.txt"
DUTCH_FILTERS_PATH = "dutch_filters.txt"
VISA_FILTERS_PATH = "visa_filters.txt"
LEARNED_PHRASES_PATH = "learned_filters.txt"
IND_CSV_PATH = "ind_companies.csv"  # Ensure this file exists in your directory
MODEL_B = "gemini-2.5-flash-lite" # Tiny/Fast
MODEL_C = "gemini-2.5-flash"      # More capable


def load_filters(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def append_filter(file_path, phrase):
    existing = load_filters(file_path)
    phrase_clean = phrase.strip()
    if phrase_clean.lower() not in [e.lower() for e in existing]:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(phrase_clean + "\n")
        return True
    return False

# --- AGENT A: CV ANALYZER ---
def get_cv_context(client):
    """Analyzes CV once and caches the result."""
    if os.path.exists(CV_ANALYSIS_PATH):
        with open(CV_ANALYSIS_PATH, "r",encoding='utf-8') as f:
            return f.read()

    print("Agent A: Analyzing your CV for the first time...")
    with open(CV_TXT_PATH, "r", encoding='utf-8') as f:
        cv_content = f.read()

    prompt = f"""
    Analyze the following CV for a Computer Science graduate. 
    Extract:
    1. Primary Tech Stack (Languages, Frameworks, Tools).
    2. Specialized areas (e.g., Computer Vision, DevOps, Backend).
    3. 5-7 Key keywords that represent this candidate's profile.
    
    CV CONTENT:
    {cv_content}
    
    Return a concise summary to be used for job matching.
    """
    
    response = client.models.generate_content(model=MODEL_C, contents=prompt)
    analysis = response.text
    
    with open(CV_ANALYSIS_PATH, "w") as f:
        f.write(analysis)
    
    return analysis

# --- HARD FILTERS (Regex & CSV) ---
def check_ind_sponsorship(company_name):
    """Checks if the company is on the Dutch IND Sponsor list."""
    try:
        df = pd.read_csv(IND_CSV_PATH)
        # Assuming the CSV has a column 'Organisation' or 'company'
        col_name = 'company' if 'company' in df.columns else df.columns[0]
        ind_list = df[col_name].astype(str).tolist()
        
        best_match, score = process.extractOne(company_name, ind_list)
        return True if score > 85 else False
    except Exception as e:
        print(f"IND Check Error: {e}")
        return False


# --- STAGE 1: REGEX HARD FILTER ---
def quick_regex_filter(description):
    dutch_patterns = load_filters(DUTCH_FILTERS_PATH)
    visa_patterns = load_filters(VISA_FILTERS_PATH)
    desc_low = description.lower()
    
    for p in dutch_patterns:
        if re.search(re.escape(p.lower()), desc_low): return f"Dutch Required ({p})"
    for p in visa_patterns:
        if re.search(re.escape(p.lower()), desc_low): return f"Visa Issue ({p})"
    return None

# --- STAGE 2: AGENT B (GATEKEEPER & LEARNER) ---
def agent_b_filter(job_data, client):
    prompt = f"""
    Analyze this job for a non-Dutch speaker needing visa sponsorship.
    Title: {job_data['title']} | Desc: {job_data['description'][:1500]}
    Return ONLY JSON:
    {{
        "requires_dutch": boolean,
        "no_sponsorship": boolean,
        "dutch_phrase": "EXACT phrase from Desc text if true",
        "visa_phrase": "EXACT phrase from Desc text if true"
    }}
    """
    try:
        response = client.models.generate_content(model=MODEL_B, contents=prompt)
        res = json.loads(response.text.replace('```json', '').replace('```', '').strip())
        
        # Add to learning files
        if res.get('requires_dutch') and res.get('dutch_phrase'):
            append_filter(DUTCH_FILTERS_PATH, res['dutch_phrase'])
        if res.get('no_sponsorship') and res.get('visa_phrase'):
            append_filter(VISA_FILTERS_PATH, res['visa_phrase'])
        return res
    except:
        return {"requires_dutch": False, "no_sponsorship": False}

# --- AGENT C: THE ANALYST ---
def agent_c_analyze(job_data, cv_context, client):
    prompt = f"""
    Based on the Candidate Profile, explain why this job fits or doesn't fit.
    PROFILE: {cv_context}
    JOB: {job_data['title']} at {job_data['company']}
    DESC: {job_data['description'][:2500]}

    Return ONLY JSON:
    {{
        "is_good_fit": boolean,
        "reasoning": "If is_good_fit is true, 3-5 sentences explaining why. If false, exactly 2 sentences why not."
    }}
    """
    try:
        response = client.models.generate_content(model=MODEL_C, contents=prompt)
        return json.loads(response.text.replace('```json', '').replace('```', '').strip())
    except:
        return {"is_good_fit": False, "reasoning": "Error during reasoning generation."}


# --- MAIN PIPELINE FUNCTION ---
def analyze_job_with_ai(job_data, client):
    # 1. Get CV Info
    cv_context = get_cv_context(client)
    
    # 2. Hard Filters (Regex)
    reject_reason = quick_regex_filter(job_data['description'])
    if reject_reason:
        print(f"   [Regex Skip] {reject_reason}")
        return None
    
    # 3. Agent B (Gatekeeper + Learning)
    b_res = agent_b_filter(job_data, client)
    if b_res['requires_dutch'] or b_res['no_sponsorship']:
        print(f"   [Agent B Skip] Dutch/Visa requirement detected.")
        return None
        
    # 4. IND Tagging (Soft Tag - Does not filter)
    is_ind = check_ind_sponsorship(job_data['company'])
    
    # 5. Agent C (Reasoning)
    analysis = agent_c_analyze(job_data, cv_context, client)
    
    # Prepare final payload
    return {
        "reasoning": analysis['reasoning'],
        "is_good_fit": analysis['is_good_fit'],
        "is_ind_sponsor": is_ind
    }