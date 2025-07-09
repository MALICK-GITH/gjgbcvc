from flask import Flask, request, render_template_string, jsonify
import requests
import os
import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple

app = Flask(__name__)

@dataclass
class Odds:
    type: str
    cote: float

@dataclass
class MatchData:
    team1: str
    team2: str
    score1: int
    score2: int
    league: str
    league_name: str
    league_country: str
    sport: str
    sport_name: str
    status: str
    datetime: str
    temp: str
    humid: str
    odds: List[str]
    prediction: str
    id: Optional[int]
    event_type: Optional[int]
    match_status: Optional[int]
    time_name: str
    time_name_en: str

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

def parse_odds(match: dict) -> List[Odds]:
    odds_data = []
    for o in match.get("E", []):
        if o.get("G") == 1 and o.get("T") in [1, 2, 3] and o.get("C") is not None:
            odds_data.append(Odds(type={1: "1", 2: "2", 3: "X"}.get(o.get("T"), "-"), cote=o.get("C")))
    if not odds_data:
        for ae in match.get("AE", []):
            if ae.get("G") == 1:
                for o in ae.get("ME", []):
                    if o.get("T") in [1, 2, 3] and o.get("C") is not None:
                        odds_data.append(Odds(type={1: "1", 2: "2", 3: "X"}.get(o.get("T"), "-"), cote=o.get("C")))
    return odds_data

def get_prediction(odds_data: List[Odds], team1: str, team2: str) -> str:
    if not odds_data:
        return "–"
    best = min(odds_data, key=lambda x: x.cote)
    return {
        "1": f"{team1} gagne",
        "2": f"{team2} gagne",
        "X": "Match nul"
    }.get(best.type, "–")

def parse_meteo(match: dict) -> Tuple[str, str]:
    meteo_data = match.get("MIS", [])
    temp = next((item["V"] for item in meteo_data if item.get("K") == 9), "–")
    humid = next((item["V"] for item in meteo_data if item.get("K") == 27), "–")
    return temp, humid

def parse_match(match: dict) -> MatchData:
    league = match.get("LE", "–")
    league_name = match.get("CN", "–")
    league_country = match.get("CE", "–")
    team1 = match.get("O1", "–")
    team2 = match.get("O2", "–")
    sport = detect_sport(league).strip()
    sport_name = match.get("SN", match.get("SE", sport))
    score1 = parse_score(match.get("SC", {}).get("FS", {}).get("S1"))
    score2 = parse_score(match.get("SC", {}).get("FS", {}).get("S2"))
    minute = parse_minute(match)
    status_info = parse_status(match, minute, score1, score2)
    match_ts = match.get("S", 0)
    match_time = datetime.datetime.utcfromtimestamp(match_ts).strftime('%d/%m/%Y %H:%M') if match_ts else "–"
    odds_data = parse_odds(match)
    formatted_odds = [f"{od.type}: {od.cote}" for od in odds_data] if odds_data else ["Pas de cotes disponibles"]
    prediction = get_prediction(odds_data, team1, team2)
    temp, humid = parse_meteo(match)
    event_type = match.get("T")
    match_status = match.get("HS")
    time_name = match.get("TN", "–")
    time_name_en = match.get("TNS", "–")
    return MatchData(
        team1=team1,
        team2=team2,
        score1=score1,
        score2=score2,
        league=league,
        league_name=league_name,
        league_country=league_country,
        sport=sport,
        sport_name=sport_name,
        status=status_info["statut"],
        datetime=match_time,
        temp=temp,
        humid=humid,
        odds=formatted_odds,
        prediction=prediction,
        id=match.get("I", None),
        event_type=event_type,
        match_status=match_status,
        time_name=time_name,
        time_name_en=time_name_en
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
        explication = "La prédiction est basée sur les cotes et les statistiques principales (tirs, possession, etc.)."
        odds_data = parse_odds(match)
        prediction = get_prediction(odds_data, team1, team2)
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
            "prediction": prediction
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
        explication = "La prédiction est basée sur les cotes et les statistiques principales (tirs, possession, etc.)."
        odds_data = parse_odds(match)
        prediction = get_prediction(odds_data, team1, team2)
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
            </style>
        </head><body>
            <div class="container">
                <a href="/" class="back-btn">&larr; Retour à la liste</a>
                <h2 id="teams">{team1} vs {team2}</h2>
                <p id="infos"><b>Ligue :</b> {league_name} ({league}) | <b>Pays :</b> {league_country} | <b>Sport :</b> {sport_name}</p>
                <p id="score"><b>Score :</b> {score1} - {score2}</p>
                <p id="prediction"><b>Prédiction du bot :</b> {prediction}</p>
                <p id="explication"><b>Explication :</b> {explication}</p>
                <h3>Statistiques principales</h3>
                <table class="stats-table">
                    <tr><th>Statistique</th><th>{team1}</th><th>{team2}</th></tr>
                    <tbody id="stats-tbody">
                    {''.join(f'<tr><td>{s["nom"]}</td><td>{s["s1"]}</td><td>{s["s2"]}</td></tr>' for s in stats)}
                    </tbody>
                </table>
                <canvas id="statsChart" height="200"></canvas>
            </div>
            <script>
                function updateMatchDetails() {
                    fetch(window.location.pathname.replace('/match/', '/api/match/'))
                        .then(response => response.json())
                        .then(data => {
                            if(data.error) return;
                            document.getElementById('teams').textContent = data.team1 + ' vs ' + data.team2;
                            document.getElementById('infos').innerHTML = `<b>Ligue :</b> ${data.league_name} (${data.league}) | <b>Pays :</b> ${data.league_country} | <b>Sport :</b> ${data.sport_name}`;
                            document.getElementById('score').innerHTML = `<b>Score :</b> ${data.score1} - ${data.score2}`;
                            document.getElementById('prediction').innerHTML = `<b>Prédiction du bot :</b> ${data.prediction}`;
                            document.getElementById('explication').innerHTML = `<b>Explication :</b> ${data.explication}`;
                            // Update stats table
                            const statsTbody = document.getElementById('stats-tbody');
                            statsTbody.innerHTML = '';
                            data.stats.forEach(function(s) {
                                statsTbody.innerHTML += `<tr><td>${s.nom}</td><td>${s.s1}</td><td>${s.s2}</td></tr>`;
                            });
                            // Update chart
                            if(window.statsChart) window.statsChart.destroy();
                            const labels = data.stats.map(s => s.nom);
                            const data1 = data.stats.map(s => parseFloat(s.s1.replace(',', '.')) || 0);
                            const data2 = data.stats.map(s => parseFloat(s.s2.replace(',', '.')) || 0);
                            window.statsChart = new Chart(document.getElementById('statsChart'), {
                                type: 'bar',
                                data: {
                                    labels: labels,
                                    datasets: [
                                        { label: data.team1, data: data1, backgroundColor: 'rgba(44,62,80,0.7)' },
                                        { label: data.team2, data: data2, backgroundColor: 'rgba(39,174,96,0.7)' }
                                    ]
                                },
                                options: { responsive: true, plugins: { legend: { position: 'top' } } }
                            });
                        });
                }
                setInterval(updateMatchDetails, 20000); // 20 secondes
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
