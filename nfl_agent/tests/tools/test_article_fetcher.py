from nfl_agent.src.tools.article_fetcher import combine_team_info, TeamArticleQueryState
from nfl_agent.src.models.espn_search import TeamInfo


class TestCombineTeamInfo:
    """Test cases for combine_team_info function covering all field types."""

    def test_old_team_info_is_none(self):
        """When old_team_info is None, should return new_team_info."""
        new_info = TeamInfo(
            name="Eagles",
            coaching_summary="Great coach",
            injuries=["Player A"],
            strengths=["Offense"],
            problem_areas=["Defense"],
            relevant_players=["QB1"],
        )
        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": None,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"] == new_info
        assert result["articles_read_count"] == 1

    def test_list_field_both_none(self):
        """When both old and new list fields are None, keep None."""
        old_info = TeamInfo(name="Eagles", injuries=None)
        new_info = TeamInfo(name="Eagles", injuries=None)

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].injuries is None

    def test_list_field_old_none_new_has_values(self):
        """When old list is None and new has values, use new values."""
        old_info = TeamInfo(name="Eagles", injuries=None)
        new_info = TeamInfo(name="Eagles", injuries=["Player A", "Player B"])

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].injuries == ["Player A", "Player B"]

    def test_list_field_old_has_values_new_none(self):
        """When old list has values and new is None, keep old values."""
        old_info = TeamInfo(name="Eagles", injuries=["Player A", "Player B"])
        new_info = TeamInfo(name="Eagles", injuries=None)

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].injuries == ["Player A", "Player B"]

    def test_list_field_old_empty_new_has_values(self):
        """When old list is empty and new has values, use new values."""
        old_info = TeamInfo(name="Eagles", injuries=[])
        new_info = TeamInfo(name="Eagles", injuries=["Player A", "Player B"])

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].injuries == ["Player A", "Player B"]

    def test_list_field_old_has_values_new_empty(self):
        """When old list has values and new is empty, keep old values."""
        old_info = TeamInfo(name="Eagles", injuries=["Player A", "Player B"])
        new_info = TeamInfo(name="Eagles", injuries=[])

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].injuries == ["Player A", "Player B"]

    def test_list_field_both_have_values_merge_and_deduplicate(self):
        """When both lists have values, merge and deduplicate."""
        old_info = TeamInfo(name="Eagles", injuries=["Player A", "Player B"])
        new_info = TeamInfo(name="Eagles", injuries=["Player B", "Player C"])

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        # Should have all unique items, preserving order (old first, then new)
        assert set(result["team_info"].injuries) == {"Player A", "Player B", "Player C"}
        assert result["team_info"].injuries[0] == "Player A"
        assert result["team_info"].injuries[1] == "Player B"
        assert result["team_info"].injuries[2] == "Player C"

    def test_list_field_all_fields(self):
        """Test merging all list fields: injuries, strengths, problem_areas, relevant_players."""
        old_info = TeamInfo(
            name="Eagles",
            injuries=["Player A"],
            strengths=["Offense"],
            problem_areas=["Defense"],
            relevant_players=["QB1"],
        )
        new_info = TeamInfo(
            name="Eagles",
            injuries=["Player B"],
            strengths=["Special Teams"],
            problem_areas=["Penalties"],
            relevant_players=["RB1"],
        )

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert set(result["team_info"].injuries) == {"Player A", "Player B"}
        assert set(result["team_info"].strengths) == {"Offense", "Special Teams"}
        assert set(result["team_info"].problem_areas) == {"Defense", "Penalties"}
        assert set(result["team_info"].relevant_players) == {"QB1", "RB1"}

    def test_string_field_both_none(self):
        """When both old and new string fields are None, keep None."""
        old_info = TeamInfo(name="Eagles", coaching_summary=None)
        new_info = TeamInfo(name="Eagles", coaching_summary=None)

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].coaching_summary is None

    def test_string_field_old_none_new_has_value(self):
        """When old string is None and new has value, use new value."""
        old_info = TeamInfo(name="Eagles", coaching_summary=None)
        new_info = TeamInfo(name="Eagles", coaching_summary="Great coach")

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].coaching_summary == "Great coach"

    def test_string_field_old_has_value_new_none(self):
        """When old string has value and new is None, keep old value."""
        old_info = TeamInfo(name="Eagles", coaching_summary="Great coach")
        new_info = TeamInfo(name="Eagles", coaching_summary=None)

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].coaching_summary == "Great coach"

    def test_string_field_old_empty_new_has_value(self):
        """When old string is empty and new has value, use new value."""
        old_info = TeamInfo(name="Eagles", coaching_summary="")
        new_info = TeamInfo(name="Eagles", coaching_summary="Great coach")

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].coaching_summary == "Great coach"

    def test_string_field_old_has_value_new_empty(self):
        """When old string has value and new is empty, keep old value."""
        old_info = TeamInfo(name="Eagles", coaching_summary="Great coach")
        new_info = TeamInfo(name="Eagles", coaching_summary="")

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].coaching_summary == "Great coach"

    def test_string_field_both_have_different_values(self):
        """When both strings have different values, append new to old."""
        old_info = TeamInfo(name="Eagles", coaching_summary="Great offense")
        new_info = TeamInfo(name="Eagles", coaching_summary="Strong defense")

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        assert result["team_info"].coaching_summary == "Great offense\n\nStrong defense"

    def test_string_field_new_value_already_in_old(self):
        """When new string value is already contained in old, don't append."""
        old_info = TeamInfo(name="Eagles", coaching_summary="Great offense")
        new_info = TeamInfo(name="Eagles", coaching_summary="Great offense")

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        # Should not append duplicate
        assert result["team_info"].coaching_summary == "Great offense"

    def test_string_field_new_value_substring_of_old(self):
        """When new string is a substring of old, should append because we check exact equality."""
        old_info = TeamInfo(name="Eagles", coaching_summary="Great offense")
        new_info = TeamInfo(name="Eagles", coaching_summary="Great")

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 0,
        }

        result = combine_team_info(state)

        # Should append because "Great" != "Great offense" (exact equality check)
        assert result["team_info"].coaching_summary == "Great offense\n\nGreat"

    def test_mixed_fields_comprehensive(self):
        """Test combining all field types together."""
        old_info = TeamInfo(
            name="Eagles",
            coaching_summary="Old summary",
            injuries=["Player A"],
            strengths=["Offense"],
            problem_areas=None,
            relevant_players=["QB1"],
        )
        new_info = TeamInfo(
            name="Eagles",
            coaching_summary="New summary",
            injuries=["Player B"],
            strengths=None,
            problem_areas=["Defense"],
            relevant_players=["RB1"],
        )

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 5,
        }

        result = combine_team_info(state)

        assert result["team_info"].name == "Eagles"
        assert "Old summary" in result["team_info"].coaching_summary
        assert "New summary" in result["team_info"].coaching_summary
        assert set(result["team_info"].injuries) == {"Player A", "Player B"}
        assert result["team_info"].strengths == ["Offense"]  # New was None, keep old
        assert result["team_info"].problem_areas == ["Defense"]  # Old was None, use new
        assert set(result["team_info"].relevant_players) == {"QB1", "RB1"}
        assert result["articles_read_count"] == 6

    def test_articles_read_count_increments(self):
        """Test that articles_read_count is incremented correctly."""
        old_info = TeamInfo(name="Eagles")
        new_info = TeamInfo(name="Eagles")

        state: TeamArticleQueryState = {
            "team_name": "Eagles",
            "team_id": 21,
            "team_info": old_info,
            "articles": None,
            "selected_article": None,
            "article_content": None,
            "new_team_info": new_info,
            "articles_read_count": 10,
        }

        result = combine_team_info(state)

        assert result["articles_read_count"] == 11
