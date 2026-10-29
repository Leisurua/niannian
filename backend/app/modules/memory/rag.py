import asyncio
from dataclasses import dataclass
import hashlib
import logging
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import Float, Integer, delete, literal, or_, select, tuple_, update

from app.integrations.contracts import EmbeddingRequest
from app.integrations.embedding import configured_embedding, validate_result
from app.modules.audit import service as audit
from app.modules.consent import service as consent
from app.modules.memory.index_models import MemoryChunk, MemoryEmbedding, Vector
from app.modules.memory.models import FileAsset, Memory
from app.platform.errors import AppError
from app.platform.config import get_settings
from app.platform.identifiers import utcnow, uuid7
from app.platform.logging import log_event
from app.platform.resource_access import authorize
from app.platform import tasks

def get_provider():
    return configured_embedding(get_settings())


@dataclass(frozen=True)
class PreparedIndex:
    family_id: UUID
    subject_user_id: UUID
    grant: UUID
    chunks: tuple[str, ...]
    texts: tuple[str, ...]


def identity_filters(provider):
    caps = provider.capabilities()
    return (MemoryEmbedding.provider == caps.provider, MemoryEmbedding.model == caps.model,
        MemoryEmbedding.model_version == caps.version, MemoryEmbedding.dimension == provider.dimension)


@dataclass(frozen=True)
class RetrievedMemory:
    id: object
    family_id: object
    subject_user_id: object
    version: int
    content: str
    type: str
    relevance: float
    title: str = ''


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
        try:
            provider = get_provider()
        except OSError:
            # Missing model files must not roll back unrelated reminder and
            # notification work in the shared worker cycle.
            log_event(logging.getLogger('nianian.worker'), logging.ERROR,
                'MEMORY_MODEL_UNAVAILABLE', error_code='EMBEDDING_MODEL_UNAVAILABLE')
            return
        present = await db.scalar(select(MemoryEmbedding.id).join(MemoryChunk).where(
            MemoryChunk.memory_id == row.id, MemoryChunk.status == 'ACTIVE', MemoryEmbedding.status == 'ACTIVE',
            MemoryChunk.deleted_at.is_(None), MemoryEmbedding.invalidated_at.is_(None), *identity_filters(provider),
            MemoryEmbedding.metadata_redacted['source_version'].astext.cast(Integer) == row.version).limit(1))
        if not present:
            caps = provider.capabilities()
            profile = hashlib.sha256(f'{caps.provider}:{caps.model}:{caps.version}:{provider.dimension}'.encode()).hexdigest()[:16]
            await tasks.enqueue(db, 'MEMORY_INDEX', row.family_id, row.id, row.version, f'{grant}:{profile}', rearm=True)
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
    row = await db.get(Memory, resource_id, populate_existing=True)
    if not row or row.version != version:
        return None
    grant = await eligible(db, row, SimpleNamespace(user_id=row.subject_user_id))
    if not grant:
        return None
    real = get_provider().capabilities().provider != 'mock'
    size, stride = (320, 256) if real else (2000, 2000)
    chunks = tuple(row.content[i:i + size] for i in range(0, len(row.content), stride)) or (row.title,)
    texts = tuple(f'{row.title[:96]}\n{chunk}' for chunk in chunks) if real else chunks
    return PreparedIndex(row.family_id, row.subject_user_id, grant, chunks, texts)


async def embed(texts, request_id, *, provider=None, purpose='document'):
    provider = provider or get_provider()
    async with asyncio.timeout(get_settings().embedding_timeout_seconds):
        result = await provider.embed(EmbeddingRequest(request_id=request_id, texts=list(texts), purpose=purpose))
    return validate_result(result, provider, len(texts))


async def apply_index(db, resource_id, version, prepared, result):
    current = await prepare_index(db, resource_id, version)
    if current is None or current != prepared:
        return
    validate_result(result, get_provider(), len(prepared.chunks))
    await db.execute(delete(MemoryChunk).where(MemoryChunk.memory_id == resource_id))
    for ordinal, (content, vector) in enumerate(zip(prepared.chunks, result.vectors, strict=True)):
        chunk = MemoryChunk(id=uuid7(), memory_id=resource_id, ordinal=ordinal, content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest())
        db.add(chunk)
        await db.flush()
        db.add(MemoryEmbedding(id=uuid7(), memory_chunk_id=chunk.id, provider=result.provider,
            model=result.model, model_version=result.model_version, dimension=result.dimension, embedding=vector,
            status='ACTIVE', metadata_redacted={'source_version': version}))


