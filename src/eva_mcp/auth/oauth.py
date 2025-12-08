"""
OAuth 2.1 Provider for EVA-MCP Server.
Integrates with Azure AD B2C for authentication and authorization.

Features:
- Dynamic client registration
- Token validation (access tokens)
- Token refresh (< 1 second target)
- Secret storage in Azure Key Vault
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

import aiohttp
from azure.identity.aio import DefaultAzureCredential
from azure.keyvault.secrets.aio import SecretClient

from eva_mcp.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# OAuth 2.1 Data Models
# ============================================================================

class OAuthClientInformation:
    """OAuth client information from dynamic registration."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        registration_client_uri: str,
        registration_access_token: str,
        **kwargs
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.registration_client_uri = registration_client_uri
        self.registration_access_token = registration_access_token
        # Store additional fields
        self.metadata = kwargs


class OAuthServerMetadata:
    """OAuth server metadata from .well-known/oauth-authorization-server."""
    
    def __init__(
        self,
        issuer: str,
        authorization_endpoint: str,
        token_endpoint: str,
        userinfo_endpoint: Optional[str] = None,
        registration_endpoint: Optional[str] = None,
        **kwargs
    ):
        self.issuer = issuer
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.userinfo_endpoint = userinfo_endpoint
        self.registration_endpoint = registration_endpoint
        self.metadata = kwargs


