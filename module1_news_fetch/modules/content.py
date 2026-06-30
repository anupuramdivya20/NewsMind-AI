import re

def contains_term(term, text):
    """
    Match whole word / whole phrase only.
    Example:
    - ai matches 'ai'
    - ai will NOT match 'said', 'rain', 'captain'
    """
    if not term or not text:
        return False

    term = str(term).strip().lower()
    text = str(text).lower()

    # normalize extra spaces
    term = re.sub(r"\s+", " ", term).strip()
    text = re.sub(r"\s+", " ", text).strip()

    pattern = r'\b' + re.escape(term) + r'\b'
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def get_content_score(article, selected_category="", selected_subcategory="", search_query="", user_interests=None):
    """
    Content-based scoring:
    Higher weight for current search / selected category / selected subcategory.
    Lower weight for old stored interests.
    Returns:
        score, reasons
    """
    if user_interests is None:
        user_interests = []

    title = (article.get("title") or "").lower()
    desc = (article.get("description") or "").lower()
    text = title + " " + desc

    score = 0
    reasons = []

    selected_category = (selected_category or "").strip()
    selected_subcategory = (selected_subcategory or "").strip()
    search_query = (search_query or "").strip()

    # =========================
    # SEARCH MODE: strongest priority
    # =========================
    if search_query and contains_term(search_query, text):
        score += 30
        reasons.append(f"Matched your search: {search_query}")

    # =========================
    # CURRENT CHOICE PRIORITY
    # =========================
    if selected_subcategory and contains_term(selected_subcategory, text):
        score += 20
        reasons.append(f"Matched selected subcategory: {selected_subcategory}")

    if selected_category and contains_term(selected_category, text):
        score += 15
        reasons.append(f"Matched selected category: {selected_category}")

    # =========================
    # OLD USER INTERESTS -> lower weight
    # =========================
    seen = set()
    for interest in user_interests:
        if not interest:
            continue

        interest = str(interest).strip()
        low = interest.lower()

        # avoid duplicate reasons
        if low in seen:
            continue
        seen.add(low)

        # avoid repeating same current category/subcategory/search as interest
        if low == selected_category.lower() or low == selected_subcategory.lower() or low == search_query.lower():
            continue

        if contains_term(interest, text):
            score += 4
            reasons.append(f"Matched your interest: {interest}")

    return score, reasons