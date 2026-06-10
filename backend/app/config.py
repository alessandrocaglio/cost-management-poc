"""
Configuration management for Cost Management Redux backend.

Loads settings from environment variables and .env file using pydantic-settings.
"""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration settings.

    Loads from environment variables and .env file.
    Required fields will raise validation error if missing.
    """

    # Red Hat Cost Management API credentials
    # Optional when override_token is set
    cost_client_id: str = Field(
        default="",
        description="Red Hat API Client ID for authentication"
    )
    cost_client_secret: SecretStr = Field(
        default="",
        description="Red Hat API Client Secret (sensitive, will be masked in logs)"
    )

    # Optional: Override token (set via OVERRIDE_TOKEN environment variable)
    override_token: str | None = Field(
        default=None,
        description="Override bearer token for development/testing"
    )

    # Cache configuration
    cache_ttl_seconds: int = Field(
        default=900,
        description="API response cache TTL in seconds (default: 15 minutes)",
        ge=0,
        le=3600
    )

    # Red Hat API endpoints
    sso_token_url: str = Field(
        default="https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token",
        description="Red Hat SSO token endpoint for OAuth2 authentication"
    )
    cost_api_base_url: str = Field(
        default="https://console.redhat.com/api/cost-management/v1",
        description="Red Hat Cost Management API base URL"
    )

    # Server configuration
    host: str = Field(
        default="0.0.0.0",
        description="Server bind address"
    )
    port: int = Field(
        default=8000,
        description="Server port",
        ge=1,
        le=65535
    )

    # CORS configuration
    cors_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins (use * for all)"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: str) -> list[str]:
        """Parse CORS origins from comma-separated string to list."""
        if v == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    def get_client_secret(self) -> str:
        """Get the plain text client secret (use carefully)."""
        return self.cost_client_secret.get_secret_value()

    def model_post_init(self, __context) -> None:
        """Validate that either OAuth2 credentials or override_token is provided."""
        if not self.override_token:
            # If no override token, OAuth2 credentials are required
            if not self.cost_client_id or not self.cost_client_secret.get_secret_value():
                raise ValueError(
                    "Either OVERRIDE_TOKEN or both COST_CLIENT_ID and COST_CLIENT_SECRET must be provided"
                )


def get_settings() -> Settings:
    """
    Get or create the global settings instance.

    This function allows lazy initialization and makes testing easier.
    """
    return Settings()


# Global settings instance (lazy initialization for app runtime)
# Use get_settings() in tests or when you need control over initialization
_settings: Settings | None = None


def load_settings() -> Settings:
    """Load and cache the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