class OAuthToken:
    """OAuth access/refresh token pair."""
    
    def __init__(
        self,
        access_token: str,
        token_type: str,
        expires_in: int,
        refresh_token: Optional[str] = None,
        scope: Optional[str] = None,
        **kwargs
    ):
        self.access_token = access_token
        self.token_type = token_type
        self.expires_in = expires_in
        self.refresh_token = refresh_token
        self.scope = scope
        self.issued_at = datetime.utcnow()
        self.metadata = kwargs
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60s buffer)."""
        expiry = self.issued_at + timedelta(seconds=self.expires_in - 60)
        return datetime.utcnow() >= expiry


# ============================================================================
# OAuth Provider
# ============================================================================

class OAuthProvider:
    """
    OAuth 2.1 provider for EVA-MCP server.
    
    Handles:
    - Dynamic client registration with Azure AD B2C
    - Token validation (userinfo endpoint)
    - Token refresh (< 1 second)
    - Secret storage in Azure Key Vault
    """
    
    def __init__(self, server_url: Optional[str] = None):
        self.server_url = server_url or settings.mcp_server_url
        self.issuer = settings.azure_ad_b2c_issuer
        
        # Azure Key Vault for secret storage
        self.kv_credential: Optional[DefaultAzureCredential] = None
        self.kv_client: Optional[SecretClient] = None
        
        # OAuth metadata cache
        self.metadata: Optional[OAuthServerMetadata] = None
        self.metadata_loaded_at: Optional[datetime] = None
        
        # Registered clients cache
        self.registered_clients: dict[str, OAuthClientInformation] = {}
        
        # Token validation cache (user_id by access_token, TTL 5 minutes)
        self._token_cache: dict[str, tuple[str, datetime]] = {}
        self._token_cache_ttl = timedelta(minutes=5)
    
    async def initialize(self) -> None:
        """
        Initialize OAuth provider.
        
        Sets up Azure Key Vault client and discovers OAuth metadata.
        """
        # Check if OAuth is configured
        if not self.issuer:
            logger.warning(
                "Azure AD B2C issuer not configured - "
                "OAuth authentication will not work"
            )
            return
        
        # Initialize Azure Key Vault client
        if settings.key_vault_url:
            try:
                self.kv_credential = DefaultAzureCredential()
                self.kv_client = SecretClient(
                    vault_url=settings.key_vault_url,
                    credential=self.kv_credential
                )
                logger.info("✓ Azure Key Vault client initialized")
            except Exception as e:
                logger.error(f"✗ Failed to initialize Key Vault client: {e}")
        else:
            logger.warning("Key Vault URL not configured - secrets will not be stored")
        
        # Discover OAuth metadata
        try:
            await self._discover_metadata()
            logger.info("✓ OAuth metadata discovered")
        except Exception as e:
            logger.error(f"✗ Failed to discover OAuth metadata: {e}")
    
    async def _discover_metadata(self) -> OAuthServerMetadata:
        """
        Discover OAuth server metadata from .well-known endpoint.
        
        Returns:
            OAuth server metadata
        
        Raises:
            Exception: If metadata discovery fails
        """
        # Check cache (refresh every 24 hours)
        if self.metadata and self.metadata_loaded_at:
            age = datetime.utcnow() - self.metadata_loaded_at
            if age < timedelta(hours=24):
                return self.metadata
        
        # Discover metadata
        metadata_url = self.issuer
        if not metadata_url.endswith("/.well-known/openid-configuration"):
            # Azure AD B2C format
            if "/.well-known/" not in metadata_url:
                base = metadata_url.rstrip("/")
                metadata_url = f"{base}/.well-known/openid-configuration"
        
        logger.debug(f"Discovering OAuth metadata: {metadata_url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(metadata_url) as resp:
                if resp.status != 200:
                    raise Exception(
                        f"Failed to fetch OAuth metadata from {metadata_url}: "
                        f"HTTP {resp.status}"
                    )
                
                data = await resp.json()
        
        # Parse metadata
        self.metadata = OAuthServerMetadata(
            issuer=data.get("issuer", self.issuer),
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            userinfo_endpoint=data.get("userinfo_endpoint"),
            registration_endpoint=data.get("registration_endpoint"),
            **data
        )
        
        self.metadata_loaded_at = datetime.utcnow()
        
        logger.debug(
            f"OAuth metadata: issuer={self.metadata.issuer}, "
            f"token_endpoint={self.metadata.token_endpoint}"
        )
        
        return self.metadata
    
    async def register_client(
        self,
        client_id: str,
        client_name: Optional[str] = None
    ) -> OAuthClientInformation:
        """
        Register OAuth client with Azure AD B2C (dynamic client registration).
        
        Args:
            client_id: Unique client identifier
            client_name: Human-readable client name
        
        Returns:
            OAuth client information with client_id and client_secret
        
        Raises:
            Exception: If registration fails or not supported
        """
        # Check cache
        if client_id in self.registered_clients:
            logger.debug(f"Using cached client registration: {client_id}")
            return self.registered_clients[client_id]
        
        # Discover metadata
        metadata = await self._discover_metadata()
        
        if not metadata.registration_endpoint:
            raise Exception(
                "Dynamic client registration not supported by OAuth server. "
                "Azure AD B2C requires pre-configured app registrations."
            )
        
        # Prepare registration request
        registration_data = {
            "client_name": client_name or f"eva-mcp-{client_id}",
            "redirect_uris": [f"{self.server_url}/oauth/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
            "application_type": "web"
        }
        
        logger.info(f"Registering OAuth client: {client_id}")
        
        # Register client
        async with aiohttp.ClientSession() as session:
            async with session.post(
                metadata.registration_endpoint,
                json=registration_data
            ) as resp:
                if resp.status != 201:
                    error_text = await resp.text()
                    raise Exception(
                        f"Client registration failed: HTTP {resp.status} - {error_text}"
                    )
                
                client_data = await resp.json()
        
        # Parse response
        client_info = OAuthClientInformation(
            client_id=client_data["client_id"],
            client_secret=client_data.get("client_secret", ""),
            registration_client_uri=client_data.get("registration_client_uri", ""),
            registration_access_token=client_data.get("registration_access_token", ""),
            **client_data
        )
        
        # Store client secret in Key Vault
        if self.kv_client and client_info.client_secret:
            try:
                secret_name = f"mcp-client-{client_id}-secret"
                await self.kv_client.set_secret(secret_name, client_info.client_secret)
                logger.info(f"✓ Stored client secret in Key Vault: {secret_name}")
            except Exception as e:
                logger.error(f"✗ Failed to store client secret: {e}")
        
        # Cache client info
        self.registered_clients[client_id] = client_info
        
        logger.info(f"✓ Client registered: {client_info.client_id}")
        
        return client_info
    
    async def validate_token(self, access_token: str) -> Optional[str]:
        """
        Validate OAuth access token and extract user ID.
        
        Calls Azure AD B2C userinfo endpoint to validate token.
        Returns user ID (sub claim) if valid, None otherwise.
        
        Args:
            access_token: OAuth access token to validate
        
        Returns:
            User ID (sub claim) if valid, None otherwise
        """
        # Check cache
        if access_token in self._token_cache:
            user_id, cached_at = self._token_cache[access_token]
            if datetime.utcnow() - cached_at < self._token_cache_ttl:
                logger.debug(f"Token validation cache hit: {user_id}")
                return user_id
        
        # Discover metadata
        try:
            metadata = await self._discover_metadata()
        except Exception as e:
            logger.error(f"Failed to discover metadata for token validation: {e}")
            return None
        
        if not metadata.userinfo_endpoint:
            logger.error("Userinfo endpoint not available - cannot validate token")
            return None
        
        # Call userinfo endpoint
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    metadata.userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"}
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Token validation failed: HTTP {resp.status}")
                        return None
                    
                    userinfo = await resp.json()
            
            # Extract user ID (sub claim)
            user_id = userinfo.get("sub")
            if not user_id:
                logger.error("Userinfo response missing 'sub' claim")
                return None
            
            # Cache validation result
            self._token_cache[access_token] = (user_id, datetime.utcnow())
            
            logger.debug(f"✓ Token validated: user_id={user_id}")
            
            return user_id
        
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None
    
    async def refresh_token(
        self,
        client_id: str,
        refresh_token: str
    ) -> OAuthToken:
        """
        Refresh OAuth access token using refresh token.
        
        Target: Complete in < 1 second.
        
        Args:
            client_id: Client ID for token refresh
            refresh_token: Refresh token
        
        Returns:
            New OAuth token with access_token and refresh_token
        
        Raises:
            Exception: If token refresh fails
        """
        start_time = datetime.utcnow()
        
        # Get client info (including secret from Key Vault)
        client_info = self.registered_clients.get(client_id)
        if not client_info:
            raise Exception(f"Client not registered: {client_id}")
        
        # Get client secret from Key Vault if not in memory
        client_secret = client_info.client_secret
        if not client_secret and self.kv_client:
            try:
                secret_name = f"mcp-client-{client_id}-secret"
                secret = await self.kv_client.get_secret(secret_name)
                client_secret = secret.value
            except Exception as e:
                logger.error(f"Failed to retrieve client secret: {e}")
                raise Exception("Client secret not available")
        
        # Discover metadata
        metadata = await self._discover_metadata()
        
        # Exchange refresh token for new access token
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        logger.info(f"Refreshing token for client: {client_id}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                metadata.token_endpoint,
                data=token_data
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(
                        f"Token refresh failed: HTTP {resp.status} - {error_text}"
                    )
                
                response_data = await resp.json()
        
        # Parse response
        new_token = OAuthToken(
            access_token=response_data["access_token"],
            token_type=response_data.get("token_type", "Bearer"),
            expires_in=response_data.get("expires_in", 3600),
            refresh_token=response_data.get("refresh_token", refresh_token),
            scope=response_data.get("scope"),
            **response_data
        )
        
        # Calculate refresh time
        refresh_duration = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(
            f"✓ Token refreshed in {refresh_duration:.3f}s "
            f"(target: < 1.0s) {'✓' if refresh_duration < 1.0 else '⚠ SLOW'}"
        )
        
        return new_token
    
    async def cleanup(self) -> None:
        """
        Cleanup OAuth provider resources.
        """
        if self.kv_client:
            await self.kv_client.close()
            logger.info("✓ Azure Key Vault client closed")
        
        if self.kv_credential:
            await self.kv_credential.close()
            logger.info("✓ Azure credential closed")
