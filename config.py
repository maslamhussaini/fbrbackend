from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # FBR — corrected URLs from working integration
    FBR_SANDBOX_URL: str  = "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata_sb"
    FBR_PROD_URL: str     = "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata"
    FBR_VALIDATE_URL: str = "https://gw.fbr.gov.pk/di_data/v1/di/validateinvoicedata_sb"
    FBR_USE_SANDBOX: bool = True
    FBR_BEARER_TOKEN: str = ""   # set in .env — your token from FBR registration

    # App
    APP_SECRET_KEY: str = "change-this-in-production"
    ENVIRONMENT: str = "development"

    @property
    def FBR_URL(self) -> str:
        return self.FBR_SANDBOX_URL if self.FBR_USE_SANDBOX else self.FBR_PROD_URL

    class Config:
        env_file = ".env"

settings = Settings()
