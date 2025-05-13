# FPL Monthly League Web App

A web application that displays monthly leaderboards and winnings for a Fantasy Premier League mini-league.

## Features

- Monthly leaderboard showing points for each gameweek
- Total points and points off lead calculations
- Winnings leaderboard showing total winnings and months won
- Tabbed interface for easy navigation between views
- Responsive design

## Local Development

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd fpl_api_debug
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your FPL league ID:
```
FPL_LEAGUE_ID=754824
```

### Running the Application

Start the Flask development server:
```bash
python main.py
```

The application will be available at http://localhost:8080

## Project Structure

- `main.py` - Flask application and FPL API integration
- `templates/` - HTML templates
  - `base.html` - Base template with common layout and styles
  - `index.html` - Main page template
- `static/` - Static files (CSS, JavaScript, images)
- `requirements.txt` - Python dependencies

## Deployment

The application is designed to be deployed on Render with the frontend hosted on GitHub Pages.

## Version History

### v1.0.0 (Current)
- Initial working version with monthly and winnings leaderboards
- Tabbed interface
- Responsive design
- Local development setup 