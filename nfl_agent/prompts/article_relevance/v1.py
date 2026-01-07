from pydantic import BaseModel

SYSTEM_PROMPT = """
    You are a senior NFL sports analyst. You are searching information about a team.
    Given the following articles, pick the article you think is most relevant to find more information about the team.
    Return the article id of the most relevant article.
    """


USER_PROMPT = """
Team name: {team_name}
The articles are: \n{articles}
"""


class ArticleRelevanceResponse(BaseModel):
    article_id: int
