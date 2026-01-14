import os
from dotenv import load_dotenv
import json
import re
import pandas as pd
from thefuzz import process
from google import genai
from google.genai import errors
import time


# --- CONFIGURATION ---
load_dotenv()

IND_CSV_PATH = 'ind_companies.csv' # Path to your IND file
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL_NAME = 'gemini-2.5-flash-lite'
# --- 1. THE REGEX FILTER (Cheap & Fast) ---
def check_hard_filters(description):
    """Returns (is_discarded, reason)"""
    # Patterns that mean 'No Visa'
    no_visa_patterns = [
        r"no visa sponsorship", r"not provide sponsorship", 
        r"authorized to work in the Netherlands", r"no sponsorship provided",
        r"geen visum sponsoring", 
    ]
    # Patterns that mean 'Must speak Dutch'
    dutch_patterns = [
        r"vloeiend nederlands", r"Vloeiend in Nederlands", r"beheersing van de nederlandse taal", 
        r"dutch is mandatory", r"must be fluent in dutch", r"Excellent command of Dutch and English",
        r"nederlands is een vereiste", r"professional proficiency (written and spoken) in both Dutch and English",
        r"sterke communicatieve vaardigheden in Nederlandse en Engels", r"Dutch fluency required",
        r"Uitstekende beheersing van Nederlands en Engels", r"communiceert duidelijk en beheerst de Nederlandse en Engelse taal goed"

    ]

    for p in no_visa_patterns:
        if re.search(p, description, re.IGNORECASE):
            return True, "Explicitly stated: No Visa Sponsorship"
    
    for p in dutch_patterns:
        if re.search(p, description, re.IGNORECASE):
            return True, "Mandatory Dutch requirement detected"
            
    return False, None

# --- 2. THE IND MATCHER (The Highlight) ---
def match_ind_list(company_name, ind_list):
    """Returns (is_on_list, score, official_name)"""
    # Fuzzy match to handle 'Tesla' vs 'Tesla Motors B.V.'
    best_match, score = process.extractOne(company_name, ind_list)
    if score > 85: # High threshold for accuracy
        return True, score, best_match
    return False, score, None

# --- 3. THE AI AGENT (High Quality Context) ---
def analyze_with_ai(job, retries=3):
    """Analyzes job with retry logic and throttling."""
    prompt = f"""
    Analyze this job for a Junior CS graduate:
    Title: {job['title']}
    Description: {job['description'][:2000]} 

    Return ONLY a JSON object with:
    "tech_stack": list of strings,
    "experience_fit": "Perfect" or "Too Senior",
    "cs_match_score": integer 1-10
    """

    for attempt in range(retries):
        try:
            # 1. THE CALL
            response = client.models.generate_content(
                model=MODEL_NAME, 
                contents=prompt
            )
            
            # 2. PARSING
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            result = json.loads(clean_json)
            
            # 3. THROTTLING (Wait 12 seconds to stay under 5 RPM limit)
            print(f"   Success! Waiting 12s to respect free tier limits...")
            time.sleep(12) 
            return result

        except errors.ClientError as e:
            if "429" in str(e):
                wait_time = (attempt + 1) * 20  # Wait 20s, 40s, 60s
                print(f"   Quota hit. Retrying in {wait_time}s... (Attempt {attempt+1}/{retries})")
                time.sleep(wait_time)
            else:
                print(f"   AI Error: {e}")
                break
        except Exception as e:
            print(f"   Unexpected Error: {e}")
            break

    return {"tech_stack": [], "experience_fit": "Unknown", "cs_match_score": 0}

# --- MAIN PIPELINE ---
def run_pipeline(jobs_input_path):
    # Load IND List
    ind_df = pd.read_csv(IND_CSV_PATH)
    # The IND list usually has the company name in 'Organisation' column
    ind_list = ind_df['company'].tolist()

    # Load Scraped Jobs
    with open(jobs_input_path, 'r', encoding='utf-8') as f:
        jobs = json.load(f)

    final_results = []

    for job in jobs:
        desc = job.get('description', '')
        company = job['company']['name']

        # Step 1: Regex Check (Skip if Hard No)
        is_discarded, reason = check_hard_filters(desc)
        if is_discarded:
            print(f"Skipping {job['title']} at {company}: {reason}")
            continue

        # Step 2: IND Check (Highlight)
        is_ind, score, official_name = match_ind_list(company, ind_list)
        
        # Step 3: AI Check (Rank)
        print(f"Analyzing {job['title']} at {company}...")
        ai_data = analyze_with_ai(job)

        # Merge all data
        processed_job = {
            "title": job['title'],
            "company": company,
            "url": job['url'],
            "ind_sponsor": is_ind,
            "ind_match_score": score if is_ind else 0,
            "ai_analysis": ai_data
        }
        final_results.append(processed_job)

    # Sort: Put IND Sponsors with high CS scores at the top
    final_results.sort(key=lambda x: (x['ind_sponsor'], x['ai_analysis']['cs_match_score']), reverse=True)

    with open('filtered_jobs.json', 'w', encoding='utf-8') as f:
        json.dump(final_results, f, indent=4)
    
    print(f"\nPipeline complete. {len(final_results)} jobs ready for review.")

if __name__ == "__main__":
    run_pipeline('jobs.json')