import asyncio

from cblm_app.service import CBLMGenerationService


def test_generation_start_requires_and_uses_running_event_loop():
    async def run():
        service = object.__new__(CBLMGenerationService)
        service.tasks = {}
        called = asyncio.Event()

        async def fake(job_id):
            called.set()

        service.run = fake
        service.start("job")
        await asyncio.wait_for(called.wait(), 1)
        await service.tasks["job"]

    asyncio.run(run())
