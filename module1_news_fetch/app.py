from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from modules.bookmarks import save_bookmark, get_bookmarks, delete_bookmark
from textblob import TextBlob
from modules.full_article import get_full_article
import requests
import os
import uuid
from gtts import gTTS
import sqlite3
import re
import feedparser
import time
import random
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
from modules.content import get_content_score, contains_term
from modules.recommendation import (
    update_interest,
    get_user_profile,
    get_recent_user_interests,
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

# =========================
# NEWS API KEY
# =========================
NEWS_API_KEY = "9ffdc75e97b241e383f9f2b367de3218"

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
    "technology": """
technology OR tech OR AI OR "artificial intelligence" OR software OR gadgets
OR smartphone OR mobile OR laptop OR startup OR startups OR internet
OR cybersecurity OR app OR apps OR programming OR coding OR Google
OR Microsoft OR Apple OR OpenAI OR chip OR semiconductor
""",
    "business": "business OR economy OR stock market OR startups OR finance",
    "sports": "cricket OR football OR IPL OR sports",
    "health": "health OR fitness OR medicine",
    "entertainment": "movies OR celebrity OR bollywood OR hollywood",
    "science": "science OR space OR NASA OR research",
    "politics": "politics OR government OR election OR parliament OR policy OR minister",
    "other" :"education OR environment OR travel OR lifestyle OR fashion OR food OR automobile OR agriculture OR culture OR wildlife OR tourism OR architecture"
}

# =========================
# NORMALIZE INTEREST
# =========================
def normalize_interest(value):
    if not value:
        return ""
    return str(value).strip()

# =========================
# NORMALIZE TITLE FOR DUPLICATE CHECK
# =========================
def normalize_title(title):
    title = re.sub(r'http\S+', '', title.lower())
    title = re.sub(r'[^a-z0-9 ]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

# =========================
# REMOVE DUPLICATES
# =========================
def deduplicate_articles(articles):
    unique_articles = []
    seen = set()

    for article in articles:
        title = clean_html(article.get("title") or "").strip()
        if not title:
            continue

        norm = normalize_title(title)
        words = norm.split()
        short_key = " ".join(words[:10]) if words else norm

        if norm in seen or short_key in seen:
            continue

        seen.add(norm)
        seen.add(short_key)
        unique_articles.append(article)

    return unique_articles

# =========================
# FILTER ARTICLES BY KEYWORD
# =========================
def filter_articles_by_keyword(articles, keyword):
    keyword = (keyword or "").strip().lower()
    if not keyword:
        return articles

    filtered = []
    for article in articles:
        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")
        full_text = (title + " " + desc).lower()

        if keyword in full_text:
            filtered.append(article)

    return filtered

# =========================
# FILTER ARTICLES BY CATEGORY
# =========================
def filter_articles_by_category(articles, category):
    category = (category or "").strip().lower()
    if not category:
        return articles

    filtered = []
    category_keywords = CATEGORY_MAP.get(category, category)

    for article in articles:
        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")
        full_text = (title + " " + desc).lower()

        matched = False

        if category in full_text:
            matched = True
        else:
            for kw in category_keywords.split(" OR "):
                if kw.strip().lower() in full_text:
                    matched = True
                    break

        if matched:
            filtered.append(article)

    return filtered

# =========================
# BUILD QUERY
# =========================
def build_query(category, subcategory, search, username, location):
    query_parts = []

    search = (search or "").strip()
    category = (category or "").strip()
    subcategory = (subcategory or "").strip()

    if search:
        query_parts.append(search)
        query = " OR ".join(query_parts)

        if location == "india":
            query = f"India AND ({query})"
        elif location == "telangana":
            query = f"(Telangana OR Hyderabad) AND ({query})"

        print("FINAL QUERY =", query)
        return query.strip()

    if username and username != "Guest":
        if category:
            update_interest(username, category)
            save_interaction(username, category)

        if subcategory:
            update_interest(username, subcategory)
            save_interaction(username, subcategory)

    if category:
        cat = category.lower()
        if cat in CATEGORY_MAP:
            query_parts.append(f"({CATEGORY_MAP[cat]})")
        else:
            query_parts.append(category)

    if subcategory:
        query_parts.append(subcategory)

    if username and username != "Guest":
        profile = get_user_profile(username)
        if profile:
            interests = [normalize_interest(i[0]) for i in profile if i and i[0]]

            seen_interest = set()
            clean_interests = []
            for interest in interests:
                low = interest.lower()
                if low not in seen_interest:
                    clean_interests.append(interest)
                    seen_interest.add(low)

            for interest in clean_interests:
                low = interest.lower()
                if low == category.lower() or low == subcategory.lower():
                    continue

                if low in CATEGORY_MAP:
                    query_parts.append(f"({CATEGORY_MAP[low]})")
                else:
                    query_parts.append(interest)

    if not query_parts:
        query_parts = ["technology", "business", "sports"]

    final_parts = []
    seen = set()
    for q in query_parts:
        q_clean = q.strip()
        if q_clean and q_clean.lower() not in seen:
            final_parts.append(q_clean)
            seen.add(q_clean.lower())

    query = " OR ".join(final_parts)

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
def fetch_news(query, language="en"):
    all_articles = []

    # =========================
    # 1) NEWSAPI
    # =========================
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 50,
            "page": 1,
            "apiKey": NEWS_API_KEY
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "").strip()
                desc = a.get("description", "").strip()
                article_url = a.get("url", "").strip()

                if not title or not article_url:
                    continue

                all_articles.append({
                    "title": title,
                    "description": desc,
                    "summary": desc if desc else "No summary available",
                    "url": article_url,
                    "urlToImage": a.get("urlToImage"),
                    "source": {"name": a.get("source", {}).get("name", "NewsAPI")}
                })
    except Exception as e:
        print("NewsAPI Error:", e)

    # =========================
    # 2) RSS FEEDS
    # =========================
    encoded_query = quote_plus(query)

    rss_urls = [
        f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q={encoded_query}+India&hl=en-IN&gl=IN&ceid=IN:en"
    ]

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:30]:
                title = clean_html(getattr(entry, "title", "")).strip()
                link = getattr(entry, "link", "").strip()
                description = clean_html(getattr(entry, "summary", "")).strip()

                if not title or not link:
                    continue

                all_articles.append({
                    "title": title,
                    "description": description,
                    "summary": description if description else "Summary not available",
                    "url": link,
                    "urlToImage": None,
                    "source": {"name": "RSS Feed"}
                })
        except Exception as e:
            print("RSS Error:", e)

    return all_articles

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

