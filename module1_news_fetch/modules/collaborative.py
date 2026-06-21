import sqlite3

def init_collab_db():
    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            interest TEXT
        )
    """)

    conn.commit()
    conn.close()

init_collab_db()

def save_interaction(username, interest):
    if not username or username == "Guest" or not interest:
        return

    interest = str(interest).strip().lower()

    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT 1 FROM interactions WHERE username=? AND lower(interest)=?",
        (username, interest)
    )
    exists = cur.fetchone()

    if not exists:
        cur.execute(
            "INSERT INTO interactions(username, interest) VALUES(?, ?)",
            (username, interest)
        )
        conn.commit()

    conn.close()

def get_collaborative_recommendations(username):
    """
    Returns interests liked by similar users.
    """
    if not username or username == "Guest":
        return []

    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    # current user interests
    cur.execute(
        "SELECT DISTINCT interest FROM interactions WHERE username=?",
        (username,)
    )
    my_interests = [row[0] for row in cur.fetchall() if row[0]]

    if not my_interests:
        conn.close()
        return []

    placeholders = ",".join(["?"] * len(my_interests))

    # similar users
    cur.execute(f"""
        SELECT DISTINCT username
        FROM interactions
        WHERE lower(interest) IN ({placeholders}) AND username != ?
    """, tuple([i.lower() for i in my_interests] + [username]))

    similar_users = [row[0] for row in cur.fetchall() if row[0]]

    if not similar_users:
        conn.close()
        return []

    placeholders2 = ",".join(["?"] * len(similar_users))

    # interests of similar users
    cur.execute(f"""
        SELECT DISTINCT interest
        FROM interactions
        WHERE username IN ({placeholders2})
    """, tuple(similar_users))

    recs = [row[0] for row in cur.fetchall() if row[0]]

    conn.close()
    return recs