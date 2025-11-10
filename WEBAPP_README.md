# RiftRewind - League of Legends Performance Tracker

A web application that analyzes League of Legends player performance using machine learning models. Enter a player's game name, tagline, and region to view AI-powered performance scores for their last 10 ranked matches.

## Features

- Search players by Game Name, Tagline, and Region
- Analyze performance across the last 10 ranked matches
- ML-powered performance scoring (0-100) with letter grades (S, A, B, C, D, F)
- Detailed match statistics including KDA, CS, damage, and vision
- Beautiful League of Legends themed UI
- Support for all major regions (NA, EUW, EUNE, KR, BR, LAN, LAS, OCE, TR, RU, JP)

## Prerequisites

- Python 3.8+
- Riot Games API Key (get one at https://developer.riotgames.com/)
- Trained ML models (see ml_training directory)

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your Riot API key:
```bash
# Option 1: Export as environment variable
export RIOT_API_KEY='your_api_key_here'

# Option 2: Create .env file (copy from .env.example)
cp .env.example .env
# Then edit .env and add your API key
```

3. Ensure ML models are trained:
```bash
cd ml_training
python train_models.py --input training_data.json --output-dir models/
cd ..
```

## Running the Application

Start the Flask development server:

```bash
python app.py
```

The application will be available at:
- **URL**: http://localhost:5000
- **Homepage**: Enter player information
- **Results**: View performance analysis

## How to Use

1. **Homepage**:
   - Enter the player's Game Name (e.g., "Hide on bush")
   - Enter the Tagline (e.g., "KR1")
   - Select the Region from the dropdown
   - Click "Analyze Performance"

2. **Results Page**:
   - View overall summary (total matches, average score, win rate)
   - See detailed match cards with:
     - Performance score (0-100)
     - Letter grade (S, A, B, C, D, F)
     - Champion played and role
     - KDA, CS, damage, and vision score
     - Match duration and result

## API Endpoints

### `GET /`
Homepage with player search form

### `POST /api/player-performance`
Fetch and analyze player performance

**Request Body**:
```json
{
  "gameName": "PlayerName",
  "tagLine": "NA1",
  "region": "NA"
}
```

**Response**:
```json
{
  "success": true,
  "player": {
    "gameName": "PlayerName",
    "tagLine": "NA1",
    "puuid": "...",
    "region": "NA"
  },
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
  "summary": {
    "total_matches": 10,
    "average_score": 75.3,
    "wins": 6,
    "losses": 4
  }
}
```

### `GET /results`
Results display page (loads data from sessionStorage)

## Project Structure

```
RiftRewind2025/
├── app.py                  # Flask application
├── requirements.txt        # Python dependencies
├── templates/
│   ├── index.html         # Homepage
│   └── results.html       # Results page
├── static/
│   └── css/
│       └── style.css      # Styles
├── ml_training/
│   ├── data_collection.py         # Riot API data collector
│   ├── performance_predictor.py   # ML prediction module
│   ├── train_models.py           # Model training script
│   └── models/                    # Trained models
│       ├── performance_model_top.pkl
│       ├── performance_model_jungle.pkl
│       ├── performance_model_middle.pkl
│       ├── performance_model_bottom.pkl
│       ├── performance_model_utility.pkl
│       ├── model_metadata.json
│       └── features.json
```

## Supported Regions

| Code | Region |
|------|--------|
| NA   | North America |
| EUW  | Europe West |
| EUNE | Europe Nordic & East |
| KR   | Korea |
| BR   | Brazil |
| LAN  | Latin America North |
| LAS  | Latin America South |
| OCE  | Oceania |
| TR   | Turkey |
| RU   | Russia |
| JP   | Japan |

## Troubleshooting

**"Riot API key not configured"**
- Make sure you've set the `RIOT_API_KEY` environment variable

**"Performance predictor not loaded"**
- Ensure models are trained and located in `ml_training/models/`
- Run the training script: `python ml_training/train_models.py`

**"Player not found"**
- Verify the Game Name and Tagline are correct
- Ensure you selected the correct region
- Remember: Riot IDs are case-sensitive

**"No matches found"**
- Player may not have played any ranked games recently
- Try a different player or region

## Development

To run in development mode with auto-reload:

```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py
```

## Production Deployment

For production deployment:

1. Use a production WSGI server (e.g., Gunicorn):
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

2. Set up environment variables securely
3. Configure a reverse proxy (nginx/Apache)
4. Enable HTTPS

## License

This project is not endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties.

## Credits

Built using:
- Flask (Web Framework)
- scikit-learn & XGBoost (ML Models)
- Riot Games API
