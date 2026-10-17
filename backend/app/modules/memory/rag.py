import asyncio
from dataclasses import dataclass
import hashlib
import math
from types import SimpleNamespace

from sqlalchemy import Float, Integer, delete, literal, or_, select, tuple_, update

from app.integrations.contracts import EmbeddingRequest, EmbeddingResult
from app.integrations.mock import MockEmbedding
from app.modules.audit import service as audit
from app.modules.consent import service as consent
from app.modules.memory.index_models import MemoryChunk, MemoryEmbedding, Vector
from app.modules.memory.models import FileAsset, Memory
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7
from app.platform.resource_access import authorize
from app.platform import tasks

PROVIDER = MockEmbedding()
VERSION = PROVIDER.capabilities().version


@dataclass(frozen=True)
class RetrievedMemory:
    id: object
    family_id: object
    subject_user_id: object
    version: int
    content: str
    type: str
    relevance: float


def live(row):
    return (row.verification_status == 'CONFIRMED' and row.verified_at is not None
        and row.deleted_at is None and row.revoked_at is None
        and (row.expires_at is None or row.expires_at > utcnow()))


async def eligible(db, row, actor):
    if not live(row) or row.visibility == 'OWNER_ONLY' and actor.user_id != row.subject_user_id:
        return None
    try:
        await authorize(db, actor, row.family_id, row.subject_user_id, 'MEMORY_READ', row.required_consent_scope)
        return await consent.explicit_scope(db, row.family_id, row.subject_user_id, actor.user_id, row.required_consent_scope)
    except AppError as error:
        if error.status_code in (403, 404):
            return None
        raise


async def invalidate(db, memory_id):
    now = utcnow()
    ids = select(MemoryChunk.id).where(MemoryChunk.memory_id == memory_id)
    await db.execute(update(MemoryEmbedding).where(MemoryEmbedding.memory_chunk_id.in_(ids)).values(status='STALE', invalidated_at=now))
    await db.execute(update(MemoryChunk).where(MemoryChunk.memory_id == memory_id).values(status='STALE', deleted_at=now))


async def changed(db, row):
    await db.flush()
    await invalidate(db, row.id)
    await tasks.enqueue(db, 'MEMORY_CLEANUP', row.family_id, row.id, row.version)
    if live(row):
        await tasks.enqueue(db, 'MEMORY_INDEX', row.family_id, row.id, row.version)
    if row.deleted_at:
        assets = (await db.scalars(select(FileAsset).where(FileAsset.memory_id == row.id, FileAsset.status == 'DELETE_REQUESTED'))).all()
        for asset in assets:
            await tasks.enqueue(db, 'FILE_CLEANUP', asset.family_id, asset.id, 1)


async def consent_changed(db, family_id, subject, scope, epoch):
    rows = (await db.scalars(select(Memory).where(Memory.family_id == family_id,
        Memory.subject_user_id == subject, Memory.required_consent_scope == scope))).all()
    for row in rows:
        await invalidate(db, row.id)
        await tasks.enqueue(db, 'MEMORY_CLEANUP', row.family_id, row.id, row.version, str(epoch))
        if live(row):
            await tasks.enqueue(db, 'MEMORY_INDEX', row.family_id, row.id, row.version, str(epoch))


async def reconcile_index(db, row):
    grant = await eligible(db, row, SimpleNamespace(user_id=row.subject_user_id))
    if grant:
        present = await db.scalar(select(MemoryEmbedding.id).join(MemoryChunk).where(
            MemoryChunk.memory_id == row.id, MemoryChunk.status == 'ACTIVE', MemoryEmbedding.status == 'ACTIVE',
            MemoryEmbedding.metadata_redacted['source_version'].astext.cast(Integer) == row.version).limit(1))
        if not present:
            await tasks.enqueue(db, 'MEMORY_INDEX', row.family_id, row.id, row.version, str(grant), rearm=True)
    else:
        await invalidate(db, row.id)
        await tasks.enqueue(db, 'MEMORY_CLEANUP', row.family_id, row.id, row.version, 'ineligible')


async def maintenance(db, after=None, limit=100):
    if not 1 <= limit <= 100:
        raise ValueError('Maintenance batch must contain 1..100 rows')
    query = select(Memory).order_by(Memory.family_id, Memory.id).limit(limit)
    if after is not None:
        query = query.where(tuple_(Memory.family_id, Memory.id) > tuple_(after[0], after[1]))
    rows = (await db.scalars(query)).all()
    for row in rows:
        await reconcile_index(db, row)
    return (rows[-1].family_id, rows[-1].id) if len(rows) == limit else None


async def prepare_index(db, resource_id, version):
    row = await db.get(Memory, resource_id)
    if not row or row.version != version:
        return None
    grant = await eligible(db, row, SimpleNamespace(user_id=row.subject_user_id))
    if not grant:
        return None
    chunks = [row.content[i:i + 2000] for i in range(0, len(row.content), 2000)] or [row.title]
    return row.family_id, grant, chunks


