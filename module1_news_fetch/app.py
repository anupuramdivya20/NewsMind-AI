from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from modules.bookmarks import save_bookmark, get_bookmarks, delete_bookmark
from textblob import TextBlob
import requests
import os
import uuid
from gtts import gTTS
import sqlite3
import re
import feedparser
import time
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

# =========================
# SAFE IMAGE
# =========================
def safe_image(article):
    img = article.get("urlToImage")
    if not img or str(img).strip() == "" or "http" not in str(img):
        img = "https://via.placeholder.com/400x200?text=No+Image"
    return img

# =========================
# CLEAN HTML FROM RSS
# =========================
def clean_html(text):
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)

from modules.translator import translate_text
from modules.rgrec import get_rgrec_recommendations
from modules.muma import get_muma_recommendations
from modules.hybrid import hybrid_recommendations
from modules.summarizer import summarize
from modules.content import get_content_score
from modules.recommendation import (
    update_interest,
    get_user_profile,
    track_article,
    get_popularity_score
)

# SAFE IMPORT
try:
    from modules.collaborative import save_interaction, get_collaborative_recommendations
except:
    def save_interaction(*args, **kwargs):
        pass

    def get_collaborative_recommendations(username):
        return []

app = Flask(__name__)
app.secret_key = "secret123"

API_KEY = "9ffdc75e97b241e383f9f2b367de3218"

# =========================
# CACHE
# =========================
NEWS_CACHE = {}
CACHE_TIME = 600   # 10 minutes

# =========================
# INIT DB
# =========================
def init_db():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =========================
# SENTIMENT
# =========================
def get_sentiment(text):
    polarity = TextBlob(text).sentiment.polarity
    if polarity > 0:
        return "positive"
    elif polarity < 0:
        return "negative"
    return "neutral"

# =========================
# CATEGORY MAP
# =========================
CATEGORY_MAP = {
    "technology": "technology OR AI OR software OR gadgets OR programming",
    "business": "business OR economy OR stock market OR startups OR finance",
    "sports": "cricket OR football OR IPL OR sports",
    "health": "health OR fitness OR medicine",
    "entertainment": "movies OR celebrity OR bollywood OR hollywood",
    "science": "science OR space OR NASA OR research",
    "politics": "politics OR government OR election OR parliament OR policy OR minister"
}

# =========================
# NORMALIZE INTEREST
# =========================
def normalize_interest(value):
    if not value:
        return ""
    return str(value).strip()

# =========================
# BUILD QUERY
# =========================
def build_query(category, subcategory, search, username, location):
    """
    - search keyword works immediately
    - category + subcategory stored for logged-in user
    - recommendations use all stored interests
    """
    query_parts = []

    # 1. search
    if search and search.strip():
        query_parts.append(search.strip())

    # 2. store current category/subcategory
    if username and username != "Guest":
        if category and category.strip():
            update_interest(username, category.strip())
            save_interaction(username, category.strip())

        if subcategory and subcategory.strip():
            update_interest(username, subcategory.strip())
            save_interaction(username, subcategory.strip())

    # 3. current category/subcategory influence query
    if category and category.strip():
        cat = category.strip().lower()
        if cat in CATEGORY_MAP:
            query_parts.append(f"({CATEGORY_MAP[cat]})")
        else:
            query_parts.append(category.strip())

    if subcategory and subcategory.strip():
        query_parts.append(subcategory.strip())

    # 4. add stored interests
    if username and username != "Guest":
        profile = get_user_profile(username)
        if profile:
            interests = [normalize_interest(i[0]) for i in profile if i and i[0]]
            interests = list(set([i for i in interests if i]))

            for interest in interests:
                interest_lower = interest.lower()
                if interest_lower in CATEGORY_MAP:
                    query_parts.append(f"({CATEGORY_MAP[interest_lower]})")
                else:
                    query_parts.append(interest)

    # 5. fallback
    if not query_parts:
        query_parts = ["technology", "business", "sports"]

    # remove duplicates
    final_parts = []
    seen = set()
    for q in query_parts:
        q_clean = q.strip()
        if q_clean and q_clean.lower() not in seen:
            final_parts.append(q_clean)
            seen.add(q_clean.lower())

    query = " OR ".join(final_parts)

    # 6. location filter
    if location == "india":
        query = f"India AND ({query})"
    elif location == "telangana":
        query = f"(Telangana OR Hyderabad) AND ({query})"

    print("FINAL QUERY =", query)
    return query.strip()

