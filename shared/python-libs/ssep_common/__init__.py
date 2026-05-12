import os
import json
import logging
from datetime import datetime, timezone
from typing import Any

from google.cloud import pubsub_v1
from google.cloud import firestore
import redis.asyncio as redis

logger = logging.getLogger("ssep")


def get_env(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise ValueError(f"Environment variable {key} is required")
    return value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class PubSubClient:
    def __init__(self, project_id: str | None = None):
        self.project_id = project_id or get_env("GCP_PROJECT_ID")
        emulator_host = os.environ.get("PUBSUB_EMULATOR_HOST")
        if emulator_host:
            self.publisher = pubsub_v1.PublisherClient(
                transport=pubsub_v1.transports.grpc.AsyncioTransport(
                    channel=pubsub_v1.transports.grpc.create_channel(emulator_host)
                )
            ) if False else pubsub_v1.PublisherClient()
        else:
            self.publisher = pubsub_v1.PublisherClient()

    def topic_path(self, topic_id: str) -> str:
        return self.publisher.topic_path(self.project_id, topic_id)

    def publish(self, topic_id: str, data: dict[str, Any]) -> str:
        payload = json.dumps(data, default=str).encode("utf-8")
        future = self.publisher.publish(self.topic_path(topic_id), payload)
        return future.result()

    def publish_async(self, topic_id: str, data: dict[str, Any]):
        payload = json.dumps(data, default=str).encode("utf-8")
        return self.publisher.publish(self.topic_path(topic_id), payload)


class FirestoreClient:
    _instance = None

    def __init__(self, project_id: str | None = None):
        self.project_id = project_id or get_env("GCP_PROJECT_ID")
        emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
        if emulator_host:
            os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
        self.db = firestore.Client(project=self.project_id)

    @classmethod
    def get_instance(cls) -> "FirestoreClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def collection(self, name: str):
        return self.db.collection(name)

    async def set_document(self, collection: str, doc_id: str, data: dict[str, Any]):
        self.db.collection(collection).document(doc_id).set(data, merge=True)

    async def get_document(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        doc = self.db.collection(collection).document(doc_id).get()
        return doc.to_dict() if doc.exists else None

    async def query_collection(self, collection: str, field: str, op: str, value: Any) -> list[dict]:
        docs = self.db.collection(collection).where(field, op, value).stream()
        return [doc.to_dict() for doc in docs]


class RedisClient:
    _instance = None

    def __init__(self, host: str | None = None, port: int = 6379, db: int = 0):
        self.host = host or get_env("REDIS_HOST", "localhost")
        self.port = port
        self.db = db
        parts = self.host.split(":")
        if len(parts) == 2:
            self.host = parts[0]
            self.port = int(parts[1])
        self._client: redis.Redis | None = None

    @classmethod
    def get_instance(cls) -> "RedisClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def connect(self):
        self._client = redis.Redis(host=self.host, port=self.port, db=self.db, decode_responses=True)

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client

    async def get(self, key: str) -> str | None:
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        await self.client.set(key, value, ex=ex)

    async def get_json(self, key: str) -> dict | list | None:
        raw = await self.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ex: int | None = None):
        await self.set(key, json.dumps(value, default=str), ex=ex)

    async def hget(self, name: str, key: str) -> str | None:
        return await self.client.hget(name, key)

    async def hset(self, name: str, key: str, value: str):
        await self.client.hset(name, key, value)

    async def hgetall(self, name: str) -> dict[str, str]:
        return await self.client.hgetall(name)

    async def close(self):
        if self._client:
            await self._client.close()


VENUE_TOPICS = [
    "crowd.density.updated",
    "queue.wait.changed",
    "gate.scan.event",
    "order.created",
    "order.status.changed",
    "incident.created",
    "incident.updated",
    "notification.send",
]
