from collections import defaultdict

user_weights = defaultdict(lambda: defaultdict(int))

def update_profile(username, category):
    user_weights[username][category] += 1

def get_weighted_profile(username):
    return user_weights[username]