# =========================
# RSS FALLBACK
# =========================
def fetch_from_rss(query):
    encoded_query = quote_plus(query)

    rss_urls = [
        f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en",
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"
    ]

    articles = []

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)

            for entry in feed.entries[:10]:
                title = clean_html(entry.get("title", ""))
                link = entry.get("link", "")
                description = clean_html(entry.get("summary", "")) if "summary" in entry else ""

                articles.append({
                    "title": title,
                    "description": description,
                    "url": link,
                    "urlToImage": None,
                    "source": {"name": "RSS Feed"}
                })
        except Exception as e:
            print("RSS ERROR:", e)

    return articles

# =========================
# FETCH NEWS
# =========================
def fetch_news(query):
    # cache
    if query in NEWS_CACHE:
        cached_articles, cached_time = NEWS_CACHE[query]
        if time.time() - cached_time < CACHE_TIME:
            print("Using cached news for:", query)
            return cached_articles

    url = (
        "https://newsapi.org/v2/everything?"
        f"q={quote_plus(query)}"
        "&language=en"
        "&sortBy=publishedAt"
        "&pageSize=30"
        f"&apiKey={API_KEY}"
    )

    print("Trying NewsAPI:", url)

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("status") != "ok":
            print("NewsAPI failed:", data)
            print("Switching to RSS fallback...")
            rss_articles = fetch_from_rss(query)
            NEWS_CACHE[query] = (rss_articles, time.time())
            return rss_articles

        articles = data.get("articles", [])
        NEWS_CACHE[query] = (articles, time.time())
        return articles

    except Exception as e:
        print("NewsAPI ERROR:", e)
        print("Switching to RSS fallback...")
        rss_articles = fetch_from_rss(query)
        NEWS_CACHE[query] = (rss_articles, time.time())
        return rss_articles

# =========================
# FILTER TELANGANA
# =========================
def filter_telangana(articles, location):
    if location != "telangana":
        return articles

    keywords = ["telangana", "hyderabad", "kcr", "revanth", "brs", "congress"]
    filtered = []

    for a in articles:
        text = (
            clean_html(a.get("title") or "") + " " +
            clean_html(a.get("description") or "")
        ).lower()

        if any(k in text for k in keywords):
            filtered.append(a)

    return filtered

# =========================================================
# HELPER FUNCTIONS
# =========================================================
def normalize_text_list(values):
    out = []
    for v in values:
        if not v:
            continue
        if isinstance(v, (list, tuple)):
            for x in v:
                if x:
                    out.append(str(x).strip().lower())
        else:
            out.append(str(v).strip().lower())
    return list(set([x for x in out if x]))

def get_content_recommendations(username):
    if not username or username == "Guest":
        return []

    try:
        profile = get_user_profile(username)
        if not profile:
            return []

        interests = [i[0] for i in profile if i and i[0]]
        return normalize_text_list(interests)
    except Exception as e:
        print("CONTENT ERROR:", e)
        return []

def get_rgrec_list(username):
    if not username or username == "Guest":
        return []

    try:
        recs = get_rgrec_recommendations(username)
        return normalize_text_list(recs)
    except Exception as e:
        print("RGREC ERROR:", e)
        return []

def get_muma_list(username):
    if not username or username == "Guest":
        return []

    try:
        recs = get_muma_recommendations(username)
        return normalize_text_list(recs)
    except Exception as e:
        print("MUMA ERROR:", e)
        return []

def get_collaborative_list(username):
    if not username or username == "Guest":
        return []

    try:
        recs = get_collaborative_recommendations(username)
        return normalize_text_list(recs)
    except Exception as e:
        print("COLLAB ERROR:", e)
        return []

