"""
Social Graph Service
Handles following, followers, idea votes, and social feed
"""

from datetime import datetime
from typing import Any

from app.utils.logger import logger


class SocialGraphService:
    """Service for managing social interactions - follows, votes, and feeds"""

    def __init__(self, db):
        self.db = db
        self.follows_table = "user_follows"
        self.votes_table = "idea_votes"
        self.ideas_table = "ideas"

    async def follow_user(self, follower_id: str, followed_id: str) -> dict[str, Any]:
        """Follow a user"""
        if follower_id == followed_id:
            raise ValueError("Cannot follow yourself")

        follow_data = {
            "follower_id": follower_id,
            "followed_id": followed_id,
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            response = (
                self.db.table(self.follows_table)
                .upsert(follow_data, on_conflict="follower_id,followed_id")
                .execute()
            )

            if response.data:
                logger.info(f"[SocialGraph] User {follower_id} followed {followed_id}")
                return response.data
            raise Exception("Failed to follow user")
        except Exception as e:
            logger.error(f"[SocialGraph] Error following user: {e}")
            raise

    async def unfollow_user(self, follower_id: str, followed_id: str) -> bool:
        """Unfollow a user"""
        try:
            self.db.table(self.follows_table).delete().eq("follower_id", follower_id).eq(
                "followed_id", followed_id
            ).execute()

            logger.info(f"[SocialGraph] User {follower_id} unfollowed {followed_id}")
            return True
        except Exception as e:
            logger.error(f"[SocialGraph] Error unfollowing user: {e}")
            return False

    async def toggle_follow(self, follower_id: str, followed_id: str) -> dict[str, Any]:
        """Toggle follow status - follow if not following, unfollow if following"""
        is_following = await self.is_following(follower_id, followed_id)

        if is_following:
            await self.unfollow_user(follower_id, followed_id)
            return {"following": False, "followed_id": followed_id}
        else:
            await self.follow_user(follower_id, followed_id)
            return {"following": True, "followed_id": followed_id}

    async def is_following(self, follower_id: str, followed_id: str) -> bool:
        """Check if a user is following another user"""
        try:
            response = (
                self.db.table(self.follows_table)
                .select("follow_id")
                .eq("follower_id", follower_id)
                .eq("followed_id", followed_id)
                .execute()
            )
            return len(response.data) > 0 if response.data else False
        except Exception:
            return False

    async def get_followers(self, user_id: str) -> list[dict[str, Any]]:
        """Get all followers of a user"""
        try:
            response = (
                self.db.table(self.follows_table)
                .select("*")
                .eq("followed_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )

            follows = response.data or []

            follower_ids = sorted({f.get("follower_id") for f in follows if f.get("follower_id")})
            users_by_id: dict[str, dict[str, Any]] = {}
            if follower_ids:
                users_response = (
                    self.db.table("users")
                    .select("user_id, email, first_name, last_name, username, profile_picture_url")
                    .in_("user_id", follower_ids)
                    .execute()
                )
                users_by_id = {
                    str(user.get("user_id")): user
                    for user in (users_response.data or [])
                    if user.get("user_id")
                }

            for f in follows:
                f["follower"] = users_by_id.get(str(f.get("follower_id")), {})

            return follows
        except Exception as e:
            logger.error(f"[SocialGraph] Error getting followers: {e}")
            return []

    async def get_following(self, user_id: str) -> list[dict[str, Any]]:
        """Get all users that a user is following"""
        try:
            response = (
                self.db.table(self.follows_table)
                .select("*")
                .eq("follower_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )

            follows = response.data or []

            followed_ids = sorted({f.get("followed_id") for f in follows if f.get("followed_id")})
            users_by_id: dict[str, dict[str, Any]] = {}
            if followed_ids:
                users_response = (
                    self.db.table("users")
                    .select("user_id, email, first_name, last_name, username, profile_picture_url")
                    .in_("user_id", followed_ids)
                    .execute()
                )
                users_by_id = {
                    str(user.get("user_id")): user
                    for user in (users_response.data or [])
                    if user.get("user_id")
                }

            for f in follows:
                f["followed"] = users_by_id.get(str(f.get("followed_id")), {})

            return follows
        except Exception as e:
            logger.error(f"[SocialGraph] Error getting following: {e}")
            return []

    async def get_follower_count(self, user_id: str) -> int:
        """Get follower count for a user"""
        try:
            response = (
                self.db.table(self.follows_table)
                .select("follow_id")
                .eq("followed_id", user_id)
                .execute()
            )
            return len(response.data) if response.data else 0
        except Exception:
            return 0

    async def get_follower_counts(self, user_ids: list[str]) -> dict[str, int]:
        """Batch follower counts for many users in one query."""
        counts = {user_id: 0 for user_id in user_ids if user_id}
        if not counts:
            return counts

        try:
            response = (
                self.db.table(self.follows_table)
                .select("followed_id")
                .in_("followed_id", list(counts.keys()))
                .execute()
            )
            for row in response.data or []:
                followed_id = str(row.get("followed_id") or "")
                if followed_id in counts:
                    counts[followed_id] += 1
            return counts
        except Exception as exc:
            logger.warning(f"[SocialGraph] Error batch counting followers: {exc}")
            return counts

    async def get_following_set(self, follower_id: str, candidate_ids: list[str]) -> set[str]:
        """Return followed user ids for one viewer across many candidates."""
        if not follower_id or not candidate_ids:
            return set()

        filtered_ids = [
            candidate_id
            for candidate_id in candidate_ids
            if candidate_id and candidate_id != follower_id
        ]
        if not filtered_ids:
            return set()

        try:
            response = (
                self.db.table(self.follows_table)
                .select("followed_id")
                .eq("follower_id", follower_id)
                .in_("followed_id", filtered_ids)
                .execute()
            )
            return {str(row.get("followed_id") or "") for row in (response.data or [])}
        except Exception as exc:
            logger.warning(f"[SocialGraph] Error batch loading following set: {exc}")
            return set()

    async def get_following_count(self, user_id: str) -> int:
        """Get following count for a user"""
        try:
            response = (
                self.db.table(self.follows_table)
                .select("follow_id")
                .eq("follower_id", user_id)
                .execute()
            )
            return len(response.data) if response.data else 0
        except Exception:
            return 0

    async def upvote_idea(self, idea_id: str, user_id: str) -> dict[str, Any]:
        """Upvote an idea"""
        vote_data = {
            "idea_id": idea_id,
            "user_id": user_id,
            "vote_type": "upvote",
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            response = (
                self.db.table(self.votes_table)
                .upsert(vote_data, on_conflict="idea_id,user_id")
                .execute()
            )

            if response.data:
                logger.info(f"[SocialGraph] User {user_id} upvoted idea {idea_id}")
                return response.data
            raise Exception("Failed to upvote idea")
        except Exception as e:
            logger.error(f"[SocialGraph] Error upvoting idea: {e}")
            raise

    async def remove_vote(self, idea_id: str, user_id: str) -> bool:
        """Remove vote from an idea"""
        try:
            self.db.table(self.votes_table).delete().eq("idea_id", idea_id).eq(
                "user_id", user_id
            ).execute()

            logger.info(f"[SocialGraph] User {user_id} removed vote from idea {idea_id}")
            return True
        except Exception as e:
            logger.error(f"[SocialGraph] Error removing vote: {e}")
            return False

    async def toggle_upvote(self, idea_id: str, user_id: str) -> dict[str, Any]:
        """Toggle upvote - add if not voted, remove if already voted"""
        has_voted = await self.has_voted(idea_id, user_id)

        if has_voted:
            await self.remove_vote(idea_id, user_id)
            return {"voted": False, "idea_id": idea_id}
        else:
            await self.upvote_idea(idea_id, user_id)
            return {"voted": True, "idea_id": idea_id}

    async def has_voted(self, idea_id: str, user_id: str) -> bool:
        """Check if a user has voted on an idea"""
        try:
            response = (
                self.db.table(self.votes_table)
                .select("vote_id")
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .execute()
            )
            return len(response.data) > 0 if response.data else False
        except Exception:
            return False

    async def get_idea_vote_count(self, idea_id: str) -> int:
        """Get total vote count for an idea"""
        try:
            response = (
                self.db.table(self.votes_table)
                .select("vote_id")
                .eq("idea_id", idea_id)
                .eq("vote_type", "upvote")
                .execute()
            )
            return len(response.data) if response.data else 0
        except Exception:
            return 0

    async def get_following_feed(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Get ideas from users that the current user follows"""
        try:
            following = await self.get_following(user_id)
            following_ids = [f["followed_id"] for f in following]

            if not following_ids:
                return []

            response = (
                self.db.table(self.ideas_table)
                .select("*")
                .in_("user_id", following_ids)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            ideas = response.data or []

            for idea in ideas:
                creator_response = (
                    self.db.table("users")
                    .select("user_id, email, first_name, last_name, username, profile_picture_url")
                    .eq("user_id", idea["user_id"])
                    .single()
                    .execute()
                )
                idea["creator"] = creator_response.data if creator_response.data else {}
                idea["upvote_count"] = await self.get_idea_vote_count(idea["idea_id"])
                idea["has_upvoted"] = await self.has_voted(idea["idea_id"], user_id)

            return ideas
        except Exception as e:
            logger.error(f"[SocialGraph] Error getting following feed: {e}")
            return []


def create_social_graph_service(db) -> SocialGraphService:
    """Factory function to create SocialGraphService instance"""
    return SocialGraphService(db)
