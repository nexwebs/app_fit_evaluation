"""
app/services/checkpointer.py
AsyncPostgresSaver wrapper para recursos limitados (512MB RAM, 2 CPUs)
"""

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.base import BaseCheckpointSaver
from psycopg_pool import ConnectionPool
from typing import Optional, Any, Iterator, AsyncIterator
import asyncio
from concurrent.futures import ThreadPoolExecutor


class AsyncPostgresSaver(BaseCheckpointSaver):
    """Wrapper async para PostgresSaver heredando de BaseCheckpointSaver"""

    def __init__(self, saver: PostgresSaver):
        self._saver = saver
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def aget_tuple(self, config: dict) -> Optional[Any]:
        """Método async para get_tuple"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._saver.get_tuple, config)

    async def aput(
        self, config: dict, checkpoint: dict, metadata: dict, new_versions: dict
    ) -> dict:
        """Método async para put"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._saver.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(self, config: dict, writes: list, task_id: str) -> None:
        """Método async para put_writes"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._saver.put_writes, config, writes, task_id
        )

    def get_tuple(self, config: dict) -> Optional[Any]:
        """Método sync para get_tuple"""
        return self._saver.get_tuple(config)

    def put(
        self, config: dict, checkpoint: dict, metadata: dict, new_versions: dict
    ) -> dict:
        """Método sync para put"""
        return self._saver.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config: dict, writes: list, task_id: str) -> None:
        """Método sync para put_writes"""
        return self._saver.put_writes(config, writes, task_id)

    async def alist(self, config: dict, **kwargs) -> AsyncIterator:
        """Método async para list"""

        def _list():
            return list(self._saver.list(config, **kwargs))

        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(self._executor, _list)

        for item in items:
            yield item

    def list(self, config: dict, **kwargs) -> Iterator:
        """Método sync para list"""
        return self._saver.list(config, **kwargs)

    @property
    def _pool(self):
        """Acceso al pool del saver original"""
        return self._saver._pool


def create_checkpointer(connection_url: str) -> AsyncPostgresSaver:
    """
    Crear checkpointer async con pool optimizado para recursos limitados

    Args:
        connection_url: URL PostgreSQL (formato psycopg, NO asyncpg)

    Returns:
        AsyncPostgresSaver configurado
    """
    pool = ConnectionPool(
        conninfo=connection_url,
        min_size=1,
        max_size=3,
        timeout=20.0,
        max_lifetime=300,
        max_idle=60,
    )

    saver = PostgresSaver(pool)
    return AsyncPostgresSaver(saver)
