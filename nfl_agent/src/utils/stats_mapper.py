import asyncio
from typing import List, Literal, Optional, Dict, Any

from nfl_agent.src.utils.client_protocol import StatsClientProtocol
from nfl_agent.src.models.espn_responses import (
    ESPNAthleteResponse,
    ESPNStatisticsResponse,
)
from nfl_agent.src.models.stats import (
    QbPlayer,
    SkillPlayer,
    DefPlayer,
    InjuredPlayer,
    Team,
)


def compute_position_class(position_abbr: str) -> Literal["QB", "SKILL", "OL", "DEF"]:
    position_upper = position_abbr.upper()

    if position_upper == "QB":
        return "QB"
    elif position_upper in ["WR", "RB", "TE", "FB"]:
        return "SKILL"
    elif position_upper in ["C", "LG", "RG", "LT", "RT", "G", "T", "OL"]:
        return "OL"
    else:
        return "DEF"


def map_injury_status(
    injuries: List[Any],
) -> Literal["out", "questionable", "doubtful", "active"]:
    if not injuries:
        return "active"

    injury = injuries[0]
    status = injury.status.lower() if hasattr(injury, "status") else ""
    type_name = (
        injury.type.name.upper()
        if hasattr(injury, "type") and hasattr(injury.type, "name")
        else ""
    )

    if "OUT" in status.upper() or "OUT" in type_name or "INJURED RESERVE" in type_name:
        return "out"
    elif "QUESTIONABLE" in status.upper() or "QUESTIONABLE" in type_name:
        return "questionable"
    elif "DOUBTFUL" in status.upper() or "DOUBTFUL" in type_name:
        return "doubtful"
    else:
        return "active"


def build_qb_player(
    athlete: ESPNAthleteResponse,
    stats: ESPNStatisticsResponse,
    team_abbr: str,
) -> QbPlayer:
    return QbPlayer(
        name=athlete.fullName,
        team=team_abbr,
        position=athlete.position.abbreviation,
        position_class="QB",
        height=int(athlete.height),
        weight=athlete.weight,
        age=athlete.age,
        passing_yards=stats.extract_stat_with_fallback("passing", ["Passing Yards"]),
        passing_attempts=stats.extract_stat_with_fallback(
            "passing", ["Passing Attempts"]
        ),
        completions=stats.extract_stat_with_fallback("passing", ["Completions"]),
        completion_pct=stats.extract_stat_with_fallback(
            "passing", ["Completion Percentage"]
        ),
        passer_rating=stats.extract_stat_with_fallback(
            "passing", ["Passer Rating", "Quarterback Rating"]
        ),
        net_yards_per_pass_attempt=stats.extract_stat_with_fallback(
            "passing", ["Net Yards Per Pass Attempt"]
        ),
        passing_touchdowns=stats.extract_stat_with_fallback(
            "passing", ["Passing Touchdowns"]
        ),
        interceptions=stats.extract_stat_with_fallback("passing", ["Interceptions"]),
        fumbles_lost=stats.extract_stat_with_fallback("general", ["Fumbles Lost"]),
        sacks_taken=stats.extract_stat_with_fallback("passing", ["Total Sacks"]),
    )


def build_skill_player(
    athlete: ESPNAthleteResponse,
    stats: ESPNStatisticsResponse,
    team_abbr: str,
) -> SkillPlayer:
    stat_lookup: Dict[str, float] = {}
    for cat in stats.splits.categories:
        for s in cat.stats:
            if s.displayName:
                stat_lookup[s.displayName] = float(s.value or 0.0)

    games_played = int(stat_lookup.get("Games Played", 0))

    targets = int(stat_lookup.get("Receiving Targets", 0))
    receptions = int(stat_lookup.get("Receptions", 0))
    receiving_yards = int(stat_lookup.get("Receiving Yards", 0))

    rushing_attempts = int(stat_lookup.get("Rushing Attempts", 0))
    rushing_yards = int(stat_lookup.get("Rushing Yards", 0))

    yards_from_scrimmage = int(
        stat_lookup.get("Total Yards From Scrimmage", receiving_yards + rushing_yards)
    )

    total_touchdowns = int(
        stat_lookup.get(
            "Total Touchdowns",
            int(stat_lookup.get("Receiving Touchdowns", 0))
            + int(stat_lookup.get("Rushing Touchdowns", 0)),
        )
    )

    fumbles_lost = int(stat_lookup.get("Fumbles Lost", 0))
    touches = rushing_attempts + receptions

    return SkillPlayer(
        name=athlete.fullName,
        team=team_abbr,
        position=athlete.position.abbreviation,
        position_class="SKILL",
        height=int(athlete.height),
        weight=athlete.weight,
        age=athlete.age,
        games_played=games_played,
        targets=targets,
        receptions=receptions,
        rushing_attempts=rushing_attempts,
        touches=touches,
        receiving_yards=receiving_yards,
        rushing_yards=rushing_yards,
        yards_from_scrimmage=yards_from_scrimmage,
        total_touchdowns=total_touchdowns,
        fumbles_lost=fumbles_lost,
    )


