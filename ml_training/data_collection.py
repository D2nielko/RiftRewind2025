"""
Data Collection Pipeline for League of Legends Performance Model

This script collects match data from Riot API to build a training dataset.
Run this offline to gather 5,000-10,000 matches across all roles.

Usage:
    python data_collection.py --api-key YOUR_KEY --num-matches 5000 --output training_data.json
"""

import requests
import json
import time
import argparse
import logging
from datetime import datetime
from typing import List, Dict
import random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RiotDataCollector:
    def __init__(self, api_key: str, region: str = 'na1', routing: str = 'americas'):
        self.api_key = api_key
        self.region = region  # Platform: na1, euw1, kr, etc.
        self.routing = routing  # Regional routing: americas, europe, asia
        self.headers = {'X-Riot-Token': api_key}

        # Rate limiting: 20 requests per second, 100 per 2 minutes
        self.request_count = 0
        self.request_timestamps = []

    def _rate_limit(self):
        """Implement rate limiting"""
        now = time.time()

        # Remove timestamps older than 2 minutes
        self.request_timestamps = [ts for ts in self.request_timestamps if now - ts < 120]

        # Check limits
        if len(self.request_timestamps) >= 95:  # Leave buffer
            sleep_time = 120 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                logger.info(f"Rate limit reached, sleeping for {sleep_time:.1f}s")
                time.sleep(sleep_time)
                self.request_timestamps = []

        # Add current request
        self.request_timestamps.append(now)
        time.sleep(0.05)  # Small delay between requests

    def _make_request(self, url: str) -> Dict:
        """Make API request with error handling"""
        self._rate_limit()

        try:
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning("Rate limited by Riot API, waiting...")
                time.sleep(120)
                return self._make_request(url)
            elif response.status_code == 404:
                logger.debug(f"Not found: {url}")
                return None
            else:
                logger.error(f"Error {response.status_code}: {url}")
                return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

    def get_challenger_players(self) -> List[str]:
        """Get list of high-elo player PUUIDs for quality data"""
        url = f"https://{self.region}.api.riotgames.com/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5"
        data = self._make_request(url)

        if not data:
            logger.error("Failed to fetch challenger players")
            return []

        puuids = [entry['puuid'] for entry in data['entries'][:50]]  # Top 50
        logger.info(f"Found {len(puuids)} challenger players")

        # Convert summoner IDs to PUUIDs
        logger.info(f"Collected {len(puuids)} PUUIDs")
        return puuids

    def get_match_history(self, puuid: str, count: int = 100) -> List[str]:
        """Get match IDs for a player"""
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params = {
            'type': 'ranked',
            'start': 0,
            'count': count
        }

        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        return []

    def get_match_details(self, match_id: str) -> Dict:
        """Get full match details"""
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        return self._make_request(url)

    def extract_participant_data(self, match: Dict) -> List[Dict]:
        """Extract training samples from match (all 10 players)"""
        if not match or 'info' not in match:
            return []

        match_info = match['info']

        # Skip non-standard games
        if match_info['gameDuration'] < 300:  # Less than 5 minutes
            return []
        if match_info['gameMode'] != 'CLASSIC':
            return []

        samples = []
        duration_mins = match_info['gameDuration'] / 60

        for participant in match_info['participants']:
            # Skip invalid positions
            if participant['individualPosition'] == 'Invalid' or participant['individualPosition'] == '':
                continue

            # Create training sample
            sample = {
                'match_id': match['metadata']['matchId'],
                'puuid': participant['puuid'],
                'champion': participant['championName'],
                'role': participant['individualPosition'],
                'win': int(participant['win']),
                'game_duration': duration_mins,

                # Core stats
                'kills': participant['kills'],
                'deaths': participant['deaths'],
                'assists': participant['assists'],
                'kda': participant['kills'] + participant['assists'] / max(participant['deaths'], 1),

                # Farm & Economy
                'cs': participant['totalMinionsKilled'],
                'cs_per_min': participant['totalMinionsKilled'] / duration_mins,
                'jungle_cs': participant.get('neutralMinionsKilled', 0),
                'gold': participant['goldEarned'],
                'gold_per_min': participant['goldEarned'] / duration_mins,

                # Damage
                'damage_dealt': participant['totalDamageDealtToChampions'],
                'damage_per_min': participant['totalDamageDealtToChampions'] / duration_mins,
                'damage_taken': participant['totalDamageTaken'],
                'damage_taken_per_min': participant['totalDamageTaken'] / duration_mins,
                'damage_mitigated': participant['damageSelfMitigated'],
                'damage_share': participant['challenges'].get('teamDamagePercentage', 0),

                # Vision
                'vision_score': participant['visionScore'],
                'vision_per_min': participant['visionScore'] / duration_mins,
                'wards_placed': participant['wardsPlaced'],
                'wards_killed': participant['wardsKilled'],
                'control_wards': participant['challenges'].get('controlWardsPlaced', 0),

                # Objectives
                'turret_plates': participant['challenges'].get('turretPlatesTaken', 0),
                'turrets': participant['turretKills'],
                'dragons': participant.get('dragonKills', 0),
                'barons': participant.get('baronKills', 0),

                # Early game
                'cs_at_10': participant['challenges'].get('laneMinionsFirst10Minutes', 0) or
                           participant['challenges'].get('jungleCsBefore10Minutes', 0),
                'cs_advantage': participant['challenges'].get('maxCsAdvantageOnLaneOpponent', 0),
                'gold_advantage': 1 if participant['challenges'].get('earlyLaningPhaseGoldExpAdvantage', 0) > 0 else 0,

                # Combat effectiveness
                'kill_participation': participant['challenges'].get('killParticipation', 0),
                'solo_kills': participant['challenges'].get('soloKills', 0),
                'multikills': participant['doubleKills'] + participant['tripleKills'] * 2 +
                             participant['quadraKills'] * 3 + participant['pentaKills'] * 4,

                # Utility
                'cc_time': participant['timeCCingOthers'],
                'healing': participant['totalHeal'],
                'shielding': participant['totalDamageShieldedOnTeammates'],

                # Deaths & Time
                'time_dead': participant['totalTimeSpentDead'],
                'time_dead_pct': participant['totalTimeSpentDead'] / match_info['gameDuration'],
                'longest_living': participant['longestTimeSpentLiving'],

                # Mechanics (from challenges)
                'skillshots_hit': participant['challenges'].get('skillshotsHit', 0),
                'skillshots_dodged': participant['challenges'].get('skillshotsDodged', 0),

                # First actions
                'first_blood': int(participant.get('firstBloodKill', False)),
                'first_tower': int(participant.get('firstTowerKill', False)),
            }

            samples.append(sample)

        return samples

    def collect_training_data(self, num_matches: int = 5000, seed_puuids: List[str] = None) -> List[Dict]:
        """Main collection loop"""
        logger.info(f"Starting data collection for {num_matches} matches")

        if not seed_puuids:
            logger.info("Fetching challenger players as seeds...")
            seed_puuids = self.get_challenger_players()

        if not seed_puuids:
            logger.error("No seed players found!")
            return []

        collected_matches = set()
        training_samples = []
        puuid_queue = seed_puuids.copy()
        random.shuffle(puuid_queue)

        while len(collected_matches) < num_matches and puuid_queue:
            puuid = puuid_queue.pop(0)

            logger.info(f"Progress: {len(collected_matches)}/{num_matches} matches, "
                       f"{len(training_samples)} samples collected")

            # Get match history
            match_ids = self.get_match_history(puuid, count=20)

            for match_id in match_ids:
                if match_id in collected_matches:
                    continue

                if len(collected_matches) >= num_matches:
                    break

                # Get match details
                match_data = self.get_match_details(match_id)

                if not match_data:
                    continue

                # Extract samples from all 10 players
                samples = self.extract_participant_data(match_data)

                if samples:
                    training_samples.extend(samples)
                    collected_matches.add(match_id)

                    # Add new players to queue for snowball sampling
                    for sample in samples:
                        if sample['puuid'] not in puuid_queue and len(puuid_queue) < 200:
                            puuid_queue.append(sample['puuid'])

                    logger.info(f"✓ Match {match_id}: {len(samples)} samples")

        logger.info(f"Collection complete: {len(collected_matches)} matches, "
                   f"{len(training_samples)} training samples")

        return training_samples

