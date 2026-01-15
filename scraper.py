import requests
from bs4 import BeautifulSoup
import time
import urllib.parse

def retrieve_job_urls(keyword, location="Netherlands"):
    encoded_keyword = urllib.parse.quote(keyword)
    # Added f_TPR=r86400 (last 24 hours) to avoid scraping old stuff every time
    url = f"https://www.linkedin.com/jobs/search?keywords={encoded_keyword}&location={location}&f_TPR=r86400&f_E=2"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error fetching {keyword}: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    job_urls = []
    # LinkedIn's public selector
    elements = soup.select(".base-card__full-link")
    for el in elements:
        job_urls.append(el["href"].split('?')[0]) # Clean URL
    
    return list(set(job_urls))

def scrape_job_details(job_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(job_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Use try-except blocks for each field to avoid crashes
        return {
            "url": job_url,
            "title": soup.find("h1").get_text(strip=True) if soup.find("h1") else "N/A",
            "company": soup.find("a", {"class": "topcard__org-name-link"}).get_text(strip=True) if soup.find("a", {"class": "topcard__org-name-link"}) else "N/A",
            "description": soup.select_one(".description__text").get_text(separator=" ", strip=True) if soup.select_one(".description__text") else ""
        }
    except Exception as e:
        print(f"Error scraping {job_url}: {e}")
        return None