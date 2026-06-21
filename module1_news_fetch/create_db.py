import sqlite3

conn = sqlite3.connect("news.db")
cursor = conn.cursor()

# MUMA
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_interests(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    category TEXT,
    count INTEGER DEFAULT 1
)
""")

# History
cursor.execute("""
CREATE TABLE IF NOT EXISTS article_history(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    article_title TEXT,
    category TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Popularity
cursor.execute("""
CREATE TABLE IF NOT EXISTS article_popularity(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_title TEXT UNIQUE,
    views INTEGER DEFAULT 1
)
""")

# RGRec
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_graph(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    article_title TEXT
)
""")

# Bookmarks
cursor.execute("""
CREATE TABLE IF NOT EXISTS bookmarks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    title TEXT,
    url TEXT,
    source TEXT
)
""")

conn.commit()
conn.close()

print("Database Created Successfully")