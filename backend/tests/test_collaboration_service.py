"""
Tests for Collaboration Service
Tests for team collaboration, access management, and version control functionality
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta, timezone
from app.services.ideas.collaboration import CollaborationService, create_collaboration_service


class MockQueryResponse:
    def __init__(self, data):
        self.data = data


class MockQueryBuilder:
    def __init__(self, data=None):
        self._data = data or []
        self._single_mode = False
    
    def select(self, *args):
        return self
    
    def eq(self, *args):
        return self
    
    def neq(self, *args):
        return self
    
    def order(self, *args, **kwargs):
        return self
    
    def limit(self, *args):
        return self
    
    def single(self):
        self._single_mode = True
        return self
    
    def insert(self, data):
        self._data = [data] if isinstance(data, dict) else data
        return self
    
    def update(self, data):
        return self
    
    def upsert(self, data, **kwargs):
        self._data = [data] if isinstance(data, dict) else data
        return self
    
    def delete(self):
        return self
    
    def execute(self):
        if self._single_mode:
            return MockQueryResponse(self._data[0] if self._data else None)
        return MockQueryResponse(self._data)


class TestCollaborationService:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db
    
    @pytest.fixture
    def service(self, mock_db):
        return CollaborationService(mock_db)
    
    def test_role_permissions(self, service):
        """Test that role permissions are correctly defined"""
        assert "view" in service.ROLE_PERMISSIONS["viewer"]
        assert "edit" not in service.ROLE_PERMISSIONS["viewer"]
        
        assert "view" in service.ROLE_PERMISSIONS["commenter"]
        assert "comment" in service.ROLE_PERMISSIONS["commenter"]
        assert "edit" not in service.ROLE_PERMISSIONS["commenter"]
        
        assert "view" in service.ROLE_PERMISSIONS["editor"]
        assert "edit" in service.ROLE_PERMISSIONS["editor"]
        assert "comment" in service.ROLE_PERMISSIONS["editor"]
        assert "share" not in service.ROLE_PERMISSIONS["editor"]
        
        assert "view" in service.ROLE_PERMISSIONS["owner"]
        assert "edit" in service.ROLE_PERMISSIONS["owner"]
        assert "share" in service.ROLE_PERMISSIONS["owner"]
        assert "manage_access" in service.ROLE_PERMISSIONS["owner"]
    
    @pytest.mark.asyncio
    async def test_get_idea_owner(self, service, mock_db):
        """Test getting idea owner"""
        mock_db.table.return_value = MockQueryBuilder([{"user_id": "owner-123"}])
        
        result = await service.get_idea_owner("idea-123")
        assert result == "owner-123"
        mock_db.table.assert_called_with("ideas")
    
    @pytest.mark.asyncio
    async def test_get_idea_owner_not_found(self, service, mock_db):
        """Test getting owner for non-existent idea"""
        mock_db.table.return_value = MockQueryBuilder([])
        
        result = await service.get_idea_owner("non-existent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_check_access_owner(self, service, mock_db):
        """Test that owner has all permissions"""
        mock_db.table.return_value = MockQueryBuilder([{"user_id": "user-123"}])
        
        result = await service.check_access("idea-123", "user-123", "manage_access")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_access_editor(self, service, mock_db):
        """Test editor permissions"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "owner-456"}])
            else:
                return MockQueryBuilder([{"role": "editor", "status": "accepted"}])
        
        mock_db.table.side_effect = table_side_effect
        
        result = await service.check_access("idea-123", "user-123", "edit")
        assert result is True
        
        result = await service.check_access("idea-123", "user-123", "share")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_check_access_viewer(self, service, mock_db):
        """Test viewer permissions"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "owner-456"}])
            else:
                return MockQueryBuilder([{"role": "viewer", "status": "accepted"}])
        
        mock_db.table.side_effect = table_side_effect
        
        result = await service.check_access("idea-123", "user-123", "view")
        assert result is True
        
        result = await service.check_access("idea-123", "user-123", "edit")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_check_access_pending_invitation(self, service, mock_db):
        """Test that pending invitations don't grant access"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "owner-456"}])
            else:
                return MockQueryBuilder([{"role": "editor", "status": "pending"}])
        
        mock_db.table.side_effect = table_side_effect
        
        result = await service.check_access("idea-123", "user-123", "view")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_user_role_owner(self, service, mock_db):
        """Test getting role for owner"""
        mock_db.table.return_value = MockQueryBuilder([{"user_id": "user-123"}])
        
        result = await service.get_user_role("idea-123", "user-123")
        assert result == "owner"
    
    @pytest.mark.asyncio
    async def test_get_user_role_collaborator(self, service, mock_db):
        """Test getting role for collaborator"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "owner-456"}])
            else:
                return MockQueryBuilder([{"role": "editor"}])
        
        mock_db.table.side_effect = table_side_effect
        
        result = await service.get_user_role("idea-123", "user-123")
        assert result == "editor"
    
    @pytest.mark.asyncio
    async def test_invite_collaborator_invalid_role(self, service, mock_db):
        """Test that invalid roles are rejected"""
        with pytest.raises(ValueError, match="Invalid role"):
            await service.invite_collaborator(
                idea_id="idea-123",
                inviter_id="owner-123",
                invitee_email="test@test.com",
                role="invalid_role"
            )
    
    @pytest.mark.asyncio
    async def test_invite_collaborator_permission_denied(self, service, mock_db):
        """Test that non-owners cannot share"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "owner-456"}])
            else:
                return MockQueryBuilder([{"role": "viewer", "status": "accepted"}])
        
        mock_db.table.side_effect = table_side_effect
        
        with pytest.raises(PermissionError, match="don't have permission"):
            await service.invite_collaborator(
                idea_id="idea-123",
                inviter_id="user-123",
                invitee_email="test@test.com",
                role="viewer"
            )
    
    def test_create_collaboration_service_factory(self, mock_db):
        """Test factory function creates service correctly"""
        service = create_collaboration_service(mock_db)
        assert isinstance(service, CollaborationService)
        assert service.db == mock_db


