from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import Base

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as connection:
        # API and worker may start together. Serialize bootstrap without adding another service.
        await connection.execute(text("SELECT pg_advisory_xact_lock(73402291)"))
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS project_id uuid")
        )
        await connection.execute(text("ALTER TABLE documents ALTER COLUMN project_id SET NOT NULL"))
        await connection.execute(
            text(
                """
                DO $$ BEGIN
                  ALTER TABLE documents ADD CONSTRAINT documents_project_id_fkey
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$
                """
            )
        )
        await connection.execute(text("DROP INDEX IF EXISTS ix_documents_sha256"))
        await connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_documents_sha256 ON documents (sha256)")
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_documents_project_id ON documents (project_id)"
            )
        )
        await connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_project_sha256 "
                "ON documents (project_id, sha256)"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_facts_embedding_hnsw "
                "ON facts USING hnsw (embedding vector_cosine_ops)"
            )
        )