def main():
    parser = argparse.ArgumentParser(description='Collect LoL match data for ML training')
    parser.add_argument('--api-key', required=True, help='Riot API key')
    parser.add_argument('--num-matches', type=int, default=5000, help='Number of matches to collect')
    parser.add_argument('--output', default='training_data.json', help='Output file')
    parser.add_argument('--region', default='na1', help='Region (na1, euw1, kr, etc.)')
    parser.add_argument('--routing', default='americas', help='Routing (americas, europe, asia)')

    args = parser.parse_args()

    collector = RiotDataCollector(args.api_key, args.region, args.routing)

    # Collect data
    training_data = collector.collect_training_data(args.num_matches)

    # Save to file
    output_data = {
        'collection_date': datetime.utcnow().isoformat(),
        'num_matches': len(set(s['match_id'] for s in training_data)),
        'num_samples': len(training_data),
        'samples': training_data
    }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    logger.info(f"Data saved to {args.output}")

    # Print statistics
    role_counts = {}
    for sample in training_data:
        role = sample['role']
        role_counts[role] = role_counts.get(role, 0) + 1

    logger.info("\nRole distribution:")
    for role, count in sorted(role_counts.items()):
        logger.info(f"  {role}: {count} samples")

if __name__ == '__main__':
    main()