def build_def_player(
    athlete: ESPNAthleteResponse,
    stats: ESPNStatisticsResponse,
    team_abbr: str,
) -> DefPlayer:
    stat_lookup: Dict[str, float] = {}
    for cat in stats.splits.categories:
        for s in cat.stats:
            if s.displayName:
                stat_lookup.setdefault(s.displayName, float(s.value or 0.0))

    games_played = (
        int(stat_lookup["Games Played"]) if "Games Played" in stat_lookup else None
    )

    total_tackles = stat_lookup.get("Total Tackles")
    solo_tackles = stat_lookup.get("Solo Tackles")
    sacks = stat_lookup.get("Sacks")
    qb_hits = stat_lookup.get("Quarterback Hits")
    passes_defended = stat_lookup.get("Passes Defended")
    interceptions = stat_lookup.get("Interceptions")
    forced_fumbles = stat_lookup.get("Forced Fumbles")

    takeaways = None
    if interceptions is not None or forced_fumbles is not None:
        takeaways = (interceptions or 0.0) + (forced_fumbles or 0.0)

    return DefPlayer(
        name=athlete.fullName,
        team=team_abbr,
        position=athlete.position.abbreviation,
        position_class="DEF",
        height=int(athlete.height),
        weight=athlete.weight,
        age=athlete.age,
        games_played=games_played,
        total_tackles=total_tackles,
        solo_tackles=solo_tackles,
        sacks=sacks,
        qb_hits=qb_hits,
        passes_defended=passes_defended,
        interceptions=interceptions,
        forced_fumbles=forced_fumbles,
        takeaways=takeaways,
    )


def build_injured_player(
    athlete: ESPNAthleteResponse,
    stats: ESPNStatisticsResponse,
    team_abbr: str,
) -> Optional[InjuredPlayer]:
    if not athlete.injuries:
        return None

    injury_status = map_injury_status(athlete.injuries)

    if injury_status == "active":
        return None

    injury = athlete.injuries[0]
    injury_desc = injury.shortComment or ""
    if not injury_desc and hasattr(injury, "type") and hasattr(injury.type, "name"):
        injury_desc = injury.type.name
    if not injury_desc:
        injury_desc = injury.status

    position_class = compute_position_class(athlete.position.abbreviation)

    injured_player_data = {
        "name": athlete.fullName,
        "team": team_abbr,
        "position": athlete.position.abbreviation,
        "position_class": position_class,
        "height": int(athlete.height),
        "weight": athlete.weight,
        "age": athlete.age,
        "injury": injury_desc,
        "injury_status": injury_status,
        "general_stats": stats.get_category_stats("general") or [],
    }

    if position_class == "QB":
        injured_player_data["passing_stats"] = stats.get_category_stats("passing")
        injured_player_data["rushing_stats"] = stats.get_category_stats("rushing")
        injured_player_data["scoring_stats"] = stats.get_category_stats("scoring")
    elif position_class == "SKILL":
        injured_player_data["rushing_stats"] = stats.get_category_stats("rushing")
        injured_player_data["receiving_stats"] = stats.get_category_stats("receiving")
        injured_player_data["scoring_stats"] = stats.get_category_stats("scoring")
    elif position_class == "DEF":
        injured_player_data["defensive_stats"] = stats.get_category_stats("defensive")

    return InjuredPlayer(**injured_player_data)


async def build_qb_player_from_client_async(
    client: StatsClientProtocol,
    athlete_id: str,
    team_abbr: str,
) -> QbPlayer:
    athlete, stats = await asyncio.gather(
        client.get_athlete_info_async(athlete_id),
        client.get_athlete_stats_async(athlete_id),
    )
    return build_qb_player(athlete, stats, team_abbr)


async def build_skill_players_from_client_async(
    client: StatsClientProtocol,
    athlete_ids: List[str],
    team_abbr: str,
) -> List[SkillPlayer]:
    async def build_single_player(athlete_id: str) -> SkillPlayer:
        athlete, stats = await asyncio.gather(
            client.get_athlete_info_async(athlete_id),
            client.get_athlete_stats_async(athlete_id),
        )
        return build_skill_player(athlete, stats, team_abbr)

    results = await asyncio.gather(
        *[build_single_player(aid) for aid in athlete_ids], return_exceptions=True
    )

    skill_players = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Warning: Failed to build skill player {athlete_ids[i]}: {result}")
        else:
            skill_players.append(result)

    return skill_players


