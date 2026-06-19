# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RiftRewind is a League of Legends performance tracker. It uses the Riot API to fetch a player's last 10 ranked matches and scores each game 0–100 using role-specific XGBoost ML models. The backend is a Flask app deployed as an AWS Lambda function (via Mangum). The frontend is either Flask-rendered templates (Jinja2) or a standalone static website that calls API Gateway.

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# On Mac, XGBoost requires OpenMP:
brew install libomp

# Set your Riot API key
export RIOT_API_KEY=your_key_here

# Start the Flask dev server
python app.py
```

The app runs on `http://localhost:5000`.

## ML Pipeline

The ML pipeline lives entirely in `ml_training/` and must be run offline before deploying.

**Step 1 – Collect training data** (2–4 hours, Challenger-level matches):
```bash
cd ml_training
python data_collection.py \
  --api-key YOUR_KEY \
  --num-matches 5000 \
  --output training_data.json \
  --region na1 --routing americas
```

**Step 2 – Train models:**
```bash
python train_models.py --input training_data.json --output-dir models/
```
Outputs 5 `.pkl` files plus `model_metadata.json` and `features.json` into `models/`.

**Step 3 – Run tests:**
```bash
python ml_training/test_models.py
python ml_training/test_prediction.py
```

## Architecture

### Request flow
1. User submits `gameName`, `tagLine`, `region` via the web form.
2. `app.py:/api/player-performance` calls the Riot Account API to resolve the PUUID, then fetches the last 10 ranked match IDs and full match details via `RiotDataCollector`.
3. For each match, `PerformancePredictor.predict_performance()` runs the role-specific XGBoost model and returns a score (0–100), letter grade, and approximate percentile.
4. Results are returned as JSON and rendered by `templates/results.html`.

### Key modules
| File | Role |
|------|------|
| `app.py` | Flask app + API routes + Lambda entry point via `Mangum(app)` |
| `lambda_function.py` | Thin wrapper: calls `handler` from `app.py` |
| `ml_training/data_collection.py` | `RiotDataCollector` – fetches and extracts training samples from Riot API |
| `ml_training/performance_predictor.py` | `PerformancePredictor` – loads `.pkl` models and scores participants |
| `ml_training/train_models.py` | Trains one `XGBRegressor` per role using computed performance scores |
| `coaching/` | Cohere retrieval layer — NL coaching over recent matches + Data Dragon docs (see `coaching/README.md`) |
| `static-website/` | Standalone frontend (S3/CloudFront) that hits API Gateway directly |
| `lambda-deploy/` | Snapshot of Lambda deployment artifacts |

### Coaching retrieval layer (`coaching/`)
A second feature on top of the same Riot ingestion. `RiotDataCollector` is
reused to pull ~20 matches, normalized to YAML chunks, combined with ~400 Data
Dragon champion/item/patch chunks. The corpus is embedded once with Cohere
`embed-v4.0` and cached to `coaching/cache/` (content-hash keyed; rebuilds only
re-embed changed chunks). A query runs embed → cosine top-50 → `rerank-v3.5`
top-5 → `command-a` grounded answer with `[S#]` citations. Exposed at `/coach`
(UI) and `/api/coach` (JSON). Build the cache first:
`python -m coaching.pipeline build --game-name NAME --tag-line TAG`. The cohere
import in `app.py:/api/coach` is lazy so the base app boots without the dep.
Requires `COHERE_API_KEY` in addition to `RIOT_API_KEY`.

### Model loading
At startup, `PerformancePredictor` loads models either from a local `ml_training/models/` directory (local dev) or from an S3 bucket (`MODELS_BUCKET` env var). The `SECRET_NAME` env var (`riftrewind/riot-api-key` by default) controls where the Riot API key is fetched from AWS Secrets Manager; falls back to `RIOT_API_KEY` env var.

### Performance scoring formula
- **Win/Loss** 30% — 25 pts for win, 5 pts for loss
- **Statistical performance** 50% — z-score normalized vs role averages across training data
- **Impact metrics** 20% — objectives (turrets, dragons, barons), combat excellence

### AWS deployment components
- **Lambda** — `lambda_function.py` → `app.py` (Mangum bridges ASGI/WSGI)
- **API Gateway** — proxies HTTP requests to Lambda
- **S3** — stores trained model `.pkl` files and optionally hosts the static frontend
- **Secrets Manager** — stores `RIOT_API_KEY`
- **Lambda Layer** — pre-built `lambda-layer/` contains Flask, boto3, scikit-learn, XGBoost, numpy, etc.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `RIOT_API_KEY` | — | Riot Games API key (required) |
| `COHERE_API_KEY` | — | Cohere key for the `/coach` retrieval layer |
| `SECRET_NAME` | `riftrewind/riot-api-key` | AWS Secrets Manager secret name |
| `MODELS_BUCKET` | — | S3 bucket for model `.pkl` files |
| `AWS_REGION` | `us-east-1` | AWS region |

Copy `.env.example` to `.env` and populate `RIOT_API_KEY` for local development.

## Static Website vs Flask Templates

Two frontend options exist:
- **Flask templates** (`templates/`): served by `app.py`, use Jinja2 and `url_for`. This is the default.
- **Static website** (`static-website/`): plain HTML/CSS/JS that calls API Gateway. Update `static-website/js/config.js` with the API Gateway URL before deploying to S3.