def get_unique_profile_interests(username):
    """
    Returns all stored interests/subcategories of user in insertion order without duplicates.
    """
    if not username or username == "Guest":
        return []

    try:
        profile = get_user_profile(username)
        if not profile:
            return []

        interests = []
        seen = set()

        for row in profile:
            if row and row[0]:
                val = str(row[0]).strip().lower()
                if val and val not in seen:
                    interests.append(val)
                    seen.add(val)

        return interests
    except Exception as e:
        print("PROFILE INTEREST ERROR:", e)
        return []
def split_user_interest_history(username):
    """
    Splits user profile into:
    1) broad interests / registration interests
    2) subcategory history selected later while using app
    """
    all_items = get_unique_profile_interests(username)

    broad_defaults = {
        "technology", "business", "sports", "health",
        "entertainment", "science", "politics",
        "music", "movies"
    }

    broad_interests = []
    subcategory_history = []

    for item in all_items:
        low = item.strip().lower()

        if low in broad_defaults:
            broad_interests.append(low)
        else:
            subcategory_history.append(low)

    return broad_interests, subcategory_history

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

def score_article_with_models(
    article,
    content_recs,
    rgrec_recs,
    muma_recs,
    collab_recs,
    selected_category="",
    selected_subcategory="",
    search_query=""
):
    title = clean_html(article.get("title") or "").lower()
    desc = clean_html(article.get("description") or "").lower()
    full_text = title + " " + desc

    content_score = 0
    rgrec_score = 0
    muma_score = 0
    collab_score = 0
    selected_score = 0
    search_score = 0

    if search_query and contains_term(search_query, full_text):
        search_score += 30

    if selected_category and contains_term(selected_category, full_text):
        selected_score += 15

    if selected_subcategory and contains_term(selected_subcategory, full_text):
        selected_score += 20

    for kw in content_recs:
        if kw and contains_term(kw, full_text):
            content_score += 2

    for kw in rgrec_recs:
        if kw and contains_term(kw, full_text):
            rgrec_score += 2

    for kw in muma_recs:
        if kw and contains_term(kw, full_text):
            muma_score += 2

    for kw in collab_recs:
        if kw and contains_term(kw, full_text):
            collab_score += 2

    popularity_score = get_popularity_score(article.get("title", ""))

    hybrid_score = (
        search_score +
        selected_score +
        content_score +
        rgrec_score +
        muma_score +
        collab_score +
        (0.5 * popularity_score)
    )

    return {
        "search_score": search_score,
        "selected_score": selected_score,
        "content_score": content_score,
        "rgrec_score": rgrec_score,
        "muma_score": muma_score,
        "collab_score": collab_score,
        "popularity_score": popularity_score,
        "hybrid_score": hybrid_score
    }

# =========================
# CORRECT ARTICLE REASON
# =========================
def get_article_reason(
    article,
    model_scores,
    content_reasons,
    selected_category="",
    selected_subcategory="",
    search_query="",
    content_recs=None,
    rgrec_recs=None,
    muma_recs=None,
    collab_recs=None
):
    if content_recs is None:
        content_recs = []
    if rgrec_recs is None:
        rgrec_recs = []
    if muma_recs is None:
        muma_recs = []
    if collab_recs is None:
        collab_recs = []

    title = clean_html(article.get("title") or "")
    desc = clean_html(article.get("description") or "")
    full_text = (title + " " + desc).lower()

    if search_query and contains_term(search_query, full_text):
        return f"Matched your search: {search_query}"

    if selected_subcategory and contains_term(selected_subcategory, full_text):
        return f"Matched selected subcategory: {selected_subcategory}"

    if selected_category and contains_term(selected_category, full_text):
        return f"Matched selected category: {selected_category}"

    if content_reasons:
        return content_reasons[0]

    for kw in collab_recs:
        if kw and contains_term(kw, full_text):
            return f"Recommended because users with similar interests also read topics like: {kw}"

    matched_rgrec = None
    matched_muma = None

    for kw in rgrec_recs:
        if kw and contains_term(kw, full_text):
            matched_rgrec = kw
            break

    for kw in muma_recs:
        if kw and contains_term(kw, full_text):
            matched_muma = kw
            break

    if matched_rgrec and matched_muma:
        return f"Matched your interest '{matched_rgrec}' and related topic '{matched_muma}'"

    if matched_muma:
        return f"Matched related topic from your interests: {matched_muma}"

    if matched_rgrec:
        return f"Matched your stored interest: {matched_rgrec}"

    for kw in content_recs:
        if kw and contains_term(kw, full_text):
            return f"Matched your previous interest: {kw}"

    return "Trending News"

# =========================
# TRENDING QUERY ROTATION HELPER
# =========================
def get_trending_query():
    trending_queries = [
        "India AND (breaking news OR top headlines OR latest news OR trending)",
        "India AND (top headlines OR viral news OR current affairs)",
        "India AND (latest politics OR latest technology OR latest business OR latest sports)",
        "India AND (today news OR trending India OR top stories)",
        "India AND (popular news OR live updates OR national news)"
    ]
    return random.choice(trending_queries)

