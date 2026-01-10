---
layout: section
---

# Design

---

# Design

## Define the Problem:

For the upcoming week in the NFL season, give me the probability of each team winning their matchup.

<img src="../components/overview.png" alt="overview" width="400" class="mx-auto" />


---
layout: image-right

# the image source
image: ../components/tools.png

# a custom class name to the content
class: my-cool-content-on-the-right
---

# Design

## Define the tools

- `team_stats`: list of stats for a team
- `player_stats`: list of stats for a player
- `news_article_analyzer`: list of insights from recent news articles about a team
- `play-by-play_analyzer` (out of scope)

- Lessons Learned: sub-agents are for managing context not role-playing


---
class: text-sm
---

# Design 
## stats lookup tool   

- no LLM API calls in this tool
- use ESPN public API
- Used Cursor a lot to understsand schemas and map to fields needed

```python

class Team(BaseModel):
    name: str
    abbreviation: str
    # pick the most important players for each team
    qb_player: QbPlayer
    skill_stats: List[SkillPlayer]
    def_players: List[DefPlayer]
    injured_players: List[InjuredPlayer]

class Player(BaseModel):
    name: str
    team: str
    position: str
    position_class: Literal["QB", "SKILL", "OL", "DEF"]
    height: int
    weight: float
    age: int
    ...
```


---
layout: two-cols-header
zoom: 0.70

---


# Design 

## news article analyzer tool   

::left::

Define the problem:

```markdown
1. Use the ESPN search to find insightful articles about the upcoming match. 
2. Select the most use article to read next.
3. Fetch and read the article content.
4. Summarize the article content.
5. Combine the article content with the team info.
```

- Lessons learned: this is a _workflow_ not a subagent
- for _workflows_ we use langgraph (DAG orchestration system)


::right::
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
        __start__([<p>__start__</p>]):::first
        get_articles(get_articles)
        select_article(select_article)
        fetch_content(fetch_content)
        summarize_content(summarize_content)
        combine_team_info(combine_team_info)
        __end__([<p>__end__</p>]):::last
        __start__ --> get_articles;
        combine_team_info -. &nbsp;end&nbsp; .-> __end__;
        combine_team_info -. &nbsp;continue&nbsp; .-> get_articles;
        fetch_content --> summarize_content;
        get_articles --> select_article;
        select_article -. &nbsp;skip&nbsp; .-> __end__;
        select_article -. &nbsp;fetch&nbsp; .-> fetch_content;
        summarize_content --> combine_team_info;
        classDef default fill:#f2f0ff,line-height:1.2
        classDef first fill-opacity:0
        classDef last fill:#bfb6fc
```


