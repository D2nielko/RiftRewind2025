# RiftRewind — League of Legends Performance Tracker

A web application that analyzes League of Legends player performance using machine
learning. Enter a player's Riot ID (game name + tagline) and region to get AI-powered
performance scores (0–100) for their last 10 ranked matches, scored by role-specific
XGBoost models.

## Features

- Search players by Game Name, Tagline, and Region
- Analyzes the last 10 ranked matches
- ML-powered performance scoring (0–100) with letter grades (S, A, B, C, D, F) and an approximate percentile
- Detailed match stats: KDA, CS, damage, vision
- Supports all major regions (NA, EUW, EUNE, KR, BR, LAN, LAS, OCE, TR, RU, JP)

## Prerequisites

- Python 3.8+
- A [Riot Games API key](https://developer.riotgames.com/)
- Trained ML models (see [`ml_training/`](ml_training/))
- On macOS, XGBoost needs OpenMP: `brew install libomp`

## Installation

```bash
pip install -r requirements.txt
```

Set your Riot API key (either option works):

```bash
# Option 1: environment variable
export RIOT_API_KEY='your_api_key_here'

# Option 2: .env file
cp .env.example .env   # then edit and add your key
```

Make sure the ML models are trained (outputs into `ml_training/models/`):

```bash
cd ml_training
python train_models.py --input training_data.json --output-dir models/
cd ..
```

## Running Locally

```bash
python app.py
```

The app runs at http://localhost:5000.

1. **Homepage** — enter the player's Game Name (e.g. `Hide on bush`), Tagline
   (e.g. `KR1`), and Region, then click **Analyze Performance**.
2. **Results** — overall summary (matches, average score, win rate) plus per-match
   cards with score, grade, champion/role, KDA, CS, damage, and vision.

### Development mode (auto-reload)

```bash
export FLASK_ENV=development FLASK_DEBUG=1
python app.py
```

## API

### `GET /`
Homepage with the player search form.

### `POST /api/player-performance`
Fetch and analyze player performance.

Request body:

```json
{ "gameName": "PlayerName", "tagLine": "NA1", "region": "NA" }
```

Response (abbreviated):

```json
{
  "success": true,
  "player": { "gameName": "PlayerName", "tagLine": "NA1", "puuid": "...", "region": "NA" },
  "matches": [
    {
      "matchId": "NA1_...",
      "champion": "Ahri",
      "role": "MIDDLE",
      "performance_score": 85.5,
      "grade": "A",
      "percentile": 92.5,
      "win": true,
      "kda": "10/2/15",
      "cs": 250,
      "damage": 45000,
      "vision_score": 35,
      "game_duration": "25:30"
    }
  ],
  "summary": { "total_matches": 10, "average_score": 75.3, "wins": 6, "losses": 4 }
}
```

### `GET /results`
Results display page (loads data from `sessionStorage`).

## Performance Scoring

- **Win/Loss** (30%) — 25 pts for a win, 5 pts for a loss
- **Statistical performance** (50%) — z-score normalized against role averages from the training data
- **Impact metrics** (20%) — objectives (turrets, dragons, barons) and combat excellence

## Project Structure

```
RiftRewind2025/
├── app.py                       # Flask app + API routes + Lambda entry point (Mangum)
├── lambda_function.py           # Thin Lambda wrapper → handler from app.py
├── requirements.txt
├── templates/                   # Jinja2 templates (default frontend)
│   ├── index.html
│   ├── results.html
│   └── coach.html
├── static/css/style.css
├── static-website/              # Standalone S3/CloudFront frontend (hits API Gateway)
├── ml_training/                 # Offline ML pipeline (see ml_training/README.md)
│   ├── data_collection.py
│   ├── performance_predictor.py
│   ├── train_models.py
│   └── models/                  # Trained .pkl models + metadata
└── aws/                         # Deployment scripts
```

## Two Frontend Options

- **Flask templates** (`templates/`) — served by `app.py`. This is the default.
- **Static website** (`static-website/`) — plain HTML/CSS/JS hosted on S3/CloudFront
  that calls API Gateway directly. Set the API Gateway URL in
  `static-website/js/config.js` before deploying.

## Deployment

The backend deploys as an AWS Lambda function (via Mangum) behind API Gateway, with
models in S3 and the Riot API key in Secrets Manager. See **[DEPLOYMENT.md](DEPLOYMENT.md)**
for the full walkthrough.

For a traditional server, use a production WSGI server such as Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Riot API key not configured` | Set the `RIOT_API_KEY` environment variable (or `.env`) |
| `Performance predictor not loaded` | Train models into `ml_training/models/` |
| `Player not found` | Riot IDs are case-sensitive; check the game name, tagline, and region |
| `No matches found` | The player may have no recent ranked games |

## License / Credits

This project is not endorsed by Riot Games and does not reflect the views or opinions
of Riot Games. Built with Flask, scikit-learn & XGBoost, and the Riot Games API.