# =========================
# ROOT
# =========================
@app.route("/")
def index():
    if session.get("user"):
        return redirect(url_for("home"))
    else:
        return redirect(url_for("guest"))

# =========================
# STRICT TITLE MATCH ONLY
# =========================
def title_matches_keyword(article, keyword):
    if not keyword:
        return True

    keyword = keyword.strip().lower()
    title = clean_html(article.get("title") or "").strip().lower()

    if not title:
        return False

    if keyword == "ai":
        if re.search(r"\bai\b", title) or "artificial intelligence" in title:
            return True
        return False

    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, title) is not None

# =========================
# STRICT CATEGORY + SUBCATEGORY FILTER
# =========================
def filter_articles_strict_for_subcategory(articles, category, subcategory):
    filtered = []

    category = (category or "").strip().lower()
    subcategory = (subcategory or "").strip().lower()

    category_keywords = []
    if category:
        cat_query = CATEGORY_MAP.get(category, category)
        category_keywords = [x.strip().lower() for x in cat_query.split(" OR ")]

    for article in articles:
        title = clean_html(article.get("title") or "").strip()
        desc = clean_html(article.get("description") or "").strip()

        if not title:
            continue

        full_text = (title + " " + desc).lower()

        category_ok = True
        if category:
            category_ok = False

            if category in full_text:
                category_ok = True
            else:
                for kw in category_keywords:
                    if kw and kw in full_text:
                        category_ok = True
                        break

        subcategory_ok = title_matches_keyword(article, subcategory)

        if category_ok and subcategory_ok:
            filtered.append(article)

    return filtered

# =========================
# FETCH ARTICLES FOR SINGLE INTEREST
# =========================
# =========================
# FETCH ARTICLES FOR SINGLE INTEREST
# =========================
def fetch_interest_articles(interest, location, category_hint=""):
    """
    Used in logged-in recommendation logic.

    If interest is a broad registered category like technology/business/health/sports/politics,
    fetch using the full CATEGORY_MAP query so the user gets all related news
    (AI, cybersecurity, startups, healthcare, cricket, finance, etc.)
    instead of only articles containing the literal category word.

    If interest is a subcategory/custom topic, fetch using that exact interest.
    """
    interest = (interest or "").strip().lower()
    category_hint = (category_hint or "").strip().lower()

    if not interest:
        return []

    # ---------------------------------------------------------
    # CASE A: broad registered interest like technology/business/etc.
    # ---------------------------------------------------------
    if interest in CATEGORY_MAP:
        base_query = f"({CATEGORY_MAP[interest]})"

    # ---------------------------------------------------------
    # CASE B: subcategory/custom topic
    # ---------------------------------------------------------
    else:
        if category_hint:
            # if a category hint is given, keep both
            if category_hint in CATEGORY_MAP:
                base_query = f'"{interest}" AND ({CATEGORY_MAP[category_hint]})'
            else:
                base_query = f'"{interest}" AND ({category_hint})'
        else:
            base_query = f'"{interest}"'

    # ---------------------------------------------------------
    # apply location
    # ---------------------------------------------------------
    if location == "india":
        query = f"India AND ({base_query})"
    elif location == "telangana":
        query = f"(Telangana OR Hyderabad) AND ({base_query})"
    else:
        query = base_query

    print("INTEREST QUERY =", query)

    articles = fetch_news(query)
    articles = filter_telangana(articles, location)
    articles = deduplicate_articles(articles)

    # ---------------------------------------------------------
    # If category_hint is passed (subcategory case), keep strict filtering
    # ---------------------------------------------------------
    if category_hint:
        strict_articles = filter_articles_strict_for_subcategory(articles, category_hint, interest)
        if strict_articles:
            return strict_articles

    # ---------------------------------------------------------
    # For broad registered interests:
    # keep article if it matches ANY keyword of that category
    # ---------------------------------------------------------
    if interest in CATEGORY_MAP:
        filtered = []
        for article in articles:
            if article_matches_registered_interest(article, interest):
                filtered.append(article)

        if filtered:
            return deduplicate_articles(filtered)

    # ---------------------------------------------------------
    # For non-category interest, use normal contains_term match
    # ---------------------------------------------------------
    keyword_filtered = []
    for article in articles:
        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")
        text = (title + " " + desc).lower()

        if contains_term(interest, text):
            keyword_filtered.append(article)

    if keyword_filtered:
        return deduplicate_articles(keyword_filtered)

    return articles

def fetch_strict_subcategory_articles(subcategory, location, category=""):
    """
    Fetch news for a subcategory and keep only those articles
    whose TITLE contains the subcategory term.
    """
    subcategory = (subcategory or "").strip()
    category = (category or "").strip()

    if not subcategory:
        return []

    if category:
        query = f'"{subcategory}" AND ({category})'
    else:
        query = f'"{subcategory}"'

    if location == "india":
        query = f"India AND ({query})"
    elif location == "telangana":
        query = f"(Telangana OR Hyderabad) AND ({query})"

    print("STRICT SUBCATEGORY FETCH QUERY =", query)

    articles = fetch_news(query)
    articles = filter_telangana(articles, location)
    articles = deduplicate_articles(articles)

    strict = []
    for article in articles:
        if title_matches_keyword(article, subcategory):
            strict.append(article)

    # if category is also selected, ensure category match too
    if category:
        strict = filter_articles_strict_for_subcategory(strict, category, subcategory)

    return deduplicate_articles(strict)

