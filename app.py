from flask import Flask, request, render_template_string, jsonify
import requests
import os
import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple

app = Flask(__name__)

@dataclass
class MatchData:
    team1: str
    team2: str
    score1: int
    score2: int
    league: str
    sport: str
    status: str
    datetime: str
    temp: str
    humid: str
    odds: List[str]
    prediction: str
    id: Optional[int]

# --- Fonctions utilitaires ---
def detect_sport(league_name: str) -> str:
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

def parse_score(score) -> int:
    try:
        return int(score) if score is not None else 0
    except:
        return 0

def parse_minute(match: dict) -> Optional[int]:
    sc = match.get("SC", {})
    if "TS" in sc and isinstance(sc["TS"], int):
        return sc["TS"] // 60
    elif "ST" in sc and isinstance(sc["ST"], int):
        return sc["ST"]
    elif "T" in match and isinstance(match["T"], int):
        return match["T"] // 60
    return None

def parse_status(match: dict, minute: Optional[int], score1: int, score2: int) -> Dict[str, Any]:
    tn = match.get("TN", "").lower()
    tns = match.get("TNS", "").lower()
    tt = match.get("SC", {}).get("TT")
    statut = "À venir"
    is_live = False
    is_finished = False
    is_upcoming = False
    if (minute is not None and minute > 0) or (score1 > 0 or score2 > 0):
        statut = f"En cours ({minute}′)" if minute else "En cours"
        is_live = True
    if ("terminé" in tn or "terminé" in tns) or (tt == 3):
        statut = "Terminé"
        is_live = False
        is_finished = True
    if statut == "À venir":
        is_upcoming = True
    return {"statut": statut, "is_live": is_live, "is_finished": is_finished, "is_upcoming": is_upcoming}

def parse_odds(match: dict) -> List[str]:
    odds_data = []
    for o in match.get("E", []):
        if o.get("G") == 1 and o.get("T") in [1, 2, 3] and o.get("C") is not None:
            odds_data.append(f"{ {1: '1', 2: '2', 3: 'X'}[o.get('T')] }: {o.get('C')}")
    if not odds_data:
        odds_data = ["Pas de cotes disponibles"]
    return odds_data

def get_prediction(match: dict, team1: str, team2: str) -> str:
    best = None
    best_type = None
    for o in match.get("E", []):
        if o.get("G") == 1 and o.get("T") in [1, 2, 3] and o.get("C") is not None:
            if best is None or o.get("C") < best:
                best = o.get("C")
                best_type = o.get("T")
    if best_type == 1:
        return f"{team1} gagne"
    elif best_type == 2:
        return f"{team2} gagne"
    elif best_type == 3:
        return "Match nul"
    return "–"