async def cleanup(db, resource_id):
    await db.execute(delete(MemoryChunk).where(MemoryChunk.memory_id == resource_id, MemoryChunk.status != 'ACTIVE'))


async def authorized_scopes(db, actor, family_id, subject):
    scopes = []
    for scope in ('FAMILY_MEMORY', 'HEALTH_MEDICATION', 'PORTRAIT', 'VOICE', 'CONVERSATION_SUMMARY', 'CAMERA_PROXIMITY', 'NOTIFICATION_TO_FAMILY'):
        try:
            await authorize(db, actor, family_id, subject, 'MEMORY_READ', scope)
            await consent.explicit_scope(db, family_id, subject, actor.user_id, scope)
            scopes.append(scope)
        except AppError as error:
            if error.status_code not in (403, 404):
                raise
    return scopes


async def retrieve(db, actor, family_id, subject, query, request_id):
    """Rank only the materialized authorized subset.

    Local inference runs between read transactions so revoke is not blocked.
    Callers must not pass unrelated uncommitted writes to this read operation.
    """
    if not await authorized_scopes(db, actor, family_id, subject):
        return ()
    provider = get_provider()
    real = provider.capabilities().provider != 'mock'
    await db.commit()
    vector = (await embed([query], request_id, provider=provider, purpose='query')).vectors[0]
    scopes = await authorized_scopes(db, actor, family_id, subject)
    if not scopes:
        return ()
    allowed = select(Memory.id, Memory.family_id, Memory.subject_user_id, Memory.version, Memory.type, Memory.title,
        MemoryChunk.content, MemoryEmbedding.embedding).join(MemoryChunk, MemoryChunk.memory_id == Memory.id).join(
        MemoryEmbedding, MemoryEmbedding.memory_chunk_id == MemoryChunk.id).where(
        Memory.family_id == family_id, Memory.subject_user_id == subject, Memory.required_consent_scope.in_(scopes),
        Memory.verification_status == 'CONFIRMED', Memory.verified_at.is_not(None), Memory.deleted_at.is_(None),
        Memory.revoked_at.is_(None), or_(Memory.expires_at.is_(None), Memory.expires_at > utcnow()),
        or_(Memory.visibility != 'OWNER_ONLY', Memory.subject_user_id == actor.user_id),
        MemoryChunk.status == 'ACTIVE', MemoryChunk.deleted_at.is_(None), MemoryEmbedding.status == 'ACTIVE',
        MemoryEmbedding.invalidated_at.is_(None), *identity_filters(provider),
        MemoryEmbedding.metadata_redacted['source_version'].astext.cast(Integer) == Memory.version,
    ).cte('authorized_memory').prefix_with('MATERIALIZED')
    distance = allowed.c.embedding.op('<=>', return_type=Float)(literal(vector, type_=Vector()))
    minimum = get_settings().embedding_min_relevance if real else 0.8
    # One best chunk per memory leaves room for other relevant records.
    best = select(allowed, distance.label('distance')).where(distance <= 1 - minimum).distinct(
        allowed.c.id).order_by(allowed.c.id, distance).subquery()
    rows = (await db.execute(select(best).order_by(best.c.distance, best.c.id).limit(5))).mappings().all()
    await audit.record(db, actor.user_id, 'MEMORY_RAG_READ', 'MEMORY', family_id=family_id, request_id=request_id)
    return tuple(RetrievedMemory(row['id'], row['family_id'], row['subject_user_id'], row['version'],
        row['content'], row['type'], 1 - row['distance'], title=row['title']) for row in rows)


async def revalidate(db, actor, records):
    for record in records:
        row = await db.get(Memory, record.id, populate_existing=True)
        if (not row or row.family_id != record.family_id or row.subject_user_id != record.subject_user_id
                or row.version != record.version or not await eligible(db, row, actor)):
            return False
    return True