# =========================
# BUILD MIXED ARTICLES FOR LOGGED-IN USER
# 60% current selected subcategory + 40% recent previous interests
# =========================
def build_logged_in_mixed_articles(username, category, subcategory, location, total_needed=60):
    """
    CASE 2 + CASE 3 logic

    CASE 2: New user selecting subcategory
        60% current selected subcategory
        40% registered interests only

    CASE 3: Past user selecting subcategory
        60% current selected subcategory (title must contain subcategory)
        40% previous subcategory history only (title must contain those subcategory names)
    """

    main_count = int(round(total_needed * 0.60))
    old_count = total_needed - main_count

    # -----------------------------------------
    # Get user profile split
    # -----------------------------------------
    broad_interests, subcategory_history = split_user_interest_history(username)

    selected_values = {
        (category or "").strip().lower(),
        (subcategory or "").strip().lower()
    }

    # remove currently selected values from past history
    clean_sub_history = []
    seen = set()
    for item in subcategory_history:
        low = item.strip().lower()
        if not low or low in selected_values:
            continue
        if low not in seen:
            clean_sub_history.append(low)
            seen.add(low)

    # remove current subcategory/category from broad interests too
    clean_broad_interests = []
    seen_broad = set()
    for item in broad_interests:
        low = item.strip().lower()
        if not low or low in selected_values:
            continue
        if low not in seen_broad:
            clean_broad_interests.append(low)
            seen_broad.add(low)

    # -----------------------------------------
    # Decide whether user is NEW or OLD
    # -----------------------------------------
    # NEW USER -> no subcategory history yet
    # OLD USER -> has past subcategory history
    is_new_user = len(clean_sub_history) == 0

    # =========================================================
    # 1) 60% CURRENT SELECTED SUBCATEGORY NEWS
    # title should contain selected subcategory
    # =========================================================
    current_articles = fetch_strict_subcategory_articles(
        subcategory=subcategory,
        location=location,
        category=category
    )

    # fallback if strict is too less
    if len(current_articles) < main_count:
        fallback = fetch_interest_articles(subcategory, location, category)
        strict_fallback = []
        for article in fallback:
            if title_matches_keyword(article, subcategory):
                strict_fallback.append(article)

        current_articles = deduplicate_articles(current_articles + strict_fallback)

    current_articles = deduplicate_articles(current_articles)[:main_count]

    # =========================================================
    # 2) 40% MIX SOURCE
    # NEW USER  -> registered broad interests only
    # OLD USER  -> previous subcategory history only
    # =========================================================
    old_articles_pool = []
    recent_interest_set = set()

    if is_new_user:
        # CASE 2: use registration interests only
        source_list = clean_broad_interests[:4]
    else:
        # CASE 3: use previous subcategory history only
        source_list = clean_sub_history[:4]

    recent_interest_set = set(source_list)

    if source_list and old_count > 0:
        per_interest = old_count // len(source_list)
        extra = old_count % len(source_list)

        for idx, old_interest in enumerate(source_list):
            take_count = per_interest + (1 if idx < extra else 0)

            # -------------------------------------
            # CASE 2 (new user): broad interests
            # -------------------------------------
            if is_new_user:
                old_articles = fetch_interest_articles(old_interest, location)

                # strict keyword filtering so unrelated news won't come
                strict_old = []
                for article in old_articles:
                    title = clean_html(article.get("title") or "")
                    desc = clean_html(article.get("description") or "")
                    text = (title + " " + desc).lower()

                    if contains_term(old_interest, text):
                        strict_old.append(article)

                old_articles = deduplicate_articles(strict_old)

            # -------------------------------------
            # CASE 3 (old user): past subcategory history
            # title must contain subcategory name
            # -------------------------------------
            else:
                old_articles = fetch_strict_subcategory_articles(
                    subcategory=old_interest,
                    location=location
                )

            old_articles_pool.extend(old_articles[:take_count])

    old_articles_pool = deduplicate_articles(old_articles_pool)

    # =========================================================
    # 3) REMOVE DUPLICATES AGAINST CURRENT ARTICLES
    # =========================================================
    current_titles = set(
        normalize_title(clean_html(a.get("title") or ""))
        for a in current_articles
        if clean_html(a.get("title") or "").strip()
    )

    filtered_old_articles = []
    seen_old = set()

    for article in old_articles_pool:
        title = clean_html(article.get("title") or "").strip()
        norm_title = normalize_title(title)

        if not norm_title:
            continue
        if norm_title in current_titles:
            continue
        if norm_title in seen_old:
            continue

        filtered_old_articles.append(article)
        seen_old.add(norm_title)

    filtered_old_articles = filtered_old_articles[:old_count]

    # =========================================================
    # 4) COMBINE 60% + 40%
    # =========================================================
    mixed_articles = current_articles + filtered_old_articles
    mixed_articles = deduplicate_articles(mixed_articles)

    # =========================================================
    # 5) FILL SHORTAGE
    # =========================================================
    if len(mixed_articles) < total_needed:
        existing_titles = set(
            normalize_title(clean_html(a.get("title") or ""))
            for a in mixed_articles
            if clean_html(a.get("title") or "").strip()
        )

        # fill from current selected subcategory first
        extra_current = fetch_strict_subcategory_articles(subcategory, location, category)
        for article in extra_current:
            title = clean_html(article.get("title") or "").strip()
            norm_title = normalize_title(title)

            if not norm_title or norm_title in existing_titles:
                continue

            mixed_articles.append(article)
            existing_titles.add(norm_title)

            if len(mixed_articles) >= total_needed:
                break

        # fill from old source list
        if len(mixed_articles) < total_needed:
            for old_interest in source_list:
                if is_new_user:
                    extra_old = fetch_interest_articles(old_interest, location)
                    strict_extra = []
                    for article in extra_old:
                        title = clean_html(article.get("title") or "")
                        desc = clean_html(article.get("description") or "")
                        text = (title + " " + desc).lower()
                        if contains_term(old_interest, text):
                            strict_extra.append(article)
                    extra_old = deduplicate_articles(strict_extra)
                else:
                    extra_old = fetch_strict_subcategory_articles(old_interest, location)

                for article in extra_old:
                    title = clean_html(article.get("title") or "").strip()
                    norm_title = normalize_title(title)

                    if not norm_title or norm_title in existing_titles:
                        continue

                    mixed_articles.append(article)
                    existing_titles.add(norm_title)

                    if len(mixed_articles) >= total_needed:
                        break

                if len(mixed_articles) >= total_needed:
                    break

    return mixed_articles[:total_needed], recent_interest_set, is_new_user
