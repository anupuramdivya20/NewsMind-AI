# modules/content.py

def get_content_score(article, selected_category="", selected_subcategory="", search_query="", user_interests=None):
    """
    Content-based scoring:
    Scores article based on category / subcategory / search / user interests match.
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

    # category match
    if selected_category and selected_category.lower() in text:
        score += 3
        reasons.append(f"Matched selected category: {selected_category}")

    # subcategory match
    if selected_subcategory and selected_subcategory.lower() in text:
        score += 4
        reasons.append(f"Matched selected subcategory: {selected_subcategory}")

    # search match
    if search_query and search_query.lower() in text:
        score += 4
        reasons.append(f"Matched search query: {search_query}")

    # user interest match
    for interest in user_interests:
        if interest and interest.lower() in text:
            score += 2
            reasons.append(f"Matched your interest: {interest}")

    return score, reasons