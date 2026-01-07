from pydantic import BaseModel


class ProbabilityResponse(BaseModel):
    home_team_probability: float
    away_team_probability: float
    home_team_summary: str
    away_team_summary: str
