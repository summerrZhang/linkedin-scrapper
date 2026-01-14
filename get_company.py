from bs4 import BeautifulSoup
import requests
import re
import csv
import time

ind_url = "https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants#content"

def get_company(url):
    response = requests.get(url)

    html = response.text
    with open("km.html", "w", encoding="utf-8") as file:
        file.write(html)
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tbody tr")

    results = []

    for row in rows:
        name_cell = row.find("th")
        kvk_cell = row.find("td")

        if not name_cell or not kvk_cell:
            continue

        name = name_cell.get_text(strip=True)
        kvk = kvk_cell.get_text(strip=True)

        results.append({"company": name, "kvk": kvk})

    with open("ind_companies.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "kvk"])
        writer.writeheader()
        writer.writerows(results)

    print(f"Saved {len(results)} companies.")

get_company(ind_url)