def score_article_with_models(article, content_recs, rgrec_recs, muma_recs, collab_recs):
    """
    Score one article using all recommendation methods.
    """
    title = clean_html(article.get("title") or "").lower()
    desc = clean_html(article.get("description") or "").lower()
    full_text = title + " " + desc

    content_score = 0
    rgrec_score = 0
    muma_score = 0
    collab_score = 0

    # CONTENT SCORE
    for kw in content_recs:
        if kw and kw in full_text:
            content_score += 1

    # RGREC SCORE
    for kw in rgrec_recs:
        if kw and kw in full_text:
            rgrec_score += 1

    # MUMA SCORE
    for kw in muma_recs:
        if kw and kw in full_text:
            muma_score += 1

    # COLLAB SCORE
    for kw in collab_recs:
        if kw and kw in full_text:
            collab_score += 1

    popularity_score = get_popularity_score(article.get("title", ""))

    # HYBRID SCORE
    try:
        hybrid_score = hybrid_recommendations(
            content_score,
            collab_score,
            rgrec_score,
            muma_score,
            popularity_score
        )
    except:
        hybrid_score = (
            (2 * content_score) +
            (2 * collab_score) +
            (2 * rgrec_score) +
            (2 * muma_score) +
            popularity_score
        )

    return {
        "content_score": content_score,
        "rgrec_score": rgrec_score,
        "muma_score": muma_score,
        "collab_score": collab_score,
        "popularity_score": popularity_score,
        "hybrid_score": hybrid_score
    }

# =========================
# ROOT
# =========================
@app.route("/")
def index():
    category = request.args.get("category", "")
    subcategory = request.args.get("subcategory", "")
    search = request.args.get("query", "")
    location = request.args.get("location", "world")
    language = request.args.get("language", "en")

    if search.strip():
        query = search.strip()
    else:
        query = "technology OR AI OR business OR sports"

    articles = fetch_news(query)
    news_list = []

    for article in articles:
        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")

        if search.strip():
            reason = f"Searched keyword: {search.strip()}"
        elif subcategory:
            reason = f"Selected subcategory: {subcategory}"
        elif category:
            reason = f"Selected category: {category.title()}"
        else:
            reason = "Trending News"

        news_list.append({
            "title": title,
            "summary": summarize(title + " " + desc),
            "source": article.get("source", {}).get("name", "Unknown"),
            "image": safe_image(article),
            "url": article.get("url"),
            "score": get_popularity_score(title),
            "sentiment": get_sentiment(title + " " + desc),
            "reason": reason
        })

    username = session.get("user", "Guest")

    return render_template(
        "index.html",
        news=news_list,
        user=username,
        category=category,
        subcategory=subcategory,
        location=location,
        language=language,
        search=search
    )

