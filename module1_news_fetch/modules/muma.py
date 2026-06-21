from modules.recommendation import get_user_profile

def get_muma_recommendations(username):
    """
    MUMA-style recommendation:
    returns user interests + expanded related terms
    """
    if not username or username == "Guest":
        return []

    try:
        profile = get_user_profile(username)
        if not profile:
            return []

        recs = []

        for row in profile:
            if row and row[0]:
                interest = str(row[0]).strip().lower()
                recs.append(interest)

                if interest == "ai":
                    recs.extend(["artificial intelligence", "machine learning", "generative ai"])
                elif interest == "cloud computing":
                    recs.extend(["cloud", "aws", "azure", "google cloud"])
                elif interest == "cricket":
                    recs.extend(["ipl", "bcci", "t20", "odi"])
                elif interest == "politics":
                    recs.extend(["election", "government", "parliament", "policy"])

        return list(set(recs))

    except Exception as e:
        print("MUMA MODULE ERROR:", e)
        return []