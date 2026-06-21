from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# lightweight model (fast + good accuracy)
model = SentenceTransformer("all-MiniLM-L6-v2")


def filter_relevant_news(user_query, articles, threshold=0.35):
    """
    Filters irrelevant news using semantic similarity
    """

    if not articles:
        return []

    # Encode user query
    query_vec = model.encode([user_query])

    filtered = []

    for article in articles:

        text = (article.get("title", "") + " " +
                article.get("description", "")).strip()

        if not text:
            continue

        article_vec = model.encode([text])

        score = cosine_similarity(query_vec, article_vec)[0][0]

        if score >= threshold:
            article["semantic_score"] = float(score)
            filtered.append(article)

    # Sort by semantic relevance
    filtered.sort(key=lambda x: x["semantic_score"], reverse=True)

    return filtered