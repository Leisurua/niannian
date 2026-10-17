from alembic import op
from sqlalchemy import text

revision = '20261015_week5_rag_tasks'
down_revision = '20261010_week3_core'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("\nCREATE TABLE memory_chunk (\n\tid UUID NOT NULL, \n\tmemory_id UUID NOT NULL, \n\tordinal INTEGER DEFAULT '0' NOT NULL, \n\tcontent TEXT NOT NULL, \n\tcontent_hash CHAR(64) NOT NULL, \n\tstatus VARCHAR(16) DEFAULT 'ACTIVE' NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_chunk_ordinal UNIQUE (memory_id, ordinal), \n\tCONSTRAINT ck_chunk_ordinal CHECK (ordinal >= 0), \n\tCONSTRAINT ck_chunk_status CHECK (status IN ('ACTIVE','STALE','DELETED')), \n\tFOREIGN KEY(memory_id) REFERENCES memory (id) ON DELETE CASCADE\n)\n\n")
    op.execute("\nCREATE TABLE memory_embedding (\n\tid UUID NOT NULL, \n\tmemory_chunk_id UUID NOT NULL, \n\tprovider VARCHAR(64) NOT NULL, \n\tmodel VARCHAR(128) NOT NULL, \n\tmodel_version VARCHAR(64) NOT NULL, \n\tdimension INTEGER NOT NULL, \n\tembedding VECTOR, \n\tstatus VARCHAR(16) DEFAULT 'PENDING' NOT NULL, \n\tmetadata JSONB DEFAULT '{}' NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tinvalidated_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_embedding_dimension CHECK (dimension > 0), \n\tCONSTRAINT ck_embedding_status CHECK (status IN ('PENDING','ACTIVE','STALE','DELETED','FAILED')), \n\tCONSTRAINT ck_embedding_active CHECK (status <> 'ACTIVE' OR (embedding IS NOT NULL AND vector_dims(embedding) = dimension AND vector_norm(embedding) > 0)), \n\tCONSTRAINT ck_embedding_metadata CHECK (jsonb_typeof(metadata) = 'object'), \n\tFOREIGN KEY(memory_chunk_id) REFERENCES memory_chunk (id) ON DELETE CASCADE\n)\n\n")
    op.execute("\nCREATE TABLE task_outbox (\n\tid UUID NOT NULL, \n\tfamily_id UUID NOT NULL, \n\tresource_id UUID NOT NULL, \n\tresource_version INTEGER NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tbusiness_key VARCHAR(200) NOT NULL, \n\tstatus VARCHAR(16) DEFAULT 'PENDING' NOT NULL, \n\tattempts INTEGER DEFAULT '0' NOT NULL, \n\tmax_attempts INTEGER DEFAULT '5' NOT NULL, \n\tavailable_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tlease_token UUID, \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tlast_error_code VARCHAR(64), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_task_version CHECK (resource_version > 0), \n\tCONSTRAINT ck_task_kind CHECK (kind IN ('MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP')), \n\tCONSTRAINT ck_task_status CHECK (status IN ('PENDING','RUNNING','RETRY','SUCCEEDED','DEAD')), \n\tCONSTRAINT ck_task_attempts CHECK (attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts), \n\tCONSTRAINT ck_task_lease CHECK ((status = 'RUNNING' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR (status <> 'RUNNING' AND lease_token IS NULL AND lease_until IS NULL)), \n\tFOREIGN KEY(family_id) REFERENCES family (id) ON DELETE RESTRICT, \n\tUNIQUE (business_key)\n)\n\n")
    op.execute('CREATE INDEX ix_task_lease ON task_outbox (status, lease_until)')
    op.execute('CREATE INDEX ix_task_ready ON task_outbox (status, available_at)')


def downgrade():
    connection = op.get_bind()
    names = ['memory_embedding', 'memory_chunk', 'task_outbox']
    connection.execute(text('LOCK TABLE ' + ','.join(names) + ' IN ACCESS EXCLUSIVE MODE'))
    for name in names:
        if connection.execute(text('SELECT EXISTS (SELECT 1 FROM ' + name + ' LIMIT 1)')).scalar():
            raise RuntimeError('Downgrade requires an empty disposable database')
    for name in names:
        op.drop_table(name)
