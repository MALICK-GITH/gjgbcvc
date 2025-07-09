def detect_sport(league_name):
    league = league_name.lower()
    if any(word in league for word in ["wta", "atp", "tennis"]):
        return "Tennis"
    elif any(word in league for word in ["basket", "nbl", "nba", "ipbl"]):
        return "Basketball"
    elif "hockey" in league:
        return "Hockey"
    elif any(word in league for word in ["tbl", "table"]):
        return "Table Basketball"
    elif "cricket" in league:
        return "Cricket"
    else:
        return "Football" 
