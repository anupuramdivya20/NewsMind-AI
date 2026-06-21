import sqlite3

def save_feedback(username, article, action):
    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback(
            username TEXT,
            article TEXT,
            action TEXT
        )
    """)

    cur.execute(
        "INSERT INTO feedback VALUES (?, ?, ?)",
        (username, article, action)
    )

    conn.commit()
    conn.close()