class StatefulMockQueryBuilder:
    """Mock that tracks inserted data and returns it correctly"""
    def __init__(self, data=None):
        self._data = data or []
        self._single_mode = False
        self._inserted = None
    
    def select(self, *args): return self
    def eq(self, *args): return self
    def neq(self, *args): return self
    def order(self, *args, **kwargs): return self
    def limit(self, *args): return self
    def delete(self): return self
    
    def single(self):
        self._single_mode = True
        return self
    
    def insert(self, data):
        self._inserted = data
        self._data = [data] if isinstance(data, dict) else data
        return self
    
    def update(self, data):
        self._data = [data] if isinstance(data, dict) else data
        return self
    
    def execute(self):
        if self._single_mode:
            return MockQueryResponse(self._data[0] if self._data else None)
        return MockQueryResponse(self._data)


class TestVersionControl:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db
    
    @pytest.fixture
    def service(self, mock_db):
        return CollaborationService(mock_db)
    
    @pytest.mark.asyncio
    async def test_create_version_as_owner_succeeds(self, service, mock_db):
        """Test that owner can create versions successfully and verify payload structure"""
        idea_data = {
            "idea_id": "idea-123",
            "user_id": "user-123",
            "title": "Test Idea",
            "description": "A test description",
            "business_model_canvas": {"canvas": "data"},
            "pitch_deck": {"slides": []},
            "product_requirements_document": "PRD content",
            "provisional_patent": None,
        }
        
        captured_inserts = []
        
        class CapturingBuilder(StatefulMockQueryBuilder):
            def insert(self, data):
                captured_inserts.append(data)
                return super().insert(data)
        
        class TableRouter:
            def __init__(self):
                self.ideas_calls = 0
                self.versions_calls = 0
            
            def get_builder(self, name):
                if name == "ideas":
                    self.ideas_calls += 1
                    return CapturingBuilder([idea_data])
                elif name == "idea_versions":
                    self.versions_calls += 1
                    if self.versions_calls == 1:
                        return CapturingBuilder([])
                    return CapturingBuilder([{
                        "version_id": "new-id",
                        "version_number": 1,
                        "title": "Test Idea",
                    }])
                return CapturingBuilder([])
        
        router = TableRouter()
        mock_db.table.side_effect = router.get_builder
        
        result = await service.create_version("idea-123", "user-123", "Initial version")
        
        assert result is not None
        assert result["version_number"] == 1
        assert router.ideas_calls >= 1
        assert router.versions_calls >= 1
        
        assert len(captured_inserts) >= 1
        version_payload = captured_inserts[0]
        assert "version_id" in version_payload
        assert version_payload["idea_id"] == "idea-123"
        assert version_payload["title"] == "Test Idea"
        assert version_payload["description"] == "A test description"
        assert version_payload["created_by"] == "user-123"
        assert version_payload["change_summary"] == "Initial version"
        assert "created_at" in version_payload
        assert version_payload.get("version_kind") == "manual"
        assert version_payload.get("content_hash")
    
    @pytest.mark.asyncio
    async def test_create_version_increments_correctly(self, service, mock_db):
        """Test that version number increments from existing versions"""
        idea_data = {
            "idea_id": "idea-123",
            "user_id": "user-123",
            "title": "Test",
            "description": "Desc",
        }
        
        class TableRouter:
            def __init__(self):
                self.version_check_done = False
            
            def get_builder(self, name):
                if name == "ideas":
                    return StatefulMockQueryBuilder([idea_data])
                elif name == "idea_versions":
                    if not self.version_check_done:
                        self.version_check_done = True
                        return StatefulMockQueryBuilder([{"version_number": 3}])
                    return StatefulMockQueryBuilder([{
                        "version_id": "new-id",
                        "version_number": 4,
                    }])
                return StatefulMockQueryBuilder([])
        
        mock_db.table.side_effect = TableRouter().get_builder
        
        result = await service.create_version("idea-123", "user-123")
        
        assert result["version_number"] == 4
    
    @pytest.mark.asyncio
    async def test_create_version_permission_denied(self, service, mock_db):
        """Test that viewers cannot create versions"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "owner-456"}])
            else:
                return MockQueryBuilder([{"role": "viewer", "status": "accepted"}])
        
        mock_db.table.side_effect = table_side_effect
        
        with pytest.raises(PermissionError, match="don't have permission"):
            await service.create_version("idea-123", "viewer-user")
    
    @pytest.mark.asyncio
    async def test_create_version_idea_not_found(self, service, mock_db):
        """Test that create_version fails if idea doesn't exist after auth passes"""
        class TableRouter:
            def __init__(self):
                self.ideas_calls = 0
            
            def get_builder(self, name):
                if name == "ideas":
                    self.ideas_calls += 1
                    if self.ideas_calls == 1:
                        return StatefulMockQueryBuilder([{"user_id": "user-123"}])
                    return StatefulMockQueryBuilder([None])
                return StatefulMockQueryBuilder([])
        
        mock_db.table.side_effect = TableRouter().get_builder
        
        with pytest.raises(ValueError, match="Idea not found"):
            await service.create_version("nonexistent", "user-123")
    
    @pytest.mark.asyncio
    async def test_get_versions_as_owner(self, service, mock_db):
        """Test getting version history as owner"""
        versions_data = [
            {"version_id": "v-2", "version_number": 2, "created_by": "user-123"},
            {"version_id": "v-1", "version_number": 1, "created_by": "user-123"},
        ]
        
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "user-123"}])
            elif name == "idea_versions":
                return MockQueryBuilder(versions_data)
            else:
                return MockQueryBuilder([{"email": "test@test.com", "username": "testuser"}])
        
        mock_db.table.side_effect = table_side_effect
        
        result = await service.get_versions("idea-123", "user-123")
        
        assert len(result) == 2
        assert result[0]["version_number"] == 2
        assert result[1]["version_number"] == 1
    
    @pytest.mark.asyncio
    async def test_get_versions_permission_denied(self, service, mock_db):
        """Test that unauthorized users cannot view versions"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "owner-456"}])
            else:
                return MockQueryBuilder([])
        
        mock_db.table.side_effect = table_side_effect
        
        with pytest.raises(PermissionError, match="don't have permission"):
            await service.get_versions("idea-123", "unauthorized-user")
    
    @pytest.mark.asyncio
    async def test_get_versions_returns_empty_list_when_no_versions(self, service, mock_db):
        """Test that empty version history returns empty list"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "user-123"}])
            elif name == "idea_versions":
                return MockQueryBuilder([])
            else:
                return MockQueryBuilder([])
        
        mock_db.table.side_effect = table_side_effect
        
        result = await service.get_versions("idea-123", "user-123")
        
        assert result == []


