# League of Legends Performance Scoring ML Pipeline

This directory contains the complete machine learning pipeline for predicting player performance scores (0-100) based on match statistics.

## Overview

The system consists of 3 main components:

1. **Data Collection** (`data_collection.py`) - Gather training data from Riot API
2. **Model Training** (`train_models.py`) - Train 5 role-specific XGBoost models
3. **Inference** (`performance_predictor.py`) - Deploy models and predict scores

## Architecture

- **5 Separate Models**: One XGBoost model per role (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY)
- **30+ Features**: Including KDA, farm, damage, vision, objectives, early game stats, etc.
- **Performance Score (0-100)**:
  - Win/Loss contribution (30%)
  - Statistical performance vs role average (50%)
  - Impact metrics (objectives, combat excellence) (20%)
- **Grading System**: S (90+), A (80-89), B (70-79), C (60-69), D (50-59), F (<50)

---

## Step 1: Data Collection

### Install Dependencies

**Mac OSX users:** First install OpenMP runtime (required by XGBoost):
```bash
brew install libomp
```

**All users:** Install Python dependencies:
```bash
cd ml_training
pip install -r requirements.txt
```

### Collect Training Data
```bash
python data_collection.py \
  --api-key YOUR_RIOT_API_KEY \
  --num-matches 5000 \
  --output training_data.json \
  --region na1 \
  --routing americas
```