def traduire_pari(groupe, t, param, team1, team2):
    def param_str(p):
        if p in [None, -1.0, ""]:
            return None
        try:
            return str(float(p)).rstrip('0').rstrip('.') if '.' in str(p) else str(p)
        except:
            return str(p)
    # Paris principaux 1X2 virtuels
    if groupe == 1:
        if t == 1:
            return f"Victoire FIFA {team1} (virtuel)"
        elif t == 2:
            return f"Victoire FIFA {team2} (virtuel)"
        elif t == 3:
            return "Match nul (virtuel)"
        elif t == 4:
            return f"Double chance virtuel : {team1} ou Nul"
        elif t == 5:
            return f"Double chance virtuel : {team2} ou Nul"
        elif t == 6:
            return f"Double chance virtuel : {team1} ou {team2}"
    # Double chance virtuel (groupe 8, T=4 ou 6)
    if groupe == 8:
        if t == 4:
            return f"Double chance virtuel : {team1} ou Nul"
        elif t == 6:
            return f"Double chance virtuel : {team1} ou {team2}"
    # Over/Under, Handicap, etc. virtuels
    if groupe in [2, 8, 15, 62]:
        if t == 7:
            p = param_str(param)
            return f"Plus de {p if p else '?'} buts (simulation)"
        elif t == 8:
            p = param_str(param)
            return f"Moins de {p if p else '?'} buts (simulation)"
        elif t == 9:
            p = param_str(param)
            return f"Handicap virtuel {team1} +{p if p else '?'}"
        elif t == 10:
            p = param_str(param)
            return f"Handicap virtuel {team2} -{p if p else '?'}"
        elif t == 11:
            return f"Les deux équipes marquent (virtuel) : Oui"
        elif t == 12:
            return f"Les deux équipes marquent (virtuel) : Non"
        elif t == 13 or t == 14:
            p = param_str(param)
            return f"Handicap asiatique virtuel {p if p else '?'}"
    # Score exact virtuel
    if groupe == 4:
        p = param_str(param)
        return f"Score exact virtuel : {p if p else '?'}"
    # Mi-temps/fin de match virtuel
    if groupe == 5:
        if t == 16:
            return f"{team1} mène à la mi-temps et gagne (virtuel)"
        elif t == 17:
            return f"{team2} mène à la mi-temps et gagne (virtuel)"
        elif t == 18:
            return f"Nul à la mi-temps, {team1} gagne (virtuel)"
        elif t == 19:
            return f"Nul à la mi-temps, {team2} gagne (virtuel)"
    # Groupes spéciaux virtuels
    if groupe == 17:
        if t == 9:
            p = param_str(param)
            return f"Handicap virtuel {team1} +{p if p else '?'}"
        elif t == 10:
            p = param_str(param)
            return f"Handicap virtuel {team2} -{p if p else '?'}"
    if groupe == 19:
        if t == 180:
            return f"Pari spécial virtuel (T=180, G=19)"
        elif t == 181:
            return f"Pari spécial virtuel (T=181, G=19)"
    # Cas générique pour tout type inconnu
    return f"Pari virtuel non reconnu (T={t}, G={groupe})"

def get_all_predictions(match: dict, team1: str, team2: str) -> list:
    predictions = []
    # Cotes principales (E)
    for o in match.get("E", []):
        cote = o.get("C")
        if cote is not None and 1.399 <= cote <= 3:
            t = o.get("T")
            groupe = o.get("G")
            param = o.get("P") if "P" in o else None
            label = traduire_pari(groupe, t, param, team1, team2)
            predictions.append({"resultat": label, "param": param if param not in [None, -1.0] else "", "cote": cote})
    # Cotes alternatives (AE/ME)
    for ae in match.get("AE", []):
        groupe = ae.get("G")
        for o in ae.get("ME", []):
            cote = o.get("C")
            if cote is not None and 1.399 <= cote <= 3:
                t = o.get("T")
                param = o.get("P") if "P" in o else None
                label = traduire_pari(groupe, t, param, team1, team2)
                predictions.append({"resultat": label, "param": param if param not in [None, -1.0] else "", "cote": cote})
    # Tri par cote croissante
    predictions.sort(key=lambda x: x["cote"])
    return predictions

# Adapter l'affichage de la prédiction du bot (get_alternative_prediction) pour n'afficher le paramètre que s'il existe et est pertinent

def get_alternative_prediction(match: dict, team1: str, team2: str) -> str:
    meilleures = []
    for ae in match.get("AE", []):
        groupe = ae.get("G")
        for o in ae.get("ME", []):
            cote = o.get("C")
            if cote is not None and 1.399 <= cote <= 3:
                t = o.get("T")
                param = o.get("P") if "P" in o else None
                label = traduire_pari(groupe, t, param, team1, team2)
                meilleures.append((cote, label, param, groupe, t))
    if meilleures:
        meilleures.sort(key=lambda x: x[0])
        cote, label, param, groupe, t = meilleures[0]
        # N'afficher le paramètre que s'il n'est pas déjà dans le libellé
        if param not in [None, -1.0, ""]:
            param_str = str(param)
            # Si le paramètre est déjà dans le label, ne pas le rajouter
            if param_str in label:
                return f"{label} [{cote}]"
        return f"{label} [{cote}]"
    return "Aucune cote alternative dans la plage (1.399 à 3)"

