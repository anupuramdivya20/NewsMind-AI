from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

vectorizer = TfidfVectorizer(stop_words="english")

def rank_articles(user_profile_text, articles):
    docs = [user_profile_text] + articles
    tfidf = vectorizer.fit_transform(docs)

    scores = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()

    ranked = sorted(zip(articles, scores), key=lambda x: x[1], reverse=True)

    return [r[0] for r in ranked]