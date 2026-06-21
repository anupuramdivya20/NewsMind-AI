# modules/hybrid.py

def hybrid_recommendations(articles, rgrec_results, muma_results, collab_interests=None):
    """
    Combine RGRec + MUMA + Collaborative scores.
    Returns:
    [(article, final_score, reason), ...]
    """
    if collab_interests is None:
        collab_interests = []

    collab_interests = [str(x).lower() for x in collab_interests]

    final_results = []

    # build maps
    rg_map = {}
    for article, score, reason in rgrec_results:
        key = article.get("url") or article.get("title")
        rg_map[key] = (score, reason)

    mu_map = {}
    for article, score, reason in muma_results:
        key = article.get("url") or article.get("title")
        mu_map[key] = (score, reason)

    for article in articles:
        key = article.get("url") or article.get("title")

        rg_score, rg_reason = rg_map.get(key, (0, ""))
        mu_score, mu_reason = mu_map.get(key, (0, ""))

        title = (article.get("title") or "").lower()
        desc = (article.get("description") or "").lower()
        text = title + " " + desc

        collab_score = 0
        collab_reason = ""

        for interest in collab_interests:
            if interest and interest in text:
                collab_score += 4
                collab_reason = f"Collaborative match: {interest}"
                break

        final_score = rg_score + mu_score + collab_score

        reasons = []
        if rg_reason:
            reasons.append(rg_reason)
        if mu_reason:
            reasons.append(mu_reason)
        if collab_reason:
            reasons.append(collab_reason)

        if not reasons:
            reasons.append("General recommendation")

        final_results.append((article, final_score, " | ".join(reasons)))

    final_results.sort(key=lambda x: x[1], reverse=True)
    return final_results