# =========================
# CASE 1: BALANCED HOME ARTICLES FOR REGISTERED INTERESTS
# Equal distribution across selected interests
# =========================
def build_balanced_home_articles(username, location, total_needed=15):
    """
    CASE 1:
    Logged-in user opens home without category/subcategory/search.
    Show only registered/broad interests with equal distribution.

    Example:
    1 interest  -> 15
    2 interests -> 8 + 7
    3 interests -> 5 + 5 + 5
    4 interests -> 4 + 4 + 4 + 3
    """

    broad_interests, _ = split_user_interest_history(username)

    # Use broad/registered interests first.
    # If none found, fallback to all stored interests.
    base_interests = broad_interests if broad_interests else get_unique_profile_interests(username)

    if not base_interests:
        return []

    # remove duplicates while preserving order
    clean_interests = []
    seen = set()
    for interest in base_interests:
        low = (interest or "").strip().lower()
        if low and low not in seen:
            clean_interests.append(low)
            seen.add(low)

    base_interests = clean_interests

    n = len(base_interests)
    if n == 0:
        return []

    # -------------------------
    # Equal quota distribution
    # -------------------------
    base_quota = total_needed // n
    remainder = total_needed % n

    # Example for 15 articles:
    # n=2 -> 7 each + 1 extra => [8,7]
    # n=3 -> 5 each => [5,5,5]
    # n=4 -> 3 each + 3 extra => [4,4,4,3]
    quotas = []
    for i in range(n):
        q = base_quota + (1 if i < remainder else 0)
        quotas.append(q)

    print("CASE 1 BASE INTERESTS =", base_interests)
    print("CASE 1 QUOTAS =", quotas)

    all_articles = []
    seen_titles = set()

    # ------------------------------------------------
    # Fetch each interest separately and take its quota
    # ------------------------------------------------
    for idx, interest in enumerate(base_interests):
        needed = quotas[idx]
        if needed <= 0:
            continue

        interest_articles = fetch_interest_articles(interest, location)

        # strict filter for relevance
        strict_interest_articles = []
        for article in interest_articles:
            title = clean_html(article.get("title") or "")
            desc = clean_html(article.get("description") or "")
            text = (title + " " + desc).lower()

            # for broad categories like technology/business/sports,
            # contains_term should help keep related articles
            if contains_term(interest, text):
                strict_interest_articles.append(article)

        strict_interest_articles = deduplicate_articles(strict_interest_articles)

        taken = 0
        for article in strict_interest_articles:
            title = clean_html(article.get("title") or "").strip()
            norm_title = normalize_title(title)

            if not title or norm_title in seen_titles:
                continue

            seen_titles.add(norm_title)
            all_articles.append(article)
            taken += 1

            if taken >= needed:
                break

    # ------------------------------------------------
    # FILL SHORTAGE:
    # if some interest didn't have enough news, fill from
    # remaining articles of all interests without breaking relevance
    # ------------------------------------------------
    if len(all_articles) < total_needed:
        print("CASE 1 SHORTAGE FILL STARTED")

        for interest in base_interests:
    # fetch only this interest's news
            interest_articles = fetch_interest_articles(interest, location)

    # strict filtering for registered interests:
    # broad categories use CATEGORY_MAP keywords
            strict_interest_articles = []
            for article in interest_articles:
                if article_matches_registered_interest(article, interest):
                    strict_interest_articles.append(article)

            for article in strict_interest_articles:
                title = clean_html(article.get("title") or "").strip()
                norm_title = normalize_title(title)

                if not title or norm_title in seen_titles:
                   continue

                seen_titles.add(norm_title)
                articles.append(article)

    return deduplicate_articles(all_articles)[:total_needed]

# =========================
# CATEGORY KEYWORD PARSER
# =========================
def get_category_keywords_from_map(category_name):
    """
    Convert CATEGORY_MAP query string into clean keyword list.
    Example:
    technology -> ["technology", "tech", "ai", "artificial intelligence", ...]
    """
    category_name = (category_name or "").strip().lower()
    if not category_name:
        return []

    raw = CATEGORY_MAP.get(category_name, "")
    if not raw:
        return [category_name]

    keywords = []
    for part in raw.split("OR"):
        kw = part.strip().strip('"').strip("'").lower()
        if kw:
            keywords.append(kw)

    # remove duplicates while preserving order
    seen = set()
    clean_keywords = []
    for kw in keywords:
        if kw not in seen:
            clean_keywords.append(kw)
            seen.add(kw)

    return clean_keywords


# =========================
# CHECK ARTICLE MATCHES A BROAD INTEREST
# =========================
def article_matches_registered_interest(article, interest):
    """
    Used ONLY for registered interests on home page with no selection.
    Broad interests like technology/health/sports/business/politics
    should match ANY keyword inside CATEGORY_MAP, not just the word itself.
    """
    interest = (interest or "").strip().lower()
    if not interest:
        return False

    title = clean_html(article.get("title") or "")
    desc = clean_html(article.get("description") or "")
    text = (title + " " + desc).lower()

    # If it is a broad category from CATEGORY_MAP, match any keyword in that category
    if interest in CATEGORY_MAP:
        keywords = get_category_keywords_from_map(interest)
        for kw in keywords:
            if kw and kw in text:
                return True
        return False

    # Otherwise normal match for subcategory / custom interest
    return contains_term(interest, text)

