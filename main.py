import os
import json
import time
from dotenv import load_dotenv
from google import genai

# Import your custom modules
from scraper import retrieve_job_urls, scrape_job_details
from filter_jobs import analyze_job_with_ai

# --- CONFIGURATION ---
load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

HISTORY_FILE = "processed_urls.txt"
OUTPUT_FILE = "ready_to_apply.json"

# Expanded Keywords (Removed the 'Junior' restriction to catch more opportunities)
KEYWORDS = [
    "Software Engineer", "Software Developer","Frontend Engineer"
    "Python Developer", "Full Stack Developer", "DevOps Engineer", 
    "Cloud Engineer", "Computer Vision", "Machine Learning", 
    "Data Engineer", "Technical Consultant", "IT Trainee"
]

MAX_JOBS_PER_KEYWORD = 8  # Increased slightly
SESSION_LIMIT = 40        # Increased for better coverage

def load_history():
    """Loads previously processed URLs from a text file."""
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_to_history(url):
    """Appends a single URL to the history file."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def main():
    # 1. Load History and Setup
    processed_history = load_history()
    all_filtered_jobs = []
    new_urls_to_analyze = []
    
    print(f"🚀 Job Pipeline Started. (History size: {len(processed_history)} URLs)")
    
    # 2. STEP 1: GATHERING URLS (Search Phase)
    print(f"Step 1: Searching for jobs across {len(KEYWORDS)} categories...")
    for kw in KEYWORDS:
        print(f"   🔍 Keyword: {kw}...")
        found_urls = retrieve_job_urls(kw)
        
        added_for_this_kw = 0
        for url in found_urls:
            # Skip if we already processed this URL in a previous run
            if url in processed_history:
                continue
            
            # Skip if we already added it to the batch in THIS run
            if url in new_urls_to_analyze:
                continue
                
            new_urls_to_analyze.append(url)
            added_for_this_kw += 1
            
            if added_for_this_kw >= MAX_JOBS_PER_KEYWORD:
                break
        
        time.sleep(1.5) # Anti-throttling for LinkedIn search

    print(f"\nFound {len(new_urls_to_analyze)} NEW jobs to analyze.")

    # 3. STEP 2: SCRAPE AND ANALYZE (AI Phase)
    processed_count = 0
    for url in new_urls_to_analyze:
        if processed_count >= SESSION_LIMIT:
            print("\nReached session limit for AI analysis.")
            break

        print(f"\n--- [{processed_count + 1}] Analyzing: {url} ---")
        
        # A. Scrape details
        job_data = scrape_job_details(url)
        
        if not job_data or len(job_data.get('description', '')) < 200:
            print("   ⚠️ Skipping: Description too short or scrape failed.")
            # We still add to history so we don't try to scrape this broken link again
            save_to_history(url)
            continue

        # B. AI Analysis Pipeline
        # This handles: Regex -> Agent B (Gatekeeper) -> IND Tagging -> Agent C (Reasoning)
        result = analyze_job_with_ai(job_data, client)

        # C. Handle Results
        if result:
            job_data.update(result)
            
            if job_data['is_good_fit']:
                print(f"   ✅ MATCH: {job_data['title']} at {job_data['company']}")
                if job_data['is_ind_sponsor']:
                    print("   🌟 [IND SPONSOR]")
                all_filtered_jobs.append(job_data)
            else:
                print(f"   ❌ Rejected: Low match for your profile.")
        else:
            # result is None means it was rejected by Regex or Agent B
            print(f"   🚫 Rejected: Language/Visa requirements or hard filters.")

        # D. Update history immediately after processing (even if rejected)
        save_to_history(url)
        processed_count += 1
        
        # Respect API Rate Limits (12s buffer for Gemini Free Tier)
        time.sleep(12)

    # 4. STEP 3: SAVE AND SORT
    if all_filtered_jobs:
        # Load existing results if they exist to merge them
        existing_results = []
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                try:
                    existing_results = json.load(f)
                except:
                    existing_results = []

        # Combine new results with old "ready to apply" jobs
        combined_results = existing_results + all_filtered_jobs
        
        # Sort by IND Sponsor first
        combined_results.sort(key=lambda x: x.get('is_ind_sponsor', False), reverse=True)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(combined_results, f, indent=4, ensure_ascii=False)

        print(f"\n\nPipeline Finished! {len(all_filtered_jobs)} new jobs added to {OUTPUT_FILE}")
    else:
        print("\n\nNo new matching jobs found in this run.")

if __name__ == "__main__":
    main()