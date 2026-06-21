from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")


# =========================
# ARTICLE EMBEDDING
# =========================
def encode_articles(articles):
    texts = [
        (a.get("title", "") + " " + a.get("description", ""))
        for a in articles
    ]
    return model.encode(texts)


# =========================
# USER EMBEDDING
# =========================
def encode_user_profile(interests):
    text = " ".join(interests)
    return model.encode([text])


# =========================
# SMART RECOMMENDATION ENGINE
# =========================
def recommend(user_interests, articles, top_k=20):

    if not articles:
        return []

    user_vec = encode_user_profile(user_interests)
    article_vecs = encode_articles(articles)

    scores = cosine_similarity(user_vec, article_vecs)[0]

    ranked = []

    for i, article in enumerate(articles):
        article["ai_score"] = float(scores[i])
        ranked.append(article)

    ranked.sort(key=lambda x: x["ai_score"], reverse=True)

    return ranked[:top_k]