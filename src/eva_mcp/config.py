"""
Configuration management for EVA-MCP server.
Loads settings from environment variables using Pydantic Settings.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # MCP Server
    mcp_server_url: str = Field(default="http://localhost:8080", description="Public URL of MCP server")
    mcp_server_host: str = Field(default="0.0.0.0", description="Server host binding")
    mcp_server_port: int = Field(default=8080, description="Server port")
    
    # Azure Cosmos DB
    cosmos_db_connection_string: str = Field(default="", description="Cosmos DB connection string")
    cosmos_db_database: str = Field(default="eva-suite-db", description="Cosmos DB database name")
    
    # Azure Resource Manager
    azure_subscription_id: str = Field(default="", description="Azure subscription ID")
    azure_tenant_id: str = Field(default="", description="Azure tenant ID")
    azure_client_id: str = Field(default="", description="Azure service principal client ID")
    azure_client_secret: str = Field(default="", description="Azure service principal client secret")
    
    # Azure AD B2C (OAuth 2.1)
    azure_ad_b2c_issuer: str = Field(default="", description="Azure AD B2C issuer URL")
    azure_ad_b2c_client_id: str = Field(default="", description="Azure AD B2C client ID")
    
    # Azure Key Vault
    key_vault_url: str = Field(default="", description="Azure Key Vault URL")
    
    # Application Insights
    application_insights_connection_string: str = Field(
        default="", 
        description="Application Insights connection string"
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")


# Global settings instance
settings = Settings()
