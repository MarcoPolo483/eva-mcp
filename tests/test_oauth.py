"""
OAuth 2.1 Integration Tests for EVA-MCP Server.
Tests dynamic client registration, token validation, and refresh flows.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from eva_mcp.auth.oauth import (
    OAuthProvider,
    OAuthClientInformation,
    OAuthServerMetadata,
    OAuthToken
)


@pytest.fixture
def mock_settings():
    """Mock settings with test Azure AD B2C configuration."""
    with patch("eva_mcp.auth.oauth.settings") as mock:
        mock.mcp_server_url = "http://localhost:8080"
        mock.azure_ad_b2c_issuer = "https://test.b2clogin.com/test/v2.0"
        mock.key_vault_url = "https://test-vault.vault.azure.net"
        yield mock


@pytest.fixture
def oauth_provider(mock_settings):
    """Create OAuth provider with mocked settings."""
    return OAuthProvider()


@pytest.fixture
def mock_metadata():
    """Mock OAuth server metadata."""
    return OAuthServerMetadata(
        issuer="https://test.b2clogin.com/test/v2.0",
        authorization_endpoint="https://test.b2clogin.com/test/oauth2/v2.0/authorize",
        token_endpoint="https://test.b2clogin.com/test/oauth2/v2.0/token",
        userinfo_endpoint="https://test.b2clogin.com/test/oauth2/v2.0/userinfo",
        registration_endpoint="https://test.b2clogin.com/test/oauth2/v2.0/register"
    )


@pytest.mark.asyncio
async def test_oauth_provider_initialization(oauth_provider, mock_settings):
    """Test OAuth provider initializes correctly."""
    assert oauth_provider.server_url == "http://localhost:8080"
    assert oauth_provider.issuer == "https://test.b2clogin.com/test/v2.0"
    assert oauth_provider.metadata is None
    assert len(oauth_provider.registered_clients) == 0


@pytest.mark.asyncio
async def test_oauth_provider_initialization_with_key_vault(oauth_provider, mock_settings):
    """Test OAuth provider initializes Key Vault client."""
    with patch("eva_mcp.auth.oauth.DefaultAzureCredential") as mock_cred, \
         patch("eva_mcp.auth.oauth.SecretClient") as mock_kv:
        
        await oauth_provider.initialize()
        
        # Should initialize Key Vault client
        mock_cred.assert_called_once()
        mock_kv.assert_called_once()


@pytest.mark.asyncio
async def test_oauth_provider_initialization_without_issuer():
    """Test OAuth provider handles missing issuer configuration."""
    with patch("eva_mcp.auth.oauth.settings") as mock:
        mock.azure_ad_b2c_issuer = ""
        mock.key_vault_url = ""
        
        provider = OAuthProvider()
        await provider.initialize()
        
        # Should not crash, just log warning
        assert provider.metadata is None


@pytest.mark.asyncio
async def test_discover_metadata(oauth_provider, mock_metadata):
    """Test OAuth metadata discovery from .well-known endpoint."""
    metadata_response = {
        "issuer": mock_metadata.issuer,
        "authorization_endpoint": mock_metadata.authorization_endpoint,
        "token_endpoint": mock_metadata.token_endpoint,
        "userinfo_endpoint": mock_metadata.userinfo_endpoint,
        "registration_endpoint": mock_metadata.registration_endpoint
    }
    
    with patch("aiohttp.ClientSession") as mock_session:
        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=metadata_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.get = mock_get
        
        # Discover metadata
        metadata = await oauth_provider._discover_metadata()
        
        assert metadata.issuer == mock_metadata.issuer
        assert metadata.token_endpoint == mock_metadata.token_endpoint
        assert metadata.userinfo_endpoint == mock_metadata.userinfo_endpoint
        assert oauth_provider.metadata == metadata


@pytest.mark.asyncio
async def test_discover_metadata_caching(oauth_provider, mock_metadata):
    """Test metadata discovery caches results for 24 hours."""
    oauth_provider.metadata = mock_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    # Should return cached metadata without HTTP call
    metadata = await oauth_provider._discover_metadata()
    
    assert metadata == mock_metadata


@pytest.mark.asyncio
async def test_discover_metadata_cache_expiry(oauth_provider):
    """Test metadata cache expires after 24 hours."""
    mock_old_metadata = OAuthServerMetadata(
        issuer="old",
        authorization_endpoint="old",
        token_endpoint="old"
    )
    
    oauth_provider.metadata = mock_old_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow() - timedelta(hours=25)
    
    new_metadata_response = {
        "issuer": "new",
        "authorization_endpoint": "new_auth",
        "token_endpoint": "new_token"
    }
    
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=new_metadata_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.get = mock_get
        
        # Should fetch new metadata
        metadata = await oauth_provider._discover_metadata()
        
        assert metadata.issuer == "new"


@pytest.mark.asyncio
async def test_discover_metadata_http_error(oauth_provider):
    """Test metadata discovery handles HTTP errors."""
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.get = mock_get
        
        with pytest.raises(Exception, match="Failed to fetch OAuth metadata"):
            await oauth_provider._discover_metadata()


@pytest.mark.asyncio
async def test_register_client(oauth_provider, mock_metadata):
    """Test dynamic client registration."""
    oauth_provider.metadata = mock_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    registration_response = {
        "client_id": "test-client-123",
        "client_secret": "secret-abc",
        "registration_client_uri": "https://test.b2clogin.com/test/client/123",
        "registration_access_token": "token-xyz"
    }
    
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(return_value=registration_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.post = mock_post
        
        # Mock Key Vault
        oauth_provider.kv_client = AsyncMock()
        
        # Register client
        client_info = await oauth_provider.register_client("test-client-123")
        
        assert client_info.client_id == "test-client-123"
        assert client_info.client_secret == "secret-abc"
        assert "test-client-123" in oauth_provider.registered_clients


@pytest.mark.asyncio
async def test_register_client_caching(oauth_provider):
    """Test client registration caching."""
    cached_client = OAuthClientInformation(
        client_id="cached-client",
        client_secret="cached-secret",
        registration_client_uri="https://cached",
        registration_access_token="cached-token"
    )
    
    oauth_provider.registered_clients["cached-client"] = cached_client
    
    # Should return cached client without HTTP call
    client_info = await oauth_provider.register_client("cached-client")
    
    assert client_info == cached_client


@pytest.mark.asyncio
async def test_register_client_no_registration_endpoint(oauth_provider):
    """Test client registration fails when endpoint not supported."""
    oauth_provider.metadata = OAuthServerMetadata(
        issuer="test",
        authorization_endpoint="test",
        token_endpoint="test",
        registration_endpoint=None  # Not supported
    )
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    with pytest.raises(Exception, match="Dynamic client registration not supported"):
        await oauth_provider.register_client("test-client")


@pytest.mark.asyncio
async def test_validate_token_success(oauth_provider, mock_metadata):
    """Test token validation with valid access token."""
    oauth_provider.metadata = mock_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    userinfo_response = {
        "sub": "user-123",
        "email": "user@example.com",
        "name": "Test User"
    }
    
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=userinfo_response)
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.get = mock_get
        
        # Validate token
        user_id = await oauth_provider.validate_token("valid-token")
        
        assert user_id == "user-123"


@pytest.mark.asyncio
async def test_validate_token_invalid(oauth_provider, mock_metadata):
    """Test token validation with invalid access token."""
    oauth_provider.metadata = mock_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 401  # Unauthorized
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.get = mock_get
        
        # Should return None for invalid token
        user_id = await oauth_provider.validate_token("invalid-token")
        
        assert user_id is None


@pytest.mark.asyncio
async def test_validate_token_caching(oauth_provider, mock_metadata):
    """Test token validation caching."""
    oauth_provider.metadata = mock_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    # Cache a token validation
    oauth_provider._token_cache["cached-token"] = ("user-456", datetime.utcnow())
    
    # Should return cached result without HTTP call
    user_id = await oauth_provider.validate_token("cached-token")
    
    assert user_id == "user-456"


@pytest.mark.asyncio
async def test_validate_token_cache_expiry(oauth_provider, mock_metadata):
    """Test token validation cache expires after TTL."""
    oauth_provider.metadata = mock_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    # Cache expired token (> 5 minutes old)
    expired_time = datetime.utcnow() - timedelta(minutes=6)
    oauth_provider._token_cache["expired-token"] = ("old-user", expired_time)
    
    userinfo_response = {"sub": "new-user"}
    
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=userinfo_response)
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.get = mock_get
        
        # Should fetch new validation
        user_id = await oauth_provider.validate_token("expired-token")
        
        assert user_id == "new-user"


@pytest.mark.asyncio
async def test_refresh_token_success(oauth_provider, mock_metadata):
    """Test token refresh with valid refresh token."""
    oauth_provider.metadata = mock_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    # Register client
    client_info = OAuthClientInformation(
        client_id="test-client",
        client_secret="test-secret",
        registration_client_uri="https://test",
        registration_access_token="test-token"
    )
    oauth_provider.registered_clients["test-client"] = client_info
    
    token_response = {
        "access_token": "new-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "new-refresh-token"
    }
    
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=token_response)
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.post = mock_post
        
        # Refresh token
        start_time = datetime.utcnow()
        new_token = await oauth_provider.refresh_token("test-client", "old-refresh-token")
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        assert new_token.access_token == "new-access-token"
        assert new_token.refresh_token == "new-refresh-token"
        assert duration < 1.0  # Should complete in < 1 second


@pytest.mark.asyncio
async def test_refresh_token_performance(oauth_provider, mock_metadata):
    """Test token refresh completes in < 1 second."""
    oauth_provider.metadata = mock_metadata
    oauth_provider.metadata_loaded_at = datetime.utcnow()
    
    client_info = OAuthClientInformation(
        client_id="test-client",
        client_secret="test-secret",
        registration_client_uri="https://test",
        registration_access_token="test-token"
    )
    oauth_provider.registered_clients["test-client"] = client_info
    
    token_response = {
        "access_token": "new-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "new-refresh"
    }
    
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=token_response)
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.post = mock_post
        
        # Measure refresh time
        start = datetime.utcnow()
        await oauth_provider.refresh_token("test-client", "refresh-token")
        duration = (datetime.utcnow() - start).total_seconds()
        
        # Quality gate: < 1 second
        assert duration < 1.0


@pytest.mark.asyncio
async def test_refresh_token_client_not_registered(oauth_provider):
    """Test token refresh fails for unregistered client."""
    with pytest.raises(Exception, match="Client not registered"):
        await oauth_provider.refresh_token("unknown-client", "refresh-token")


@pytest.mark.asyncio
async def test_oauth_token_expiry_check():
    """Test OAuth token expiry detection."""
    # Create expired token (issued 2 hours ago, expires in 1 hour)
    old_token = OAuthToken(
        access_token="old",
        token_type="Bearer",
        expires_in=3600
    )
    old_token.issued_at = datetime.utcnow() - timedelta(hours=2)
    
    assert old_token.is_expired
    
    # Create fresh token
    new_token = OAuthToken(
        access_token="new",
        token_type="Bearer",
        expires_in=3600
    )
    
    assert not new_token.is_expired


@pytest.mark.asyncio
async def test_oauth_provider_cleanup(oauth_provider):
    """Test OAuth provider cleanup."""
    # Mock Key Vault client
    oauth_provider.kv_client = AsyncMock()
    oauth_provider.kv_credential = AsyncMock()
    
    await oauth_provider.cleanup()
    
    oauth_provider.kv_client.close.assert_called_once()
    oauth_provider.kv_credential.close.assert_called_once()