# =========================
# HOME
# =========================
@app.route("/home")
def home():
    username = session.get("user", "Guest")

    category = request.args.get("category", "")
    subcategory = request.args.get("subcategory", "")
    search = request.args.get("query", "")
    location = request.args.get("location", "world")
    language = request.args.get("language", "en")

    print("CATEGORY =", category)
    print("SUBCATEGORY =", subcategory)
    print("SEARCH =", search)
    print("LOCATION =", location)

    query = build_query(category, subcategory, search, username, location)
    print("QUERY =", query)

    articles = fetch_news(query)
    articles = filter_telangana(articles, location)

    # model recommendation keywords
    content_recs = get_content_recommendations(username)
    rgrec_recs = get_rgrec_list(username)
    muma_recs = get_muma_list(username)
    collab_recs = get_collaborative_list(username)

    print("CONTENT RECS =", content_recs)
    print("RGREC RECS =", rgrec_recs)
    print("MUMA RECS =", muma_recs)
    print("COLLAB RECS =", collab_recs)

    news_list = []

    profile = get_user_profile(username) if username != "Guest" else []
    interests = [i[0].lower() for i in profile] if profile else []

    for article in articles:
        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")
        full_text = title + " " + desc

        summary_en = summarize(full_text)

        try:
            if language != "en":
                title_final = translate_text(title, language)
                summary_final = translate_text(summary_en, language)
            else:
                title_final = title
                summary_final = summary_en
        except:
            title_final = title
            summary_final = summary_en

        # model scores
        model_scores = score_article_with_models(
            article,
            content_recs,
            rgrec_recs,
            muma_recs,
            collab_recs
        )

        # content-based exact match reasons
        content_score, content_reasons = get_content_score(
            article,
            category,
            subcategory,
            search,
            interests
        )

        # =========================
        # ARTICLE-SPECIFIC WHY RECOMMENDED
        # =========================
        if content_reasons:
            reason = content_reasons[0]

        elif model_scores["collab_score"] > 0:
            reason = "Recommended by Collaborative Filtering"

        elif model_scores["rgrec_score"] > 0 and model_scores["muma_score"] > 0:
            reason = "Recommended by RGRec + MUMA"

        elif model_scores["rgrec_score"] > 0:
            reason = "Recommended by RGRec"

        elif model_scores["muma_score"] > 0:
            reason = "Recommended by MUMA"

        elif model_scores["content_score"] > 0:
            reason = "Recommended by Content-Based Filtering"

        else:
            reason = "Trending News"

        news_list.append({
            "title": title_final,
            "summary": summary_final,
            "source": article.get("source", {}).get("name", "Unknown"),
            "image": safe_image(article),
            "url": article.get("url"),
            "score": model_scores["hybrid_score"] + content_score,
            "sentiment": get_sentiment(full_text),
            "reason": reason
        })

    news_list.sort(key=lambda x: x["score"], reverse=True)

    return render_template(
        "index.html",
        news=news_list,
        user=username,
        category=category,
        subcategory=subcategory,
        location=location,
        language=language,
        search=search
    )

# =========================
# LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    msg = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            msg = "All fields required"
        elif " " in username:
            msg = "Spaces not allowed in email"
        elif len(username) < 5:
            msg = "Email too short"
        elif len(password) < 6:
            msg = "Password too short"
        else:
            conn = sqlite3.connect("users.db")
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM users WHERE username=? AND password=?",
                (username, password)
            )
            user = cur.fetchone()
            conn.close()

            if user:
                session["user"] = username
                return redirect(url_for("home"))
            else:
                msg = "Incorrect email or password"

    return render_template("login.html", message=msg)

# =========================
# REGISTER
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    msg = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        interest = request.form.get("interest", "").strip()

        if not username or not password or not confirm_password or not interest:
            msg = "All fields required"
        elif not re.match(r"^[a-zA-Z0-9_.+-]+@gmail\.com$", username):
            msg = "Only Gmail allowed"
        elif " " in username:
            msg = "Spaces not allowed in email"
        elif len(username) < 8:
            msg = "Email too short"
        elif password != confirm_password:
            msg = "Passwords do not match"
        elif len(password) < 6:
            msg = "Password must be at least 6 characters"
        elif not any(char.isupper() for char in password):
            msg = "Password must contain one uppercase letter"
        elif not any(char.islower() for char in password):
            msg = "Password must contain one lowercase letter"
        elif not any(char.isdigit() for char in password):
            msg = "Password must contain one number"
        elif not any(char in "@$!%*#?&" for char in password):
            msg = "Password must contain one special character"
        else:
            conn = sqlite3.connect("users.db")
            cur = conn.cursor()

            cur.execute("SELECT * FROM users WHERE username=?", (username,))
            if cur.fetchone():
                msg = "User already exists"
            else:
                cur.execute(
                    "INSERT INTO users(username,password) VALUES(?,?)",
                    (username, password)
                )
                conn.commit()
                conn.close()

                update_interest(username, interest)
                save_interaction(username, interest)

                msg = "You have successfully registered"
                return redirect(url_for("login"))

            conn.close()

    return render_template("register.html", message=msg)

# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("guest"))

# =========================
# EXPLORE
# =========================
@app.route("/explore")
def explore():
    if "user" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("home"))

