from pydantic import BaseModel


class Probability(BaseModel):
    home_team_probability: float
    away_team_probability: float