def parse_meteo(match: dict) -> Tuple[str, str]:
    meteo_data = match.get("MIS", [])
    temp = next((item["V"] for item in meteo_data if item.get("K") == 9), "–")
    humid = next((item["V"] for item in meteo_data if item.get("K") == 27), "–")
    return temp, humid

def parse_match(match: dict) -> MatchData:
    league = match.get("LE", "–")
    team1 = match.get("O1", "–")
    team2 = match.get("O2", "–")
    sport = detect_sport(league).strip()
    score1 = parse_score(match.get("SC", {}).get("FS", {}).get("S1"))
    score2 = parse_score(match.get("SC", {}).get("FS", {}).get("S2"))
    minute = parse_minute(match)
    status_info = parse_status(match, minute, score1, score2)
    match_ts = match.get("S", 0)
    match_time = datetime.datetime.utcfromtimestamp(match_ts).strftime('%d/%m/%Y %H:%M') if match_ts else "–"
    odds = parse_odds(match)
    prediction = get_prediction(match, team1, team2)
    temp, humid = parse_meteo(match)
    return MatchData(
        team1=team1,
        team2=team2,
        score1=score1,
        score2=score2,
        league=league,
        sport=sport,
        status=status_info["statut"],
        datetime=match_time,
        temp=temp,
        humid=humid,
        odds=odds,
        prediction=prediction,
        id=match.get("I", None)
    )

@app.route('/')
def home():
    try:
        selected_sport = request.args.get("sport", "").strip()
        selected_league = request.args.get("league", "").strip()
        selected_status = request.args.get("status", "").strip()

        api_url = "https://1xbet.com/LiveFeed/Get1x2_VZip?sports=85&count=50&lng=fr&gr=70&mode=4&country=96&getEmpty=true"
        response = requests.get(api_url)
        matches = response.json().get("Value", [])

        sports_detected = set()
        leagues_detected = set()
        data: List[MatchData] = []

        for match in matches:
            try:
                m = parse_match(match)
                sports_detected.add(m.sport)
                leagues_detected.add(m.league)
                # Filtres
                if selected_sport and m.sport != selected_sport:
                    continue
                if selected_league and m.league != selected_league:
                    continue
                status_info = parse_status(match, parse_minute(match), m.score1, m.score2)
                if selected_status == "live" and not status_info["is_live"]:
                    continue
                if selected_status == "finished" and not status_info["is_finished"]:
                    continue
                if selected_status == "upcoming" and not status_info["is_upcoming"]:
                    continue
                data.append(m)
            except Exception as e:
                print(f"Erreur lors du traitement d'un match: {e}")
                continue

        # --- Pagination ---
        try:
            page = int(request.args.get('page', 1))
        except:
            page = 1
        per_page = 20
        total = len(data)
        total_pages = (total + per_page - 1) // per_page
        data_paginated = data[(page-1)*per_page:page*per_page]

        return render_template_string(TEMPLATE, data=[asdict(m) for m in data_paginated],
            sports=sorted(sports_detected),
            leagues=sorted(leagues_detected),
            selected_sport=selected_sport or "Tous",
            selected_league=selected_league or "Toutes",
            selected_status=selected_status or "Tous",
            page=page,
            total_pages=total_pages
        )

    except Exception as e:
        return f"Erreur : {e}"

