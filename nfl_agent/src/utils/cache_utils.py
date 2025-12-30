# cache tools for 3rd party calls (espn api)

from cachetools import TTLCache

# TTL caches with appropriate expiration times
teams_cache: TTLCache = TTLCache(maxsize=32, ttl=300)  # Team info: 5 minutes
depth_cache: TTLCache = TTLCache(
    maxsize=32, ttl=604800
)  # Depth charts: 1 week (7 days)
athlete_cache: TTLCache = TTLCache(
    maxsize=200, ttl=86400
)  # Athlete bio: 1 day (24 hours)
stats_cache: TTLCache = TTLCache(maxsize=200, ttl=3600)  # Player stats: 1 hour


def clear_cache() -> None:
    teams_cache.clear()
    depth_cache.clear()
    athlete_cache.clear()
    stats_cache.clear()
    standings_cache.clear()
    roster_cache.clear()


_client = None


def get_espn_client():
    from nfl_agent.src.utils.espn_client import ESPNClient

    global _client
    if _client is None:
        _client = ESPNClient()
    return _client
