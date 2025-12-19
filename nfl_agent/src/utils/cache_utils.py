# cache tools for 3rd party calls (espn api)

from cachetools import TTLCache

# TTL caches (5 minute expiration)
teams_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
standings_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
roster_cache: TTLCache = TTLCache(maxsize=32, ttl=300)


def clear_cache() -> None:
    teams_cache.clear()
    standings_cache.clear()
    roster_cache.clear()


_client = None


def get_espn_client():
    from nfl_agent.src.utils.client import ESPNClient

    global _client
    if _client is None:
        _client = ESPNClient()
    return _client