@app.route('/api/matches')
def api_matches():
    try:
        selected_sport = request.args.get("sport", "").strip()
        selected_league = request.args.get("league", "").strip()
        selected_status = request.args.get("status", "").strip()

        api_url = "https://1xbet.com/LiveFeed/Get1x2_VZip?sports=85&count=50&lng=fr&gr=70&mode=4&country=96&getEmpty=true"
        response = requests.get(api_url)
        matches = response.json().get("Value", [])

        data: List[MatchData] = []
        for match in matches:
            try:
                m = parse_match(match)
                # Filtres
                if selected_sport and m.sport != selected_sport:
                    continue
                if selected_league and m.league != selected_league:
                    continue
                status_info = parse_status(match, parse_minute(match), m.score1, m.score2)
                if selected_status == "live" and not status_info["is_live"]:
                    continue
                if selected_status == "finished" and not status_info["is_finished"]:
                    continue
                if selected_status == "upcoming" and not status_info["is_upcoming"]:
                    continue
                data.append(m)
            except Exception as e:
                continue
        # Pagination
        try:
            page = int(request.args.get('page', 1))
        except:
            page = 1
        per_page = 20
        total = len(data)
        total_pages = (total + per_page - 1) // per_page
        data_paginated = data[(page-1)*per_page:page*per_page]
        return jsonify({
            "data": [asdict(m) for m in data_paginated],
            "page": page,
            "total_pages": total_pages
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/match/<int:match_id>')
def api_match_details(match_id):
    try:
        api_url = "https://1xbet.com/LiveFeed/Get1x2_VZip?sports=85&count=50&lng=fr&gr=70&mode=4&country=96&getEmpty=true"
        response = requests.get(api_url)
        matches = response.json().get("Value", [])
        match = next((m for m in matches if m.get("I") == match_id), None)
        if not match:
            return jsonify({"error": f"Aucun match trouvé pour l'identifiant {match_id}"}), 404
        team1 = match.get("O1", "–")
        team2 = match.get("O2", "–")
        league = match.get("LE", "–")
        league_name = match.get("CN", "–")
        league_country = match.get("CE", "–")
        sport = detect_sport(league)
        sport_name = match.get("SN", match.get("SE", sport))
        score1 = parse_score(match.get("SC", {}).get("FS", {}).get("S1"))
        score2 = parse_score(match.get("SC", {}).get("FS", {}).get("S2"))
        stats = []
        st = match.get("SC", {}).get("ST", [])
        if st and isinstance(st, list) and len(st) > 0 and "Value" in st[0]:
            for stat in st[0]["Value"]:
                nom = stat.get("N", "?")
                s1 = stat.get("S1", "0")
                s2 = stat.get("S2", "0")
                stats.append({"nom": nom, "s1": s1, "s2": s2})
        explication = "Toutes les opportunités de pari virtuel (alternatives uniquement) comprises entre 1.399 et 3 sont listées ci-dessous, avec leur libellé explicite. Les résultats sont issus de simulations virtuelles (FIFA, NBA2K, etc.)."
        all_predictions = get_all_predictions(match, team1, team2)
        alt_prediction = get_alternative_prediction(match, team1, team2)
        return jsonify({
            "team1": team1,
            "team2": team2,
            "league": league,
            "league_name": league_name,
            "league_country": league_country,
            "sport": sport,
            "sport_name": sport_name,
            "score1": score1,
            "score2": score2,
            "stats": stats,
            "explication": explication,
            "all_predictions": all_predictions,
            "alt_prediction": alt_prediction
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/match/<int:match_id>')
def match_details(match_id):
    try:
        api_url = "https://1xbet.com/LiveFeed/Get1x2_VZip?sports=85&count=50&lng=fr&gr=70&mode=4&country=96&getEmpty=true"
        response = requests.get(api_url)
        matches = response.json().get("Value", [])
        match = next((m for m in matches if m.get("I") == match_id), None)
        if not match:
            return f"Aucun match trouvé pour l'identifiant {match_id}"
        team1 = match.get("O1", "–")
        team2 = match.get("O2", "–")
        league = match.get("LE", "–")
        league_name = match.get("CN", "–")
        league_country = match.get("CE", "–")
        sport = detect_sport(league)
        sport_name = match.get("SN", match.get("SE", sport))
        score1 = parse_score(match.get("SC", {}).get("FS", {}).get("S1"))
        score2 = parse_score(match.get("SC", {}).get("FS", {}).get("S2"))
        stats = []
        st = match.get("SC", {}).get("ST", [])
        if st and isinstance(st, list) and len(st) > 0 and "Value" in st[0]:
            for stat in st[0]["Value"]:
                nom = stat.get("N", "?")
                s1 = stat.get("S1", "0")
                s2 = stat.get("S2", "0")
                stats.append({"nom": nom, "s1": s1, "s2": s2})
        explication = "Toutes les opportunités de pari virtuel (alternatives uniquement) comprises entre 1.399 et 3 sont listées ci-dessous, avec leur libellé explicite. Les résultats sont issus de simulations virtuelles (FIFA, NBA2K, etc.)."
        all_predictions = get_all_predictions(match, team1, team2)
        alt_prediction = get_alternative_prediction(match, team1, team2)
        return f'''
        <!DOCTYPE html>
        <html><head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Détails du match</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: Arial; padding: 20px; background: #f4f4f4; }}
                .container {{ max-width: 700px; margin: auto; background: white; border-radius: 10px; box-shadow: 0 2px 8px #ccc; padding: 20px; }}
                h2 {{ text-align: center; }}
                .stats-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                .stats-table th, .stats-table td {{ border: 1px solid #ccc; padding: 8px; text-align: center; }}
                .back-btn {{ margin-bottom: 20px; display: inline-block; }}
                .pred-table {{ width: 90%; margin: 20px auto 0 auto; border-collapse: collapse; }}
                .pred-table th, .pred-table td {{ border: 1px solid #aaa; padding: 6px; text-align: center; }}
                .pred-section {{
                    border: 3px solid #2196f3;
                    background: #e3f2fd;
                    border-radius: 10px;
                    padding: 18px 12px 12px 12px;
                    margin: 25px 0 25px 0;
                    box-shadow: 0 2px 8px #b3e5fc;
                    transition: box-shadow 0.2s;
                }}
                .pred-section:hover {{
                    box-shadow: 0 4px 16px #90caf9;
                }}
                .alt-prediction-section {{
                    border: 3px solid #ff1744;
                    background: #ffebee;
                    border-radius: 10px;
                    padding: 12px 10px;
                    margin: 18px 0 18px 0;
                    font-size: 1.08em;
                    font-weight: bold;
                    color: #b71c1c;
                    box-shadow: 0 0 12px 2px #ff1744, 0 2px 8px #ffcdd2;
                    display: block;
                }}
                .alt-prediction-table-section {{
                    border: 3px solid #ff1744;
                    background: #fff3f3;
                    border-radius: 10px;
                    padding: 16px 10px 10px 10px;
                    margin: 18px 0 18px 0;
                    box-shadow: 0 0 12px 2px #ff1744, 0 2px 8px #ffcdd2;
                }}
                .alt-prediction-table {{
                    width: 98%;
                    margin: 10px auto 0 auto;
                    border-collapse: collapse;
                    background: #fff;
                }}
                .alt-prediction-table th, .alt-prediction-table td {{
                    border: 1.5px solid #ff1744;
                    padding: 7px 6px;
                    text-align: center;
                }}
                .alt-prediction-best {{
                    background: #ff1744;
                    color: #fff;
                    font-weight: bold;
                    font-size: 1.08em;
                }}
            </style>
        </head><body>
            <div class="container">
                <a href="/" class="back-btn">&larr; Retour à la liste</a>
                <h2 id="teams">{team1} vs {team2}</h2>
                <p id="infos"><b>Ligue :</b> {league_name} ({league}) | <b>Pays :</b> {league_country} | <b>Sport :</b> {sport_name}</p>
                <p id="score"><b>Score :</b> {score1} - {score2}</p>
                <div class="alt-prediction-table-section">
                    <div class="alt-prediction-section" id="alt-prediction"><b>Meilleure prédiction alternative :</b> {alt_prediction}</div>
                    <h4 style="margin-top:10px;">Tableau des alternatives (Handicap & Over/Under, cotes 1.399 à 3)</h4>
                    <table class="alt-prediction-table" id="alt-prediction-table">
                        <tr><th>Type de pari</th><th>Cote</th><th>Probabilité estimée</th></tr>
                        {''.join(f'<tr class="alt-prediction-best">' if i==0 else '<tr>' + f'<td>{{p["resultat"]}}</td><td>{{p["cote"]}}</td><td>{{round(1/float(p["cote"]),3) if p.get("cote") else "-"}}</td></tr>' for i,p in enumerate([pp for pp in all_predictions if any(x in pp["resultat"].lower() for x in ["handicap", "plus de", "moins de", "asiatique"])]) )}
                    </table>
                </div>
                <div id="predictions" class="pred-section">
                    <h3>Prédictions principales et alternatives (cotes 1.399 à 3)</h3>
                    <table class="pred-table" id="pred-table">
                        <tr><th>Pari/prédiction</th><th>Paramètre</th><th>Cote</th></tr>
                        {''.join(f'<tr><td>{{p["resultat"]}}</td><td>{{p["param"]}}</td><td>{{p["cote"]}}</td></tr>' for p in all_predictions)}
                    </table>
                </div>
                <p id="explication"><b>Explication :</b> {explication}</p>
                <h3>Statistiques principales</h3>
                <table class="stats-table">
                    <tr><th>Statistique</th><th>{team1}</th><th>{team2}</th></tr>
                    <tbody id="stats-tbody">
                    {''.join(f'<tr><td>{{s["nom"]}}</td><td>{{s["s1"]}}</td><td>{{s["s2"]}}</td></tr>' for s in stats)}
                    </tbody>
                </table>
                <canvas id="statsChart" height="200"></canvas>
            </div>
            <script>
                function updateMatchDetails() {{
                    fetch(window.location.pathname.replace('/match/', '/api/match/'))
                        .then(response => response.json())
                        .then(data => {{
                            if(data.error) return;
                            document.getElementById('teams').textContent = data.team1 + ' vs ' + data.team2;
                            document.getElementById('infos').innerHTML = `<b>Ligue :</b> ${{data.league_name}} (${{data.league}}) | <b>Pays :</b> ${{data.league_country}} | <b>Sport :</b> ${{data.sport_name}}`;
                            document.getElementById('score').innerHTML = `<b>Score :</b> ${{data.score1}} - ${{data.score2}}`;

                            // Prédictions principales et alternatives
                            const predTable = document.getElementById('pred-table');
                            let predRows = '<tr><th>Pari/prédiction</th><th>Paramètre</th><th>Cote</th></tr>';
                            data.all_predictions.forEach(function(p) {{
                                predRows += `<tr><td>${{p.resultat}}</td><td>${{p.param}}</td><td>${{p.cote}}</td></tr>`;
                            }});
                            predTable.innerHTML = predRows;

                            // Tableau alternatives (Handicap & Over/Under)
                            const altTable = document.getElementById('alt-prediction-table');
                            let altRows = '<tr><th>Type de pari</th><th>Cote</th><th>Probabilité estimée</th></tr>';
                            let first = true;
                            data.all_predictions.forEach(function(p) {{
                                if (p.resultat.toLowerCase().includes('handicap') || p.resultat.toLowerCase().includes('plus de') || p.resultat.toLowerCase().includes('moins de') || p.resultat.toLowerCase().includes('asiatique')) {{
                                    let proba = p.cote ? (1/parseFloat(p.cote)).toFixed(3) : '-';
                                    let rowClass = first ? ' class="alt-prediction-best"' : '';
                                    altRows += `<tr${{rowClass}}><td>${{p.resultat}}</td><td>${{p.cote}}</td><td>${{proba}}</td></tr>`;
                                    first = false;
                                }}
                            }});
                            altTable.innerHTML = altRows;

                            document.getElementById('alt-prediction').innerHTML = `<b>Meilleure prédiction alternative :</b> ${{data.alt_prediction}}`;
                            document.getElementById('explication').innerHTML = `<b>Explication :</b> ${{data.explication}}`;

                            // Update stats table
                            const statsTbody = document.getElementById('stats-tbody');
                            statsTbody.innerHTML = '';
                            data.stats.forEach(function(s) {{
                                statsTbody.innerHTML += `<tr><td>${{s.nom}}</td><td>${{s.s1}}</td><td>${{s.s2}}</td></tr>`;
                            }});
                            // Update chart
                            if(window.statsChart) window.statsChart.destroy();
                            const labels = data.stats.map(s => s.nom);
                            const data1 = data.stats.map(s => parseFloat(s.s1.replace(',', '.')) || 0);
                            const data2 = data.stats.map(s => parseFloat(s.s2.replace(',', '.')) || 0);
                            window.statsChart = new Chart(document.getElementById('statsChart'), {{
                                type: 'bar',
                                data: {{
                                    labels: labels,
                                    datasets: [
                                        {{ label: data.team1, data: data1, backgroundColor: 'rgba(44,62,80,0.7)' }},
                                        {{ label: data.team2, data: data2, backgroundColor: 'rgba(39,174,96,0.7)' }}
                                    ]
                                }},
                                options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }} }}
                            }});
                        }});
                }}
                setInterval(updateMatchDetails, 5000); // 5 secondes
            </script>
        </body></html>
        '''
    except Exception as e:
        return f"Erreur lors de l'affichage des détails du match : {e}"

TEMPLATE = """<!DOCTYPE html>
<html><head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Matchs en direct</title>
    <style>
        body { font-family: Arial; padding: 20px; background: #f4f4f4; }
        h2 { text-align: center; }
        form { text-align: center; margin-bottom: 20px; }
        select { padding: 8px; margin: 0 10px; font-size: 14px; }
        table { border-collapse: collapse; margin: auto; width: 98%; background: white; }
        th, td { padding: 10px; border: 1px solid #ccc; text-align: center; }
        th { background: #2c3e50; color: white; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .pagination { text-align: center; margin: 20px 0; }
        .pagination button { padding: 8px 16px; margin: 0 4px; font-size: 16px; border: none; background: #2c3e50; color: white; border-radius: 4px; cursor: pointer; }
        .pagination button:disabled { background: #ccc; cursor: not-allowed; }
        /* Responsive */
        @media (max-width: 800px) {
            table, thead, tbody, th, td, tr { display: block; }
            th { position: absolute; left: -9999px; top: -9999px; }
            tr { margin-bottom: 15px; background: white; border-radius: 8px; box-shadow: 0 2px 6px #ccc; }
            td { border: none; border-bottom: 1px solid #eee; position: relative; padding-left: 50%; min-height: 40px; }
            td:before { position: absolute; top: 10px; left: 10px; width: 45%; white-space: nowrap; font-weight: bold; }
            td:nth-of-type(1):before { content: 'Équipe 1'; }
            td:nth-of-type(2):before { content: 'Score 1'; }
            td:nth-of-type(3):before { content: 'Score 2'; }
            td:nth-of-type(4):before { content: 'Équipe 2'; }
            td:nth-of-type(5):before { content: 'Sport'; }
            td:nth-of-type(6):before { content: 'Ligue'; }
            td:nth-of-type(7):before { content: 'Statut'; }
            td:nth-of-type(8):before { content: 'Date & Heure'; }
            td:nth-of-type(9):before { content: 'Température'; }
            td:nth-of-type(10):before { content: 'Humidité'; }
            td:nth-of-type(11):before { content: 'Cotes'; }
            td:nth-of-type(12):before { content: 'Prédiction'; }
        }
        /* Loader */
        #loader { display: none; position: fixed; left: 0; top: 0; width: 100vw; height: 100vh; background: rgba(255,255,255,0.7); z-index: 9999; justify-content: center; align-items: center; }
        #loader .spinner { border: 8px solid #f3f3f3; border-top: 8px solid #2c3e50; border-radius: 50%; width: 60px; height: 60px; animation: spin 1s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
    </style>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            var forms = document.querySelectorAll('form');
            forms.forEach(function(form) {
                form.addEventListener('submit', function() {
                    document.getElementById('loader').style.display = 'flex';
                });
            });
            // Rafraîchissement automatique du tableau
            function fetchMatches() {
                const params = new URLSearchParams(window.location.search);
                fetch('/api/matches?' + params.toString())
                    .then(response => response.json())
                    .then(json => {
                        if(json.data) {
                            const tbody = document.getElementById('matches-tbody');
                            tbody.innerHTML = '';
                            json.data.forEach(function(m) {
                                tbody.innerHTML += `
        <tr>
            <td>${m.team1}</td><td>${m.score1}</td><td>${m.score2}</td><td>${m.team2}</td>
            <td>${m.sport}</td><td>${m.league}</td><td>${m.status}</td><td>${m.datetime}</td>
            <td>${m.temp}°C</td><td>${m.humid}%</td><td>${m.odds.join(' | ')}</td><td>${m.prediction}</td>
            <td>${m.id ? `<a href='/match/${m.id}'><button>Détails</button></a>` : '–'}</td>
        </tr>`;
                            });
                        }
                    });
            }
            setInterval(fetchMatches, 20000); // 20 secondes
        });
    </script>
</head><body>
    <div id="loader"><div class="spinner"></div></div>
    <h2>📊 Matchs en direct — {{ selected_sport }} / {{ selected_league }} / {{ selected_status }}</h2>

    <form method="get">
        <label>Sport :
            <select name="sport" onchange="this.form.submit()">
                <option value="">Tous</option>
                {% for s in sports %}
                    <option value="{{s}}" {% if s == selected_sport %}selected{% endif %}>{{s}}</option>
                {% endfor %}
            </select>
        </label>
        <label>Ligue :
            <select name="league" onchange="this.form.submit()">
                <option value="">Toutes</option>
                {% for l in leagues %}
                    <option value="{{l}}" {% if l == selected_league %}selected{% endif %}>{{l}}</option>
                {% endfor %}
            </select>
        </label>
        <label>Statut :
            <select name="status" onchange="this.form.submit()">
                <option value="">Tous</option>
                <option value="live" {% if selected_status == "live" %}selected{% endif %}>En direct</option>
                <option value="upcoming" {% if selected_status == "upcoming" %}selected{% endif %}>À venir</option>
                <option value="finished" {% if selected_status == "finished" %}selected{% endif %}>Terminé</option>
            </select>
        </label>
    </form>

    <div class="pagination">
        <form method="get" style="display:inline;">
            <input type="hidden" name="sport" value="{{ selected_sport if selected_sport != 'Tous' else '' }}">
            <input type="hidden" name="league" value="{{ selected_league if selected_league != 'Toutes' else '' }}">
            <input type="hidden" name="status" value="{{ selected_status if selected_status != 'Tous' else '' }}">
            <button type="submit" name="page" value="{{ page-1 }}" {% if page <= 1 %}disabled{% endif %}>Page précédente</button>
        </form>
        <span>Page {{ page }} / {{ total_pages }}</span>
        <form method="get" style="display:inline;">
            <input type="hidden" name="sport" value="{{ selected_sport if selected_sport != 'Tous' else '' }}">
            <input type="hidden" name="league" value="{{ selected_league if selected_league != 'Toutes' else '' }}">
            <input type="hidden" name="status" value="{{ selected_status if selected_status != 'Tous' else '' }}">
            <button type="submit" name="page" value="{{ page+1 }}" {% if page >= total_pages %}disabled{% endif %}>Page suivante</button>
        </form>
    </div>

    <table>
        <tr>
            <th>Équipe 1</th><th>Score 1</th><th>Score 2</th><th>Équipe 2</th>
            <th>Sport</th><th>Ligue</th><th>Statut</th><th>Date & Heure</th>
            <th>Température</th><th>Humidité</th><th>Cotes</th><th>Prédiction</th><th>Détails</th>
        </tr>
        <tbody id="matches-tbody">
        {% for m in data %}
        <tr>
            <td>{{m.team1}}</td><td>{{m.score1}}</td><td>{{m.score2}}</td><td>{{m.team2}}</td>
            <td>{{m.sport}}</td><td>{{m.league}}</td><td>{{m.status}}</td><td>{{m.datetime}}</td>
            <td>{{m.temp}}°C</td><td>{{m.humid}}%</td><td>{{m.odds|join(" | ")}}</td><td>{{m.prediction}}</td>
            <td>{% if m.id %}<a href="/match/{{m.id}}"><button>Détails</button></a>{% else %}–{% endif %}</td>
        </tr>
        {% endfor %}
        </tbody>
    </table>
</body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