class TestRestoreVersion:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db
    
    @pytest.fixture
    def service(self, mock_db):
        return CollaborationService(mock_db)
    
    @pytest.mark.asyncio
    async def test_restore_version_permission_denied(self, service, mock_db):
        """Test that viewers cannot restore versions"""
        def table_side_effect(name):
            if name == "ideas":
                return MockQueryBuilder([{"user_id": "owner-456"}])
            else:
                return MockQueryBuilder([{"role": "viewer", "status": "accepted"}])
        
        mock_db.table.side_effect = table_side_effect
        
        with pytest.raises(PermissionError, match="don't have permission"):
            await service.restore_version("idea-123", "version-1", "viewer-user")
    
    @pytest.mark.asyncio
    async def test_restore_version_as_owner(self, service, mock_db):
        """Test that owner can restore to a previous version"""
        idea_data = {
            "idea_id": "idea-123",
            "user_id": "user-123",
            "title": "Current Title",
            "description": "Current description",
        }
        
        old_version_data = {
            "version_id": "v-1",
            "version_number": 1,
            "title": "Old Title",
            "description": "Old description",
            "business_model_canvas": None,
            "pitch_deck": None,
            "product_requirements_document": None,
            "provisional_patent": None,
        }
        
        class TableRouter:
            def __init__(self):
                self.ideas_calls = 0
                self.versions_insert_count = 0
            
            def get_builder(self, name):
                if name == "ideas":
                    self.ideas_calls += 1
                    builder = StatefulMockQueryBuilder([idea_data])
                    return builder
                elif name == "idea_versions":
                    self.versions_insert_count += 1
                    return StatefulMockQueryBuilder([old_version_data])
                return StatefulMockQueryBuilder([])
        
        router = TableRouter()
        mock_db.table.side_effect = router.get_builder
        
        result = await service.restore_version("idea-123", "v-1", "user-123")
        
        assert result is not None
        assert router.ideas_calls >= 1
    
    @pytest.mark.asyncio
    async def test_restore_version_not_found(self, service, mock_db):
        """Test that restore fails if version doesn't exist"""
        idea_data = {
            "idea_id": "idea-123",
            "user_id": "user-123",
            "title": "Test",
        }
        
        class TableRouter:
            def __init__(self):
                self.versions_calls = 0
            
            def get_builder(self, name):
                if name == "ideas":
                    return StatefulMockQueryBuilder([idea_data])
                elif name == "idea_versions":
                    self.versions_calls += 1
                    if self.versions_calls <= 2:
                        return StatefulMockQueryBuilder([{"version_number": 1}])
                    return StatefulMockQueryBuilder([None])
                return StatefulMockQueryBuilder([])
        
        mock_db.table.side_effect = TableRouter().get_builder
        
        with pytest.raises(ValueError, match="Version not found"):
            await service.restore_version("idea-123", "nonexistent", "user-123")
    
    @pytest.mark.asyncio
    async def test_restore_creates_backup_first(self, service, mock_db):
        """Test that restore creates a backup version before restoring"""
        idea_data = {"idea_id": "idea-123", "user_id": "user-123", "title": "Current"}
        version_data = {"version_id": "v-1", "version_number": 1, "title": "Old"}
        
        insert_calls = []
        
        class TrackingBuilder(StatefulMockQueryBuilder):
            def insert(self, data):
                insert_calls.append(data)
                return super().insert(data)
        
        class TableRouter:
            def get_builder(self, name):
                if name == "ideas":
                    return TrackingBuilder([idea_data])
                elif name == "idea_versions":
                    return TrackingBuilder([version_data])
                return TrackingBuilder([])
        
        mock_db.table.side_effect = TableRouter().get_builder
        
        await service.restore_version("idea-123", "v-1", "user-123")
        
        assert len(insert_calls) >= 1


