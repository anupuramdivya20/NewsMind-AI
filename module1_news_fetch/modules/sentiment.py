from textblob import TextBlob

def get_sentiment(text):
    p = TextBlob(text).sentiment.polarity
    if p > 0:
        return 1
    elif p < 0:
        return -1
    return 0