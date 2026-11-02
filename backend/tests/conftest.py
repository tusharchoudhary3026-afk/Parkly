import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://parkly:parkly@localhost:5432/parkly_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
