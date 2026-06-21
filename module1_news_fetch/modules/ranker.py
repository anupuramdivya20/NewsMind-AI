from collections import defaultdict

# =========================
# FEATURE-BASED RANKING SYSTEM
# =========================

def compute_content_score(user_interests, article_text):
    score = 0

    article_text = article_text.lower()

    for interest in user_interests:
        if interest.lower() in article_text:
            score += 3

    return score


def compute_location_score(location, article_text):
    text = article_text.lower()

    if location == "telangana":
        keywords = ["telangana", "hyderabad", "kcr", "revanth", "brs"]
        return sum(2 for k in keywords if k in text)

    if location == "india":
        return 1 if "india" in text or "indian" in text else 0

    return 1


def compute_sentiment_score(sentiment):
    if sentiment == "positive":
        return 1
    elif sentiment == "negative":
        return 0.5
    return 0.8


def rank_articles(articles, user_interests, location):

    ranked = []

    for article in articles:

        title = article.get("title", "")
        desc = article.get("description", "")
        text = (title + " " + desc).lower()

        content_score = compute_content_score(user_interests, text)
        location_score = compute_location_score(location, text)
        sentiment_score = compute_sentiment_score(article.get("sentiment", "neutral"))

        final_score = (content_score * 0.6) + (location_score * 0.3) + (sentiment_score * 0.1)

        article["final_score"] = final_score
        ranked.append(article)

    ranked.sort(key=lambda x: x["final_score"], reverse=True)

    return ranked