async def embed(texts, request_id):
    async with asyncio.timeout(5):
        result = EmbeddingResult.model_validate(await PROVIDER.embed(EmbeddingRequest(request_id=request_id, texts=texts)))
    if (result.provider != 'mock' or result.model != 'mock-embedding-v1' or result.model_version != VERSION
            or result.dimension != 8 or len(result.vectors) != len(texts)):
        raise ValueError('Invalid embedding identity')
    for vector in result.vectors:
        if len(vector) != 8 or any(not math.isfinite(x) for x in vector) or sum(x * x for x in vector) == 0:
            raise ValueError('Invalid vector')
    return result


async def apply_index(db, resource_id, version, prepared, result):
    current = await prepare_index(db, resource_id, version)
    if current is None or current != prepared:
        return
    await db.execute(delete(MemoryChunk).where(MemoryChunk.memory_id == resource_id))
    for ordinal, (content, vector) in enumerate(zip(prepared[2], result.vectors, strict=True)):
        chunk = MemoryChunk(id=uuid7(), memory_id=resource_id, ordinal=ordinal, content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest())
        db.add(chunk)
        await db.flush()
        db.add(MemoryEmbedding(id=uuid7(), memory_chunk_id=chunk.id, provider=result.provider,
            model=result.model, model_version=result.model_version, dimension=result.dimension, embedding=vector,
            status='ACTIVE', metadata_redacted={'source_version': version}))


async def cleanup(db, resource_id):
    await db.execute(delete(MemoryChunk).where(MemoryChunk.memory_id == resource_id, MemoryChunk.status != 'ACTIVE'))


async def retrieve(db, actor, family_id, subject, query, request_id):
    """Exact distance over a materialized authorized subset; never global ranking."""
    scopes = []
    for scope in ('FAMILY_MEMORY', 'HEALTH_MEDICATION', 'PORTRAIT', 'VOICE', 'CONVERSATION_SUMMARY', 'CAMERA_PROXIMITY', 'NOTIFICATION_TO_FAMILY'):
        try:
            await authorize(db, actor, family_id, subject, 'MEMORY_READ', scope)
            await consent.explicit_scope(db, family_id, subject, actor.user_id, scope)
            scopes.append(scope)
        except AppError as error:
            if error.status_code not in (403, 404):
                raise
    if not scopes:
        return ()
    vector = (await embed([query], request_id)).vectors[0]
    allowed = select(Memory.id, Memory.family_id, Memory.subject_user_id, Memory.version, Memory.type,
        MemoryChunk.content, MemoryEmbedding.embedding).join(MemoryChunk, MemoryChunk.memory_id == Memory.id).join(
        MemoryEmbedding, MemoryEmbedding.memory_chunk_id == MemoryChunk.id).where(
        Memory.family_id == family_id, Memory.subject_user_id == subject, Memory.required_consent_scope.in_(scopes),
        Memory.verification_status == 'CONFIRMED', Memory.verified_at.is_not(None), Memory.deleted_at.is_(None),
        Memory.revoked_at.is_(None), or_(Memory.expires_at.is_(None), Memory.expires_at > utcnow()),
        or_(Memory.visibility != 'OWNER_ONLY', Memory.subject_user_id == actor.user_id),
        MemoryChunk.status == 'ACTIVE', MemoryChunk.deleted_at.is_(None), MemoryEmbedding.status == 'ACTIVE',
        MemoryEmbedding.invalidated_at.is_(None), MemoryEmbedding.provider == 'mock', MemoryEmbedding.model == 'mock-embedding-v1',
        MemoryEmbedding.model_version == VERSION, MemoryEmbedding.dimension == 8,
        MemoryEmbedding.metadata_redacted['source_version'].astext.cast(Integer) == Memory.version,
    ).cte('authorized_memory').prefix_with('MATERIALIZED')
    distance = allowed.c.embedding.op('<=>', return_type=Float)(literal(vector, type_=Vector()))
    rows = (await db.execute(select(allowed, distance.label('distance')).where(distance <= 0.2)
        .order_by(distance, allowed.c.id).limit(5))).mappings().all()
    await audit.record(db, actor.user_id, 'MEMORY_RAG_READ', 'MEMORY', family_id=family_id, request_id=request_id)
    return tuple(RetrievedMemory(row['id'], row['family_id'], row['subject_user_id'], row['version'],
        row['content'], row['type'], 1 - row['distance']) for row in rows)


async def revalidate(db, actor, records):
    for record in records:
        row = await db.get(Memory, record.id, populate_existing=True)
        if (not row or row.family_id != record.family_id or row.subject_user_id != record.subject_user_id
                or row.version != record.version or not await eligible(db, row, actor)):
            return False
    return True