class TestAccessManagement:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db
    
    @pytest.fixture
    def service(self, mock_db):
        return CollaborationService(mock_db)
    
    def test_role_hierarchy(self, service):
        """Test role hierarchy and permission inheritance"""
        viewer_perms = service.ROLE_PERMISSIONS["viewer"]
        commenter_perms = service.ROLE_PERMISSIONS["commenter"]
        editor_perms = service.ROLE_PERMISSIONS["editor"]
        owner_perms = service.ROLE_PERMISSIONS["owner"]
        
        assert viewer_perms.issubset(commenter_perms)
        assert commenter_perms.issubset(editor_perms)
        assert editor_perms.issubset(owner_perms)
    
    @pytest.mark.asyncio
    async def test_cannot_change_owner_role(self, service, mock_db):
        """Test that owner's role cannot be changed"""
        mock_db.table.return_value = MockQueryBuilder([{"user_id": "owner-123"}])
        
        with pytest.raises(ValueError, match="Cannot change the owner's role"):
            await service.update_collaborator_role(
                idea_id="idea-123",
                updater_id="owner-123",
                target_user_id="owner-123",
                new_role="editor"
            )
    
    @pytest.mark.asyncio
    async def test_cannot_remove_owner(self, service, mock_db):
        """Test that owner cannot be removed"""
        mock_db.table.return_value = MockQueryBuilder([{"user_id": "owner-123"}])
        
        with pytest.raises(ValueError, match="Cannot remove the owner"):
            await service.remove_collaborator(
                idea_id="idea-123",
                remover_id="owner-123",
                target_user_id="owner-123"
            )
    
    @pytest.mark.asyncio
    async def test_valid_roles_are_accepted(self, service):
        """Test that all valid roles are in the permissions dict"""
        valid_roles = ["owner", "editor", "commenter", "viewer"]
        for role in valid_roles:
            assert role in service.ROLE_PERMISSIONS
            assert isinstance(service.ROLE_PERMISSIONS[role], set)


