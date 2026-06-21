import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize, word_tokenize

# =========================
# SAFE NLTK INIT
# =========================
try:
    stop_words = set(stopwords.words("english"))
except:
    nltk.download("punkt")
    nltk.download("stopwords")
    stop_words = set(stopwords.words("english"))


# =========================
# CORE SUMMARIZER (MTECH UPGRADE)
# =========================
def summarize(text, max_sentences=2):

    if not text or len(text.strip()) == 0:
        return "No summary available"

    sentences = sent_tokenize(text)

    if len(sentences) <= max_sentences:
        return text

    # =========================
    # WORD FREQUENCY MODEL
    # =========================
    word_freq = {}

    words = word_tokenize(text.lower())

    for word in words:
        if word.isalnum() and word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1

    # =========================
    # SENTENCE SCORING
    # =========================
    sentence_score = {}

    for sentence in sentences:
        for word in word_tokenize(sentence.lower()):
            if word in word_freq:
                sentence_score[sentence] = sentence_score.get(sentence, 0) + word_freq[word]

    # Normalize sentence scores (M.Tech improvement)
    max_score = max(sentence_score.values()) if sentence_score else 1

    for key in sentence_score:
        sentence_score[key] /= max_score

    # =========================
    # RANK SENTENCES
    # =========================
    ranked_sentences = sorted(
        sentence_score,
        key=sentence_score.get,
        reverse=True
    )

    summary = " ".join(ranked_sentences[:max_sentences])

    return summary


# =========================
# ROUGE EVALUATION HOOK (MTECH THESIS READY)
# =========================
def evaluate_summary(generated, reference):
    """
    Placeholder for ROUGE evaluation (for thesis)
    You can connect rouge-score or bert-score later
    """

    if not generated or not reference:
        return 0

    gen_words = set(generated.lower().split())
    ref_words = set(reference.lower().split())

    overlap = gen_words.intersection(ref_words)

    precision = len(overlap) / len(gen_words) if gen_words else 0
    recall = len(overlap) / len(ref_words) if ref_words else 0

    if precision + recall == 0:
        return 0

    f1 = 2 * (precision * recall) / (precision + recall)

    return round(f1, 3)


# =========================
# FUTURE TRANSFORMER HOOK (IMPORTANT FOR M.TECH)
# =========================
def transformer_summary_placeholder(text):
    """
    This is where BART / T5 / PEGASUS can be integrated
    Keeps architecture thesis-ready
    """

    return summarize(text)