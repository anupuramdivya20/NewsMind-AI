from modules.recommendation import get_user_profile

def get_rgrec_recommendations(username):
    """
    RGRec-style recommendation:
    returns stored interest keywords of user.
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
                recs.append(str(row[0]).strip().lower())

        return list(set(recs))

    except Exception as e:
        print("RGREC MODULE ERROR:", e)
        return []