# =========================
# HOME
# =========================
@app.route("/home")
def home():
    username = session.get("user", "Guest")

    category = request.args.get("category", "").strip()
    subcategory = request.args.get("subcategory", "").strip()
    search = request.args.get("query", "").strip()
    location = request.args.get("location", "india")
    language = request.args.get("language", "en")

    print("CATEGORY =", category)
    print("SUBCATEGORY =", subcategory)
    print("SEARCH =", search)
    print("LOCATION =", location)

    recent_interest_set = set()
    is_new_user_mix = False

    # =========================================================
    # 1) LOGGED-IN USER + SUBCATEGORY SELECTED
    # 60% selected subcategory + 40% recent interests
    # =========================================================
    is_new_user_mix = False

    if username != "Guest" and subcategory and not search:
       if category:
        update_interest(username, category)
        save_interaction(username, category)

       if subcategory:
        update_interest(username, subcategory)
        save_interaction(username, subcategory)

       articles, recent_interest_set, is_new_user_mix = build_logged_in_mixed_articles(
        username=username,
        category=category,
        subcategory=subcategory,
        location=location,
        total_needed=60
    )

    # =========================================================
    # 2) GUEST / NORMAL SUBCATEGORY FILTER
    # =========================================================
    elif subcategory and not search:
        if category:
            sub_query = f'"{subcategory}" AND ({category})'
        else:
            sub_query = f'"{subcategory}"'

        if location == "india":
            sub_query = f"India AND ({sub_query})"
        elif location == "telangana":
            sub_query = f"(Telangana OR Hyderabad) AND ({sub_query})"

        print("STRICT SUBCATEGORY QUERY =", sub_query)

        articles = fetch_news(sub_query)
        articles = filter_telangana(articles, location)
        articles = deduplicate_articles(articles)

        articles = filter_articles_strict_for_subcategory(
            articles,
            category,
            subcategory
        )

    # =========================================================
    # 3) ALL OTHER CASES
    # =========================================================
    else:
            # Search has highest priority
     if search:
        query = build_query(category, subcategory, search, username, location)
        print("QUERY =", query)

        articles = fetch_news(query)
        articles = filter_telangana(articles, location)
        articles = deduplicate_articles(articles)

     elif username != "Guest" and not category and not subcategory:
    # -----------------------------------------------------
    # CASE 1:
    # Logged-in user + no category + no subcategory + no search
    # -> show only registered interests with equal distribution
    # -----------------------------------------------------
      
        broad_interests, subcategory_history = split_user_interest_history(username)

    # CASE 1:
    # For home without selection, show only registered/broad interests.
    # If no broad interests exist, then fallback to all stored interests.
        base_interests = broad_interests if broad_interests else get_unique_profile_interests(username)

        if base_interests:
           TOTAL_NEWS = 15
           articles = []
           seen_titles = set()

        # remove duplicates from interests while preserving order
           clean_interests = []
           seen_interests = set()
           for interest in base_interests:
               low = interest.strip().lower()
               if low and low not in seen_interests:
                  clean_interests.append(low)
                  seen_interests.add(low)

           interest_count = len(clean_interests)

        # equal distribution logic
        # 1 interest -> 15
        # 2 interests -> 8 + 7
        # 3 interests -> 5 + 5 + 5
        # 4 interests -> 4 + 4 + 4 + 3
           base_quota = TOTAL_NEWS // interest_count
           extra = TOTAL_NEWS % interest_count

           for idx, interest in enumerate(clean_interests):
               quota = base_quota + (1 if idx < extra else 0)

            # fetch only this interest's news
               interest_articles = fetch_interest_articles(interest, location)

            # strict filtering:
            # if broad interest like technology/business/sports/etc,
            # use all keywords from CATEGORY_MAP
               strict_interest_articles = []
               for article in interest_articles:
                   if article_matches_registered_interest(article, interest):
                      strict_interest_articles.append(article)

               strict_interest_articles = deduplicate_articles(strict_interest_articles)

               taken = 0
               for article in strict_interest_articles:
                   title = clean_html(article.get("title") or "").strip()
                   norm_title = normalize_title(title)

                   if not title or norm_title in seen_titles:
                      continue

                   seen_titles.add(norm_title)
                   articles.append(article)
                   taken += 1

                   if taken >= quota:
                      break

        # fill shortage if some interest had fewer articles
           if len(articles) < TOTAL_NEWS:
              for interest in clean_interests:
                  extra_articles = fetch_interest_articles(interest, location)

                  extra_filtered = []
                  for article in extra_articles:
                      if article_matches_registered_interest(article, interest):
                         extra_filtered.append(article)

                  extra_filtered = deduplicate_articles(extra_filtered)

                  for article in extra_filtered:
                      title = clean_html(article.get("title") or "").strip()
                      norm_title = normalize_title(title)

                      if not title or norm_title in seen_titles:
                        continue

                      seen_titles.add(norm_title)
                      articles.append(article)

                      if len(articles) >= TOTAL_NEWS:
                         break

                  if len(articles) >= TOTAL_NEWS:
                     break

              articles = deduplicate_articles(articles)[:TOTAL_NEWS]

        else:
            query = build_query(category, subcategory, search, username, location)
            print("QUERY =", query)
            articles = fetch_news(query)
            articles = filter_telangana(articles, location)
            articles = deduplicate_articles(articles)
        

    # =========================================================
    # RECOMMENDATION SIGNALS / SCORING
    # =========================================================
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

    for article in articles[:60]:
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

        content_score, content_reasons = get_content_score(
            article,
            category,
            subcategory,
            search,
            interests
        )

        model_scores = score_article_with_models(
            article,
            content_recs,
            rgrec_recs,
            muma_recs,
            collab_recs,
            selected_category=category,
            selected_subcategory=subcategory,
            search_query=search
        )

        final_score = model_scores["hybrid_score"] + content_score

        reason = get_article_reason(
            article,
            model_scores,
            content_reasons,
            selected_category=category,
            selected_subcategory=subcategory,
            search_query=search,
            content_recs=content_recs,
            rgrec_recs=rgrec_recs,
            muma_recs=muma_recs,
            collab_recs=collab_recs
        )

        # if this article belongs to recent-interest mix, show clearer reason
        if username != "Guest" and subcategory and not search:
           article_text = (title + " " + desc).lower()

           matched_old_interest = None
           for old_interest in recent_interest_set:
               if old_interest and contains_term(old_interest, article_text):
                  matched_old_interest = old_interest
                  break

           if matched_old_interest:
               if is_new_user_mix:
                  reason = f"From your registered interest: {matched_old_interest}"
               else:
                  reason = f"From your past selected subcategory: {matched_old_interest}"
           elif contains_term(subcategory, article_text):
              reason = f"Matched selected subcategory: {subcategory}"

        news_list.append({
            "title": title_final,
            "summary": summary_final,
            "source": article.get("source", {}).get("name", "Unknown"),
            "image": safe_image(article),
            "url": article.get("url"),
            "score": final_score,
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
        selected_interests = request.form.getlist("interest")

        if not username or not password or not confirm_password:
            msg = "All fields required"
        elif not selected_interests:
            msg = "Please select at least one interest"
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
                conn.close()
            else:
                cur.execute(
                    "INSERT INTO users(username,password) VALUES(?,?)",
                    (username, password)
                )
                conn.commit()
                conn.close()

                for interest in selected_interests:
                    update_interest(username, interest)
                    save_interaction(username, interest)

                return redirect(url_for("login"))

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
    username = session.get("user", "Guest")

    trending_queries = [
        "India AND (breaking news OR top headlines OR latest news OR trending)",
        "India AND (technology OR AI OR startups OR gadgets)",
        "India AND (business OR economy OR stock market OR finance)",
        "India AND (sports OR cricket OR football OR IPL)",
        "India AND (health OR medicine OR fitness OR wellness)",
        "India AND (politics OR election OR government OR parliament)"
    ]

    session_key = f"trending_index_{username}"
    current_index = session.get(session_key, 0)
    query = trending_queries[current_index % len(trending_queries)]
    session[session_key] = (current_index + 1) % len(trending_queries)

    print("TRENDING QUERY =", query)

    articles = fetch_news(query)
    articles = deduplicate_articles(articles)

    if not articles:
        fallback_query = "India AND (breaking news OR top headlines OR latest news)"
        print("TRENDING FALLBACK QUERY =", fallback_query)
        articles = fetch_news(fallback_query)
        articles = deduplicate_articles(articles)

    news_list = []

    for article in articles[:60]:
        title = clean_html(article.get("title") or "").strip()
        desc = clean_html(article.get("description") or "").strip()

        if not title:
            continue

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

    if not news_list:
        fallback_query = "technology OR business OR sports"
        print("TRENDING SECOND FALLBACK QUERY =", fallback_query)
        articles = fetch_news(fallback_query)
        articles = deduplicate_articles(articles)

        for article in articles[:60]:
            title = clean_html(article.get("title") or "").strip()
            desc = clean_html(article.get("description") or "").strip()

            if not title:
                continue

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

    title = request.args.get("title","")
    source = request.args.get("source","News Source")
    article_url = request.args.get("url","")

    article = get_full_article(article_url)

    if article:
        summary = summarize(article["text"])
        full_text = article["text"]
    else:
        summary = "Unable to fetch article."
        full_text = ""

    return render_template(
        "article.html",
        title=title,
        source=source,
        article_url=article_url,
        summary=summary,
        full_text=full_text
    )

# =========================
# GUEST
# =========================
@app.route("/guest")
def guest():
    if session.get("user"):
        return redirect(url_for("home"))
    category = request.args.get("category", "").strip()
    subcategory = request.args.get("subcategory", "").strip()
    search = request.args.get("query", "").strip()
    location = request.args.get("location", "india")
    language = request.args.get("language", "en")

    username = "Guest"
    MAX_NEWS = 60

    def with_location(q):
        q = (q or "").strip()
        if not q:
            return ""
        if location == "india":
            return f"India AND ({q})"
        elif location == "telangana":
            return f"(Telangana OR Hyderabad) AND ({q})"
        return q

    def get_category_query(cat):
        cat = (cat or "").strip().lower()

        category_queries = {
            "technology": """
technology OR tech OR AI OR "artificial intelligence" OR software
OR gadgets OR smartphone OR mobile OR laptop OR startup OR startups
OR internet OR cybersecurity OR app OR apps OR programming OR coding
OR Google OR Microsoft OR Apple OR OpenAI OR chip OR semiconductor
""",
            "business": """
business OR economy OR finance OR market OR stock OR startup
OR company OR investment OR banking OR revenue OR trade
""",
            "sports": """
sports OR cricket OR football OR IPL OR world cup OR tennis
OR match OR player OR tournament OR score
""",
            "health": """
health OR fitness OR medicine OR hospital OR doctor OR disease
OR treatment OR wellness OR healthcare
""",
            "entertainment": """
movies OR film OR cinema OR actor OR actress OR celebrity
OR bollywood OR hollywood OR music OR show OR web series
""",
            "science": """
science OR research OR space OR NASA OR discovery OR scientist
OR experiment OR innovation
""",
            "politics": """
politics OR government OR election OR minister OR parliament
OR policy OR congress OR bjp OR chief minister
""" ,
"other": """
education OR environment OR travel OR lifestyle
OR fashion OR food OR automobile
OR agriculture OR culture OR wildlife
OR tourism OR architecture
""",
        }

        return category_queries.get(cat, cat)

    def get_category_keywords(cat):
        cat = (cat or "").strip().lower()

        category_keywords_map = {
            "technology": [
                "technology", "tech", "ai", "artificial intelligence",
                "software", "gadgets", "smartphone", "mobile", "laptop",
                "startup", "startups", "internet", "cybersecurity", "app",
                "apps", "programming", "coding", "google", "microsoft",
                "apple", "openai", "chip", "semiconductor"
            ],
            "business": [
                "business", "economy", "finance", "market", "stock",
                "startup", "company", "investment", "banking", "revenue"
            ],
            "sports": [
                "sports", "cricket", "football", "ipl", "world cup",
                "tennis", "match", "player", "tournament", "score"
            ],
            "health": [
                "health", "fitness", "medicine", "hospital", "doctor",
                "disease", "treatment", "wellness", "healthcare"
            ],
            "entertainment": [
                "movie", "movies", "film", "cinema", "actor", "actress",
                "celebrity", "bollywood", "hollywood", "music", "show"
            ],
            "science": [
                "science", "research", "space", "nasa", "discovery",
                "scientist", "experiment", "innovation"
            ],
            "politics": [
                "politics", "government", "election", "minister",
                "parliament", "policy", "congress", "bjp", "chief minister"
            ],
            "other": [
    "education",
    "environment",
    "travel",
    "lifestyle",
    "fashion",
    "food",
    "automobile",
    "agriculture",
    "culture",
    "wildlife",
    "tourism",
    "architecture"
],
        }

        return category_keywords_map.get(cat, [cat])

    def article_matches_keyword(article, keyword):
        if not keyword:
            return True

        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")
        text = (title + " " + desc).lower()

        keyword = keyword.strip().lower()

        if keyword in text:
            return True

        if keyword == "ai":
            if re.search(r"\bai\b", text) or "artificial intelligence" in text:
                return True

        return False

    def article_matches_category(article, category):
        if not category:
            return True

        title = clean_html(article.get("title") or "")
        desc = clean_html(article.get("description") or "")
        text = (title + " " + desc).lower()

        keywords = get_category_keywords(category)

        for kw in keywords:
            if kw.lower() in text:
                return True

        return False

    def build_news_list(articles, reason_text, match_keyword=None, match_category=None, limit=20):
        news = []
        seen_titles = set()

        articles = deduplicate_articles(articles)

        for article in articles:
            title = clean_html(article.get("title") or "").strip()
            desc = clean_html(article.get("description") or "").strip()

            if not title:
                continue

            if match_keyword and not article_matches_keyword(article, match_keyword):
                continue

            if match_category and not article_matches_category(article, match_category):
                continue

            norm_title = normalize_title(title)
            if norm_title in seen_titles:
                continue
            seen_titles.add(norm_title)

            summary_en = summarize(title + " " + desc)

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

            news.append({
                "title": title_final,
                "summary": summary_final,
                "source": article.get("source", {}).get("name", "Unknown"),
                "image": safe_image(article),
                "url": article.get("url"),
                "score": get_popularity_score(title),
                "sentiment": get_sentiment(title + " " + desc),
                "reason": reason_text
            })

            if len(news) >= limit:
                return news

        for article in articles:
            if len(news) >= limit:
                break

            title = clean_html(article.get("title") or "").strip()
            desc = clean_html(article.get("description") or "").strip()

            if not title:
                continue

            norm_title = normalize_title(title)
            if norm_title in seen_titles:
                continue
            seen_titles.add(norm_title)

            summary_en = summarize(title + " " + desc)

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

            news.append({
                "title": title_final,
                "summary": summary_final,
                "source": article.get("source", {}).get("name", "Unknown"),
                "image": safe_image(article),
                "url": article.get("url"),
                "score": get_popularity_score(title),
                "sentiment": get_sentiment(title + " " + desc),
                "reason": reason_text
            })

        return news[:limit]

    news_list = []

    if search:
        query = with_location(search)
        print("GUEST SEARCH QUERY =", query)

        articles = fetch_news(query)
        articles = filter_telangana(articles, location)

        news_list = build_news_list(
            articles=articles,
            reason_text=f"Matched your search: {search}",
            match_keyword=search,
            limit=MAX_NEWS
        )

    elif subcategory:
        if category:
            query = f'"{subcategory}" AND ({category})'
        else:
            query = f'"{subcategory}"'

        query = with_location(query)
        print("GUEST SUBCATEGORY QUERY =", query)

        articles = fetch_news(query)
        articles = filter_telangana(articles, location)
        articles = deduplicate_articles(articles)

        strict_articles = filter_articles_strict_for_subcategory(
            articles,
            category,
            subcategory
        )

        news_list = build_news_list(
            articles=strict_articles if strict_articles else articles,
            reason_text=f"Matched selected subcategory: {subcategory}",
            match_keyword=subcategory,
            match_category=category if category else None,
            limit=MAX_NEWS
        )

    elif category:
        category_query = get_category_query(category)
        query = with_location(category_query)
        print("GUEST CATEGORY QUERY =", query)

        articles = fetch_news(query)
        articles = filter_telangana(articles, location)

        news_list = build_news_list(
            articles=articles,
            reason_text=f"Matched selected category: {category}",
            match_category=category,
            limit=MAX_NEWS
        )

    else:
        query = with_location("""
technology OR AI OR business OR sports OR politics OR science
OR health OR startups OR India news
""")
        print("GUEST DEFAULT QUERY =", query)

        articles = fetch_news(query)
        articles = filter_telangana(articles, location)

        news_list = build_news_list(
            articles=articles,
            reason_text="Trending News",
            limit=MAX_NEWS
        )

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