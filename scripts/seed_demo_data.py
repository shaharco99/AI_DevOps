#!/usr/bin/env python3
"""Fill the database with fake data so demo prompts return something.

Without this the tables are empty, the agent truthfully answers "0 rows", and a
demo looks broken. Re-running is a no-op once the data is there, so the counts
the README quotes stay true. Pass --force to add another batch anyway.

    DATABASE_URL="sqlite+aiosqlite:///./demo.db" python scripts/seed_demo_data.py
"""

import asyncio
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai_devops_assistant.database.models import ApplicationLog, Base, MetricSnapshot, PipelineLog

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./demo.db")

LOG_MESSAGES = {
    "ERROR": "connection refused to redis:6379",
    "WARNING": "slow query took 2.3s",
    "INFO": "request handled",
}


def _uid() -> str:
    return str(uuid.uuid4())


async def seed(force: bool = False) -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    # Naive UTC: the models use DateTime without timezone.
    now = datetime.now(UTC).replace(tzinfo=None)

    async with session_factory() as session:
        existing = await session.scalar(select(func.count()).select_from(PipelineLog))
        if existing and not force:
            print(f"Already seeded ({existing} pipeline runs). Use --force to add more.")
            await engine.dispose()
            return

        for i in range(20):
            failed = i % 4 == 0
            session.add(
                PipelineLog(
                    id=_uid(),
                    pipeline_id=random.choice(["build-api", "deploy-web", "nightly-e2e"]),
                    run_number=1000 + i,
                    status="failed" if failed else "success",
                    log_content=("npm ERR! test suite failed" if failed else "build completed"),
                    error_summary="Test failures in auth.spec.js" if failed else None,
                    created_at=now - timedelta(hours=i),
                )
            )

        for i in range(30):
            level = ["ERROR", "WARNING", "INFO"][i % 3]
            session.add(
                ApplicationLog(
                    id=_uid(),
                    level=level,
                    message=LOG_MESSAGES[level],
                    source=random.choice(["api", "worker"]),
                    created_at=now - timedelta(hours=i % 24),
                )
            )

        for i in range(20):
            session.add(
                MetricSnapshot(
                    id=_uid(),
                    service_name=random.choice(["api", "worker"]),
                    metric_name=random.choice(["cpu_usage", "latency_p95"]),
                    value=round(random.uniform(0.1, 0.95), 3),
                    timestamp=now - timedelta(hours=i),
                    labels={"env": "demo"},
                )
            )

        await session.commit()

    await engine.dispose()
    print("Seeded: 20 pipeline runs (5 failed), 30 application logs, 20 metric snapshots")


if __name__ == "__main__":
    asyncio.run(seed(force="--force" in sys.argv))
