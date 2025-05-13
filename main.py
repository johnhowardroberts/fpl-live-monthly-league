import os
import requests
from dotenv import load_dotenv
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, render_template, jsonify, request
import hashlib
import pickle
from pathlib import Path
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get the absolute path to the templates directory
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
logger.info(f"Template directory: {template_dir}")

# Log environment information
logger.info("\nEnvironment Information:")
logger.info(f"Python version: {sys.version}")
logger.info(f"Platform: {sys.platform}")
logger.info(f"Running on Render: {'RENDER' in os.environ}")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Environment variables: {dict(os.environ)}")

app = Flask(__name__, 
           template_folder=template_dir,
           static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'static')))

class FPLAPI:
    BASE_URL = "https://fantasy.premierleague.com/api"
    CACHE_DIR = Path("cache")
    CACHE_DURATION = timedelta(minutes=5)
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': 'https://fantasy.premierleague.com',
            'Referer': 'https://fantasy.premierleague.com/',
            'sec-ch-ua': '"Chromium";v="136", "Not(A:Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'DNT': '1'
        })
        
        # Create cache directory if it doesn't exist
        self.CACHE_DIR.mkdir(exist_ok=True)
        
        # Add a small delay between requests
        self.last_request_time = 0
        self.min_request_interval = 1.0  # seconds
        
        # Initialize with a visit to the main page to get cookies
        try:
            logger.info("\nInitializing FPL API session...")
            response = self.session.get('https://fantasy.premierleague.com/')
            logger.info(f"Initial page visit status: {response.status_code}")
            logger.info(f"Cookies received: {dict(self.session.cookies)}")
        except Exception as e:
            logger.error(f"Error during initialization: {e}")
    
    def _wait_before_request(self):
        """Ensure we don't make requests too quickly."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last_request)
        self.last_request_time = time.time()
    
    def _get_cache_path(self, url):
        """Generate a cache file path for a URL."""
        cache_key = hashlib.md5(url.encode()).hexdigest()
        return self.CACHE_DIR / f"{cache_key}.cache"
    
    def _is_cache_valid(self, cache_path):
        """Check if the cache is still valid."""
        if not cache_path.exists():
            return False
        cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        return cache_age < self.CACHE_DURATION
    
    def _get_from_cache(self, url):
        """Get data from cache if available and valid."""
        cache_path = self._get_cache_path(url)
        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
            except:
                return None
        return None
    
    def _save_to_cache(self, url, data):
        """Save data to cache."""
        cache_path = self._get_cache_path(url)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
        except:
            pass
    
    def _make_request(self, url):
        """Make a request with caching and rate limiting."""
        # Try to get from cache first
        cached_data = self._get_from_cache(url)
        if cached_data is not None:
            logger.info(f"\nUsing cached data for {url}")
            return cached_data
        
        # If not in cache or cache invalid, make the request
        try:
            self._wait_before_request()
            logger.info(f"\nMaking request to {url}")
            logger.info(f"Request headers: {dict(self.session.headers)}")
            logger.info(f"Current cookies: {dict(self.session.cookies)}")
            
            response = self.session.get(url, timeout=10)
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            
            if response.status_code == 403:
                logger.error("403 Forbidden received. Full response:")
                logger.error(response.text)
            
            response.raise_for_status()
            data = response.json()
            self._save_to_cache(url, data)
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to {url}: {e}")
            # If request fails, try to return cached data even if expired
            cached_data = self._get_from_cache(url)
            if cached_data is not None:
                logger.info("Using expired cache data due to request failure")
                return cached_data
            raise
    
    def get_bootstrap_static(self):
        """Get bootstrap data using the newer endpoint."""
        url = f"{self.BASE_URL}/bootstrap-dynamic/"
        return self._make_request(url)
    
    def get_league_standings(self, league_id: int):
        """Get league standings using the newer endpoint."""
        url = f"{self.BASE_URL}/leagues-classic/{league_id}/standings/"
        return self._make_request(url)

    def get_gameweek_picks(self, team_id: int, gameweek: int):
        """Get gameweek picks using the newer endpoint."""
        url = f"{self.BASE_URL}/entry/{team_id}/event/{gameweek}/picks/"
        return self._make_request(url)

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
                logger.error(f"Error fetching data for team {entry_name} in gameweek {gw}: {e}")
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
    league_id = int(os.getenv('FPL_LEAGUE_ID', '754824'))

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
    port = int(os.getenv('PORT', 8080))
    print("\n" + "="*80)
    print("FPL Monthly League Web Server")
    print("="*80)
    print("\nThe server is starting up...")
    print(f"Once ready, you can view the league table at: http://localhost:{port}")
    print("\nPress Ctrl+C to stop the server when you're done.")
    print("="*80 + "\n")
    app.run(debug=True, port=port) 