# =========================
# TRENDING
# =========================
@app.route("/trending")
def trending():
    query = "breaking news OR top headlines OR latest news OR trending"
    articles = fetch_news(query)

    news_list = []

    for article in articles:
        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")

        news_list.append({
            "title": title,
            "summary": summarize(title + " " + desc),
            "source": article.get("source", {}).get("name", "Unknown"),
            "image": safe_image(article),
            "url": article.get("url"),
            "score": get_popularity_score(title),
            "sentiment": get_sentiment(title + " " + desc),
            "reason": "Trending News"
        })

    news_list.sort(key=lambda x: x["score"], reverse=True)
    return render_template("trending.html", news=news_list)

# =========================
# BOOKMARK SAVE
# =========================
@app.route("/bookmark")
def bookmark():
    if "user" not in session:
        return redirect(url_for("login"))

    title = request.args.get("title", "")
    url = request.args.get("url", "")
    source = request.args.get("source", "")

    if title and url:
        save_bookmark(session["user"], title, url, source)

    return redirect(url_for("home"))

# =========================
# BOOKMARK LIST
# =========================
@app.route("/bookmarks")
def bookmarks():
    if "user" not in session:
        return redirect(url_for("login"))

    user_name = session["user"]
    data = get_bookmarks(user_name)

    return render_template("bookmarks.html", bookmarks=data)

# =========================
# DELETE BOOKMARK
# =========================
@app.route("/delete_bookmark/<int:bookmark_id>")
def delete_bookmark_route(bookmark_id):
    if "user" not in session:
        return redirect(url_for("login"))

    delete_bookmark(bookmark_id)
    return redirect(url_for("bookmarks"))

# =========================
# TRACK
# =========================
@app.route("/track")
def track():
    title = request.args.get("title", "")
    category = request.args.get("category", "").strip()
    subcategory = request.args.get("subcategory", "").strip()
    article_url = request.args.get("url", "")
    source = request.args.get("source", "News Source")

    if "user" in session:
        username = session["user"]

        track_article(username, title, category if category else subcategory)

        if category:
            update_interest(username, category)
            save_interaction(username, category)

        if subcategory:
            update_interest(username, subcategory)
            save_interaction(username, subcategory)

    return redirect(url_for(
        "article_page",
        title=title,
        source=source,
        url=article_url
    ))

# =========================
# ARTICLE PAGE
# =========================
@app.route("/article")
def article_page():
    title = request.args.get("title", "")
    source = request.args.get("source", "News Source")
    article_url = request.args.get("url", "")

    return render_template(
        "article.html",
        title=title,
        source=source,
        article_url=article_url
    )

# =========================
# GUEST
# =========================
@app.route("/guest")
def guest():
    category = request.args.get("category", "")
    subcategory = request.args.get("subcategory", "")
    search = request.args.get("query", "")
    location = request.args.get("location", "world")
    language = request.args.get("language", "en")

    username = session.get("user", "Guest")
    query = build_query(category, subcategory, search, username, location)

    if not query or query.strip() == "":
        query = "technology OR AI OR business OR sports"

    articles = fetch_news(query)

    news_list = []
    for article in articles:
        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")

        if search.strip():
            reason = f"Searched keyword: {search.strip()}"
        elif subcategory.strip():
            reason = f"Selected subcategory: {subcategory.strip()}"
        elif category.strip():
            reason = f"Selected category: {category.strip().title()}"
        else:
            reason = "Trending News"

        news_list.append({
            "title": title,
            "summary": summarize(title + " " + desc),
            "source": article.get("source", {}).get("name", "Unknown"),
            "image": safe_image(article),
            "url": article.get("url"),
            "score": get_popularity_score(title),
            "sentiment": get_sentiment(title + " " + desc),
            "reason": reason
        })

    return render_template(
        "index.html",
        news=news_list,
        user=username,
        category=category,
        subcategory=subcategory,
        location=location,
        language=language,
        search=search
    )

# =========================
# VOICE
# =========================
@app.route("/voice")
def voice():
    try:
        text = request.args.get("text", "").strip()
        lang = request.args.get("lang", "en")

        filename = f"{uuid.uuid4().hex}.mp3"
        path = os.path.join("static", filename)

        gTTS(text=text[:300], lang=lang).save(path)
        return jsonify({"audio": f"/static/{filename}"})

    except Exception as e:
        return jsonify({"error": str(e)})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)