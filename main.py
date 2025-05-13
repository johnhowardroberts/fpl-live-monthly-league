import os
import requests
from dotenv import load_dotenv
import time
import json
from datetime import datetime
from collections import defaultdict
from flask import Flask, render_template, jsonify, request

# Get the absolute path to the templates directory
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
print(f"Template directory: {template_dir}")  # Debug print

app = Flask(__name__, 
           template_folder=template_dir,
           static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'static')))

class FPLAPI:
    BASE_URL = "https://fantasy.premierleague.com/api"
    
    def __init__(self):
        self.session = requests.Session()
    
    def get_bootstrap_static(self):
        url = f"{self.BASE_URL}/bootstrap-static/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_league_standings(self, league_id: int):
        url = f"{self.BASE_URL}/leagues-classic/{league_id}/standings/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_gameweek_picks(self, team_id: int, gameweek: int):
        url = f"{self.BASE_URL}/entry/{team_id}/event/{gameweek}/picks/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

def get_gameweeks_by_month(bootstrap_data):
    """Create a mapping of months to gameweeks based on deadline times.
    Includes both finished gameweeks and gameweeks that are currently live."""
    gameweeks_by_month = defaultdict(list)
    current_time = datetime.utcnow()
    
    for event in bootstrap_data['events']:
        deadline = datetime.strptime(event['deadline_time'], "%Y-%m-%dT%H:%M:%SZ")
        # Include gameweek if it's either finished or the deadline has passed
        if event['finished'] or deadline <= current_time:
            month = deadline.strftime("%B")  # Get month name
            gameweeks_by_month[month].append(event['id'])
    
    return gameweeks_by_month

def get_current_month():
    """Get the current month name."""
    return datetime.utcnow().strftime("%B")

def get_month_data(month, league_data, fpl, gameweeks_by_month):
    """Get data for a specific month."""
    if month not in gameweeks_by_month:
        return None
        
    gameweeks = gameweeks_by_month[month]
    results = []
    
    for team in league_data['standings']['results']:
        team_id = team['entry']
        entry_name = team['entry_name']
        player_name = team['player_name']
        total = 0
        gameweek_scores = {}
        
        for gw in gameweeks:
            try:
                gw_data = fpl.get_gameweek_picks(team_id, gw)
                points = gw_data.get('entry_history', {}).get('points', 0)
                total += points
                gameweek_scores[gw] = points
                time.sleep(0.2)  # Be polite to the API
            except Exception as e:
                print(f"Error fetching data for team {entry_name} in gameweek {gw}: {e}")
                gameweek_scores[gw] = 0
        
        results.append({
            'name': entry_name,
            'player_name': player_name,
            'total': total,
            'gameweek_scores': gameweek_scores
        })
    
    results.sort(key=lambda x: x['total'], reverse=True)
    return {
        'gameweeks': sorted(gameweeks),
        'teams': results
    }

def get_monthly_data(current_month_only=False):
    fpl = FPLAPI()
    league_id = 754824

    # Get bootstrap data and create month-to-gameweek mapping
    bootstrap_data = fpl.get_bootstrap_static()
    gameweeks_by_month = get_gameweeks_by_month(bootstrap_data)
    
    # Get league data
    league_data = fpl.get_league_standings(league_id)
    
    # Initialize winnings data for all teams
    winnings = {}
    for team in league_data['standings']['results']:
        winnings[team['entry_name']] = {
            'name': team['entry_name'],
            'player_name': team['player_name'],
            'total_winnings': 0,
            'months_won': 0
        }
    
    current_time = datetime.utcnow()
    may_deadline = datetime(2025, 5, 25, 18, 10, 0)  # May 25th, 2025, 6:10pm UK time
    
    # Calculate points for each month
    monthly_data = {}
    
    if current_month_only:
        current_month = get_current_month()
        if current_month in gameweeks_by_month:
            month_data = get_month_data(current_month, league_data, fpl, gameweeks_by_month)
            if month_data:
                monthly_data[current_month] = month_data
    else:
        for month, gameweeks in sorted(gameweeks_by_month.items()):
            month_data = get_month_data(month, league_data, fpl, gameweeks_by_month)
            if month_data:
                monthly_data[month] = month_data
                
                # Calculate winnings for this month if it's not the current month
                # (except for May which is included if we're past the deadline)
                is_current_month = month == get_current_month()
                is_may = month == "May"
                include_in_winnings = not is_current_month or (is_may and current_time >= may_deadline)
                
                if include_in_winnings:
                    # Get the highest points in this month
                    highest_points = month_data['teams'][0]['total']
                    
                    # Count how many teams tied for first
                    winners = [team for team in month_data['teams'] if team['total'] == highest_points]
                    prize_per_winner = 140 / len(winners)
                    
                    # Update winnings for each winner
                    for winner in winners:
                        team_id = winner['name']
                        winnings[team_id]['total_winnings'] += prize_per_winner
                        winnings[team_id]['months_won'] += 1 / len(winners)
    
    # Convert winnings to list and sort by total winnings
    winnings_list = list(winnings.values())
    winnings_list.sort(key=lambda x: x['total_winnings'], reverse=True)
    
    return {
        'league_name': league_data['league']['name'],
        'team_count': len(league_data['standings']['results']),
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        'months': monthly_data,
        'winnings': winnings_list
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    current_month_only = request.args.get('current', 'false').lower() == 'true'
    return jsonify(get_monthly_data(current_month_only))

@app.route('/api/winnings')
def get_winnings():
    data = get_monthly_data()
    return jsonify(data['winnings'])

if __name__ == "__main__":
    print("\n" + "="*80)
    print("FPL Monthly League Web Server")
    print("="*80)
    print("\nThe server is starting up...")
    print("Once ready, you can view the league table at: http://localhost:8080")
    print("\nPress Ctrl+C to stop the server when you're done.")
    print("="*80 + "\n")
    app.run(debug=True, port=8080) 