"""Multi-platform publishers — Instagram, Facebook (and later: TikTok, YouTube)."""

from .instagram import publish_to_instagram
from .facebook import publish_to_facebook

__all__ = ["publish_to_instagram", "publish_to_facebook"]
