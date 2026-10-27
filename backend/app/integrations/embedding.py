"""Chinese semantic embeddings on CPU. Runtime never downloads or sends text."""

import asyncio
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import threading

from app.integrations.contracts import EmbeddingResult, ProviderCapabilities, ProviderError
from app.integrations.mock import MockEmbedding

MODEL = 'BAAI/bge-small-zh-v1.5'
MODEL_REPOSITORY = 'Qdrant/bge-small-zh-v1.5'
MODEL_REVISION = '46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59'
QUERY_PREFIX = '为这个句子生成表示以用于检索相关文章：'
MODEL_FILES = ('model_optimized.onnx', 'tokenizer.json', 'config.json',
               'special_tokens_map.json', 'tokenizer_config.json')


def validate_result(result, provider, count):
    result = EmbeddingResult.model_validate(result)
    caps = provider.capabilities()
    if ((result.provider, result.model, result.model_version, result.dimension)
            != (caps.provider, caps.model, caps.version, provider.dimension)
            or len(result.vectors) != count):
        raise ValueError('Invalid embedding identity or count')
    for vector in result.vectors:
        if (len(vector) != provider.dimension
                or any(not math.isfinite(x) or abs(x) > 3.4028234e38 for x in vector)
                or not any(abs(x) >= 1.17549435e-38 for x in vector)):
            raise ValueError('Invalid embedding vector')
    return result


class LocalEmbedding:
    dimension = 512

    def __init__(self, model_path, threads=2):
        self.model_path = Path(model_path).resolve()
        self.threads = threads
        self._model = None
        self._lock = threading.Lock()
        digest = hashlib.sha256(('bge-cls-normalized:title96:chunk320-overlap64:v1:' + QUERY_PREFIX).encode())
        for name in MODEL_FILES:
            with (self.model_path / name).open('rb') as source:
                digest.update(hashlib.file_digest(source, 'sha256').digest())
        self.version = digest.hexdigest()

    def capabilities(self):
        return ProviderCapabilities(provider='local', model=MODEL, version=self.version,
            embedding=True, offline=True, languages=('zh-CN',))

    def _embed(self, texts, purpose):
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(model_name=MODEL, threads=self.threads,
                    providers=['CPUExecutionProvider'], local_files_only=True,
                    specific_model_path=str(self.model_path), cache_dir=str(self.model_path))
            if purpose == 'query':
                texts = [QUERY_PREFIX + text for text in texts]
            return [vector.tolist() for vector in self._model.embed(texts, batch_size=16)]

    async def embed(self, request):
        try:
            vectors = await asyncio.to_thread(self._embed, request.texts, request.purpose)
            return validate_result(EmbeddingResult(vectors=vectors, dimension=self.dimension,
                provider='local', model=MODEL, model_version=self.version), self, len(request.texts))
        except Exception:
            raise ProviderError(code='UNAVAILABLE', provider='local', operation='embed',
                retryable=True, safe_to_retry=True, attempt=1,
                user_message_key='ai.temporarily_unavailable') from None


@lru_cache(maxsize=4)
def _local_provider(model_path, threads):
    return LocalEmbedding(model_path, threads)


def configured_embedding(settings):
    if settings.embedding_provider == 'mock':
        return MockEmbedding()
    return _local_provider(settings.embedding_model_path, settings.embedding_threads)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Download the public BGE model before offline runtime')
    parser.add_argument('--download', required=True, help='Model directory shared by API and worker')
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=MODEL_REPOSITORY, revision=MODEL_REVISION,
        allow_patterns=list(MODEL_FILES), local_dir=args.download)
    provider = LocalEmbedding(args.download)
    provider._embed(['本地模型准备完成'], 'document')
    print(f'{MODEL}: ready, dimension={provider.dimension}, version={provider.version}')
