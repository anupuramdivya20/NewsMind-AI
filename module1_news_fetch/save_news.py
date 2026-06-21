import requests
import json

#  API KEY
API_KEY = "9ffdc75e97b241e383f9f2b367de3218"

#  API URL (reliable endpoint)
url = f"https://newsapi.org/v2/everything?q=technology&language=en&sortBy=publishedAt&apiKey={API_KEY}"

try:
    #  Fetch data
    response = requests.get(url)
    data = response.json()

    #  Check API status
    if data.get("status") != "ok":
        print("API Error:", data.get("message"))
        exit()

    articles = data.get("articles", [])

    #  Clean & structure data
    news_dataset = []

    for article in articles:
        if article["title"] and article["description"]:
            news_item = {
                "title": article["title"],
                "description": article["description"],
                "source": article["source"]["name"],
                "url": article["url"],
                "publishedAt": article["publishedAt"]
            }
            news_dataset.append(news_item)

    #  Save to JSON file
    with open("news_dataset.json", "w", encoding="utf-8") as f:
        json.dump(news_dataset, f, indent=4, ensure_ascii=False)
    print("Module 2 Completed Successfully!")
    print(f" Total News Stored: {len(news_dataset)}")

except Exception as e:
    print(" Error occurred:", str(e))