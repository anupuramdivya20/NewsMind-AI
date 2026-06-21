from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)

def fit_transform(articles):
    corpus = [(a["title"] + " " + (a.get("description") or "")) for a in articles]
    matrix = vectorizer.fit_transform(corpus)
    return matrix

def get_scores(user_text, matrix):
    user_vec = vectorizer.transform([user_text])
    return cosine_similarity(user_vec, matrix).flatten()