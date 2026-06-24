# GoogleSearch.py
import requests
from bs4 import BeautifulSoup

def get_location():
    # Here you could use a service to get the user's actual location.
    # For simplicity, let's assume the location is New Delhi, India.
    return "New Delhi, India"

def find_nearby_places(keyword, limit=3):
    query = f"{keyword} near me"
    url = f"https://www.google.com/search?q={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    print(f"Google Search URL: {url}")
    print(f"Google Search Response Code: {response.status_code}")
    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    for result in soup.select('.VkpGBb'):
        if len(results) >= limit:
            break
        name_tag = result.select_one('.dbg0pd')
        address_tag = result.select_one('.rllt__details div')
        link_tag = result.find('a', href=True)

        name = name_tag.get_text() if name_tag else "Name not found"
        address = address_tag.get_text() if address_tag else "Address not found"
        link = f"https://www.google.com{link_tag['href']}" if link_tag else "Link not found"
        
        results.append({'name': name, 'address': address, 'link': link})

    print(f"Extracted Results: {results}")
    return results

def get_places_info(keyword):
    places = find_nearby_places(keyword)
    if not places:
        return None
    
    results = []
    for place in places:
        place_info = {
            'name': place['name'],
            'address': place['address'],
            'link': place['link']
        }
        results.append(place_info)
    
    return results