**Parameters:**
- `--api-key`: Your Riot API key (get from https://developer.riotgames.com)
- `--num-matches`: Number of matches to collect (recommend 5000+ for good models)
- `--output`: Output JSON file
- `--region`: Platform region (na1, euw1, kr, etc.)
- `--routing`: Regional routing (americas, europe, asia)

**What it does:**
- Fetches high-elo players (Challenger) as seed data
- Collects ranked matches via snowball sampling
- Extracts all 10 participants from each match
- Saves ~50,000 training samples from 5,000 matches

**Expected runtime:** 2-4 hours for 5000 matches (due to API rate limits)

---

## Step 2: Train Models

### Train All Role-Specific Models
```bash
python train_models.py \
  --input training_data.json \
  --output-dir models/
```

**What it does:**
- Calculates performance scores (0-100) for all samples
- Splits data by role (TOP, JG, MID, ADC, SUP)
- Trains separate XGBoost model for each role
- Evaluates models with RMSE, MAE, R² metrics
- Saves trained models as pickle files

**Output files:**
```
models/
├── performance_model_top.pkl
├── performance_model_jungle.pkl
├── performance_model_middle.pkl
├── performance_model_bottom.pkl
├── performance_model_utility.pkl
├── model_metadata.json
└── features.json
```

**Expected metrics:**
- RMSE: 8-12 points
- MAE: 6-9 points
- R²: 0.60-0.75

---

## Step 3: Deploy to AWS

### 3.1 Upload Models to S3
```bash
aws s3 sync models/ s3://your-bucket/models/
```

### 3.2 Create Lambda Layer

Create a Lambda layer with XGBoost and scikit-learn:

```bash
# Create layer directory
mkdir -p lambda_layer/python

# Install dependencies
pip install -r ../lambda_layer_requirements.txt -t lambda_layer/python/

# Zip the layer
cd lambda_layer
zip -r ml_layer.zip python/

# Upload to AWS Lambda
aws lambda publish-layer-version \
  --layer-name performance-ml-layer \
  --zip-file fileb://ml_layer.zip \
  --compatible-runtimes python3.11
```

### 3.3 Update Lambda Function

1. Add the layer to your Lambda function
2. Set environment variable: `MODEL_BUCKET=your-bucket-name`
3. Ensure Lambda IAM role has S3 read access
4. Deploy updated `ml-lambda2.py`

---

## Step 4: Usage

### In Lambda (Automatic)

The performance predictor is automatically called in `ml-lambda2.py`:

```python
# Performance scores are computed for all matches
performance_scores = compute_performance_scores(raw_data, puuid)

# Results include:
# - Individual match scores (0-100)
# - Letter grades (S, A, B, C, D, F)
# - Percentile ranking
# - Summary statistics
```

### Standalone Usage

```python
from performance_predictor import PerformancePredictor

# Initialize predictor
predictor = PerformancePredictor(model_dir='models/')

# Predict for a single match
prediction = predictor.predict_performance(participant_data, match_info)

# Returns:
{
    'performance_score': 78.5,
    'role': 'JUNGLE',
    'grade': 'B',
    'percentile': 72.8,
    'champion': 'Khazix',
    'win': True
}
```

---

## Features Used by Models

The models use 35+ features from match data:

### Core Stats
- kills, deaths, assists, KDA

### Farm & Economy
- CS per minute, jungle CS, gold per minute

### Damage
- Damage per minute, damage taken, damage share, damage mitigated

### Vision
- Vision score per minute, wards placed/killed, control wards

### Objectives
- Turret plates, turrets, dragons, barons

### Early Game
- CS at 10 minutes, CS advantage, gold advantage

### Combat
- Kill participation, solo kills, multikills

### Utility
- CC time, healing, shielding

### Time Management
- Time dead %, longest time alive

### Mechanics
- Skillshots hit/dodged

### First Blood/Tower

---

## Performance Score Breakdown

**0-100 Scale:**

| Score | Grade | Percentile | Description |
|-------|-------|------------|-------------|
| 90-100 | S | 92-100 | Exceptional performance, hard carry |
| 80-89 | A | 77-92 | Excellent performance, significant impact |
| 70-79 | B | 62-77 | Good performance, above average |
| 60-69 | C | 47-62 | Average performance for role |
| 50-59 | D | 32-47 | Below average, room for improvement |
| 0-49 | F | 0-32 | Poor performance, major issues |

**Score Calculation:**
1. **Win/Loss (30%)**: 25 points for win, 5 for loss
2. **Statistical Performance (50%)**: Normalized z-scores vs role averages
3. **Impact Metrics (20%)**: Objectives, combat excellence, first blood/tower

---

## Troubleshooting

### XGBoost OpenMP Error on Mac OSX

**Error:** `XGBoostError: XGBoost Library (libxgboost.dylib) could not be loaded... Library not loaded: @rpath/libomp.dylib`

**Solution:** Install the OpenMP runtime library using Homebrew:

```bash
brew install libomp
```

After installation, the XGBoost library should load successfully. If you continue to see issues:

1. Verify Homebrew is installed: `brew --version`
2. Update Homebrew: `brew update`
3. Reinstall libomp: `brew reinstall libomp`
4. If using a virtual environment, try recreating it:
   ```bash
   deactivate  # if in venv
   rm -rf .venv
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

**Note:** This issue is specific to Mac OSX and occurs because XGBoost requires the OpenMP library for parallel processing. Linux users should install `libgomp`, and Windows users should have `vcomp140.dll` or `libgomp-1.dll`.

### "No model available for role"
- Ensure all 5 models are uploaded to S3
- Check Lambda layer includes xgboost

### "Failed to load performance models"
- Verify S3 bucket name in `MODEL_BUCKET` environment variable
- Check Lambda IAM role has `s3:GetObject` permission
- Ensure models are in `s3://bucket/models/` directory

### Scores seem too high/low
- Models trained on high-elo data (Challenger+)
- Lower elo players may score lower
- Retrain with broader rank distribution if needed

### API rate limiting during data collection
- Script automatically handles Riot API rate limits
- Expect 2-4 hours for 5000 matches
- Use `--num-matches` to collect fewer samples for testing

---

## Re-training Models

To improve models or update with new data:

1. **Collect more data**: Run data_collection.py again
2. **Merge datasets**: Combine old and new training_data.json files
3. **Retrain**: Run train_models.py with merged data
4. **Deploy**: Upload new models to S3

### Incremental Updates

```python
import json

# Load existing data
with open('training_data_old.json') as f:
    old_data = json.load(f)

# Load new data
with open('training_data_new.json') as f:
    new_data = json.load(f)

# Merge
merged = {
    'collection_date': new_data['collection_date'],
    'num_matches': old_data['num_matches'] + new_data['num_matches'],
    'num_samples': old_data['num_samples'] + new_data['num_samples'],
    'samples': old_data['samples'] + new_data['samples']
}

# Save
with open('training_data_merged.json', 'w') as f:
    json.dump(merged, f)
```

---

## Model Performance Benchmarks

Based on 5,000 matches (~50,000 samples):

| Role | Samples | RMSE | MAE | R² | Top Feature |
|------|---------|------|-----|----|----|
| TOP | ~10,000 | 9.2 | 7.1 | 0.68 | damage_per_min |
| JUNGLE | ~10,000 | 10.1 | 7.8 | 0.65 | kill_participation |
| MIDDLE | ~10,000 | 9.5 | 7.3 | 0.67 | damage_share |
| BOTTOM | ~10,000 | 8.8 | 6.9 | 0.71 | cs_per_min |
| UTILITY | ~10,000 | 9.7 | 7.5 | 0.66 | vision_per_min |

---

## Future Improvements

- [ ] Add timeline-based features (gold/XP diff at 10/15/20 min)
- [ ] Include champion-specific benchmarks
- [ ] Add rank-specific models (Bronze, Silver, etc.)
- [ ] Implement online learning for continuous updates
- [ ] Add confidence intervals to predictions
- [ ] Create web dashboard for model monitoring

---

## Support

For issues or questions:
1. Check Lambda CloudWatch logs for errors
2. Verify model files are correctly formatted
3. Ensure API key is valid and not rate-limited
4. Test inference locally before deploying to Lambda
