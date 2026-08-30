"""Dedicated scheduler process. Do not run inside the FastAPI API process."""
import asyncio
from app.jobs.scheduler import scheduler, setup_scheduler

async def main():
    setup_scheduler()
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)

if __name__ == "__main__":
    asyncio.run(main())