async def build_def_players_from_client_async(
    client: StatsClientProtocol,
    athlete_ids: List[str],
    team_abbr: str,
) -> List[DefPlayer]:
    async def build_single_player(athlete_id: str) -> DefPlayer:
        athlete, stats = await asyncio.gather(
            client.get_athlete_info_async(athlete_id),
            client.get_athlete_stats_async(athlete_id),
        )
        return build_def_player(athlete, stats, team_abbr)

    results = await asyncio.gather(
        *[build_single_player(aid) for aid in athlete_ids], return_exceptions=True
    )

    def_players = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(
                f"Warning: Failed to build defensive player {athlete_ids[i]}: {result}"
            )
        else:
            def_players.append(result)

    return def_players


async def build_injured_players_from_client_async(
    client: StatsClientProtocol,
    athlete_ids: List[str],
    team_abbr: str,
    max_players: int = 5,
) -> List[InjuredPlayer]:
    async def build_single_injured_player(
        athlete_id: str,
    ) -> Optional[InjuredPlayer]:
        try:
            athlete, stats = await asyncio.gather(
                client.get_athlete_info_async(athlete_id),
                client.get_athlete_stats_async(athlete_id),
            )
            return build_injured_player(athlete, stats, team_abbr)
        except Exception as e:
            print(f"Warning: Failed to build injured player {athlete_id}: {e}")
            return None

    results = await asyncio.gather(
        *[build_single_injured_player(aid) for aid in athlete_ids],
        return_exceptions=True,
    )

    injured_players = []
    for result in results:
        if isinstance(result, Exception):
            continue
        elif result is not None:
            injured_players.append(result)

    def priority_score(player: InjuredPlayer) -> tuple:
        position_priority = {"QB": 3, "SKILL": 2, "DEF": 1, "OL": 0}
        pos_score = position_priority.get(player.position_class, 0)

        injury_priority = {"out": 3, "doubtful": 2, "questionable": 1, "active": 0}
        inj_score = injury_priority.get(player.injury_status, 0)

        return (pos_score, inj_score)

    injured_players.sort(key=priority_score, reverse=True)
    return injured_players[:max_players]


async def build_team_from_client_async(
    client: StatsClientProtocol,
    team_id: str,
    max_wr: int = 3,
    max_injured: int = 5,
) -> Team:
    team_info = client.get_team_info(team_id)
    team_abbr = team_info.team.abbreviation

    depth_chart = client.get_team_depth_chart(team_id)

    qb_ids = depth_chart.get_starter_by_position("QB")
    if not qb_ids:
        raise ValueError(f"No QB found in depth chart for team {team_id}")
    qb_id = qb_ids[0]

    skill_ids = []
    skill_ids.extend(depth_chart.get_starter_by_position("RB"))
    skill_ids.extend(depth_chart.get_starter_by_position("WR", max_wr))
    skill_ids.extend(depth_chart.get_starter_by_position("TE"))

    def_ids = []
    def_ids.extend(depth_chart.get_starter_by_position("LDE"))
    def_ids.extend(depth_chart.get_starter_by_position("RDE"))
    def_ids.extend(depth_chart.get_starter_by_position("MLB"))
    def_ids.extend(depth_chart.get_starter_by_position("SLB"))
    def_ids.extend(depth_chart.get_starter_by_position("LCB"))

    all_player_ids = [qb_id] + skill_ids + def_ids

    qb_player, skill_players, def_players, injured_players = await asyncio.gather(
        build_qb_player_from_client_async(client, qb_id, team_abbr),
        build_skill_players_from_client_async(client, skill_ids, team_abbr),
        build_def_players_from_client_async(client, def_ids, team_abbr),
        build_injured_players_from_client_async(
            client, all_player_ids, team_abbr, max_injured
        ),
    )

    return Team(
        name=team_info.team.displayName,
        abbreviation=team_abbr,
        qb_player=qb_player,
        skill_stats=skill_players,
        def_players=def_players,
        injured_players=injured_players,
    )


def build_team_from_client(
    client: StatsClientProtocol,
    team_id: str,
    max_wr: int = 3,
    max_injured: int = 5,
) -> Team:
    return asyncio.run(
        build_team_from_client_async(client, team_id, max_wr, max_injured)
    )
