import sqlite3

def init_recommendation_db():
    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            interest TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS article_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            title TEXT,
            category TEXT
        )
    """)

    conn.commit()
    conn.close()

init_recommendation_db()


def update_interest(username, interest):
    if not username or username == "Guest" or not interest:
        return

    interest = str(interest).strip().lower()

    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    # Prevent immediate duplicate spam of same latest interest
    cur.execute("""
        SELECT interest
        FROM user_interests
        WHERE username=?
        ORDER BY id DESC
        LIMIT 1
    """, (username,))
    last_row = cur.fetchone()

    if not last_row or (last_row[0] or "").strip().lower() != interest:
        cur.execute(
            "INSERT INTO user_interests(username, interest) VALUES(?, ?)",
            (username, interest)
        )
        conn.commit()

    conn.close()


def get_user_profile(username):
    if not username or username == "Guest":
        return []

    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT interest
        FROM user_interests
        WHERE username=?
    """, (username,))

    data = cur.fetchall()
    conn.close()
    return data


def get_recent_user_interests(username, limit=3):
    """
    Returns most recent unique interests for the user.
    Example output: ['ai', 'cricket', 'business']
    """
    if not username or username == "Guest":
        return []

    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT interest
        FROM user_interests
        WHERE username=?
        ORDER BY id DESC
    """, (username,))

    rows = cur.fetchall()
    conn.close()

    recent = []
    seen = set()

    for row in rows:
        interest = (row[0] or "").strip().lower()
        if interest and interest not in seen:
            recent.append(interest)
            seen.add(interest)

        if len(recent) >= limit:
            break

    return recent


def track_article(username, title, category):
    if not username or username == "Guest":
        return

    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO article_tracking(username, title, category) VALUES(?, ?, ?)",
        (username, title, category)
    )

    conn.commit()
    conn.close()


def get_popularity_score(title):
    if not title:
        return 0

    score = 0
    title = title.lower()

    keywords = ["breaking", "latest", "trending", "big", "exclusive", "update"]
    for word in keywords:
        if word in title:
            score += 5

    score += min(len(title) // 20, 5)
    return score