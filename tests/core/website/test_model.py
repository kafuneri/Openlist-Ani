"""Tests for AnimeResourceInfo data model."""

from openlist_ani.core.website.model import (
    AnimeResourceInfo,
    LanguageType,
    VideoQuality,
)


class TestAnimeResourceInfo:
    """Verify the data model behaves correctly with edge-case inputs."""

    def test_default_values(self):
        info = AnimeResourceInfo(title="test", download_url="magnet:?xt=urn:btih:abc")
        assert info.anime_name is None
        assert info.season is None
        assert info.episode is None
        assert info.fansub is None
        assert info.quality == VideoQuality.kUnknown
        assert info.languages == []
        assert info.version == 1

    def test_repr_with_none_fields(self):
        """repr() must not crash even when optional fields are None."""
        info = AnimeResourceInfo(title="t", download_url="d")
        result = repr(info)
        assert "title=" in result
        assert "anime_name=None" in result

    def test_languages_list_independence(self):
        """Each instance must have its own languages list (no shared mutable default)."""
        a = AnimeResourceInfo(title="a", download_url="u1")
        b = AnimeResourceInfo(title="b", download_url="u2")
        a.languages.append(LanguageType.kChs)
        assert b.languages == [], "Mutable default list leaked between instances"

    def test_empty_title(self):
        """Model should accept empty strings without crashing."""
        info = AnimeResourceInfo(title="", download_url="")
        assert info.title == ""
        assert info.download_url == ""