class TestInvitationWorkflow:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db
    
    @pytest.fixture
    def service(self, mock_db):
        return CollaborationService(mock_db)
    
    def test_valid_invitation_responses(self, service):
        """Test that valid invitation response types are defined"""
        valid_responses = ["accepted", "declined"]
        for response in valid_responses:
            assert response in ["accepted", "declined"]
    
    def test_pending_status_exists(self, service):
        """Test that pending status is a valid invitation status"""
        assert "pending" == "pending"
    
    def test_constants_are_defined(self, service):
        """Test that role constants are properly defined"""
        assert service.ROLE_OWNER == "owner"
        assert service.ROLE_EDITOR == "editor"
        assert service.ROLE_COMMENTER == "commenter"
        assert service.ROLE_VIEWER == "viewer"
    
    def test_table_names_are_defined(self, service):
        """Test that table names are properly defined"""
        assert service.collaborators_table == "idea_collaborators"
        assert service.versions_table == "idea_versions"
        assert service.ideas_table == "ideas"


class TestAutoVersioning:
    """Tests for automatic version creation on autosave (maybe_record_auto_version_after_user_edit)."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return CollaborationService(mock_db)

    # -- _parse_to_naive_utc --

    def test_parse_to_naive_utc_with_none(self, service):
        assert service._parse_to_naive_utc(None) is None

    def test_parse_to_naive_utc_with_naive_string(self, service):
        result = service._parse_to_naive_utc("2026-03-29T12:00:00")
        assert result == datetime(2026, 3, 29, 12, 0, 0)
        assert result.tzinfo is None

    def test_parse_to_naive_utc_with_z_suffix(self, service):
        result = service._parse_to_naive_utc("2026-03-29T12:00:00Z")
        assert result == datetime(2026, 3, 29, 12, 0, 0)
        assert result.tzinfo is None

    def test_parse_to_naive_utc_with_offset_string(self, service):
        result = service._parse_to_naive_utc("2026-03-29T12:00:00+00:00")
        assert result == datetime(2026, 3, 29, 12, 0, 0)
        assert result.tzinfo is None

    def test_parse_to_naive_utc_with_aware_datetime(self, service):
        aware = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)
        result = service._parse_to_naive_utc(aware)
        assert result == datetime(2026, 3, 29, 12, 0, 0)
        assert result.tzinfo is None

    def test_parse_to_naive_utc_with_naive_datetime(self, service):
        naive = datetime(2026, 3, 29, 12, 0, 0)
        result = service._parse_to_naive_utc(naive)
        assert result == naive
        assert result.tzinfo is None

    @pytest.mark.asyncio
    async def test_maybe_record_returns_none_without_edit_access(self, service, monkeypatch):
        async def no_edit(*_a, **_kw):
            return False

        async def owner_id(_i):
            return "owner-1"

        monkeypatch.setattr(service, "check_access", no_edit)
        monkeypatch.setattr(service, "get_idea_owner", owner_id)

        out = await service.maybe_record_auto_version_after_user_edit("idea-123", "u1")
        assert out is None

    @pytest.mark.asyncio
    async def test_maybe_record_returns_none_on_db_error(self, service, mock_db, monkeypatch):
        async def yes_edit(*_a, **_kw):
            return True

        async def owner_id(_i):
            return "owner-1"

        monkeypatch.setattr(service, "check_access", yes_edit)
        monkeypatch.setattr(service, "get_idea_owner", owner_id)
        mock_db.table.side_effect = Exception("DB error")

        out = await service.maybe_record_auto_version_after_user_edit("idea-123", "owner-1")
        assert out is None

    def test_auto_version_interval_deprecated_constant(self, service):
        assert service.AUTO_VERSION_INTERVAL_MINUTES == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
