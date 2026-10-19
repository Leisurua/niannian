"""Approved W7-01..04. Frozen DDL snapshot, no runtime model imports."""
from alembic import op
import sqlalchemy as sa

revision = '20261019_week7_notifications'
down_revision = '20261017_week6_conversation'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE signal_event (
            id UUID NOT NULL,
            owner_user_id UUID NOT NULL,
            family_id UUID NOT NULL,
            type VARCHAR(32) NOT NULL,
            severity VARCHAR(8) DEFAULT 'L1' NOT NULL,
            source_conversation_id UUID,
            source_message_id UUID,
            evidence_summary TEXT,
            evidence_hash VARCHAR(64),
            confidence NUMERIC(5, 4),
            rule_id VARCHAR(96),
            rule_version VARCHAR(64),
            policy_version VARCHAR(64) NOT NULL,
            trigger_category VARCHAR(64) NOT NULL,
            consent_check_result VARCHAR(16) NOT NULL,
            status VARCHAR(24) DEFAULT 'DETECTED' NOT NULL,
            dedupe_key VARCHAR(64),
            duplicate_of_id UUID,
            detected_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            validated_at TIMESTAMP WITH TIME ZONE,
            notified_at TIMESTAMP WITH TIME ZONE,
            last_action_by UUID,
            last_action_at TIMESTAMP WITH TIME ZONE,
            resolution_code VARCHAR(32),
            resolved_at TIMESTAMP WITH TIME ZONE,
            retention_until TIMESTAMP WITH TIME ZONE NOT NULL,
            deleted_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            CONSTRAINT ck_signal_type CHECK (type IN ('PHYSICAL_DISCOMFORT','EMOTION_EXPRESSION','IMPORTANT_MEMORY','MISS_FAMILY','SCAM_RISK','EMERGENCY')),
            CONSTRAINT ck_signal_severity CHECK (severity IN ('L0','L1','L2','L3','L4')),
            CONSTRAINT ck_signal_status CHECK (status IN ('DETECTED','VALIDATED','NOTIFIED','ACKNOWLEDGED','CONTACTED','FALSE_POSITIVE','RESOLVED','WITHHELD','NOTIFICATION_FAILED')),
            CONSTRAINT ck_signal_consent CHECK (consent_check_result IN ('ALLOWED','DENIED','WITHHELD')),
            CONSTRAINT ck_signal_confidence CHECK (confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_signal_retention CHECK (retention_until >= detected_at),
            CONSTRAINT ck_signal_mock_source CHECK (source_message_id IS NULL AND evidence_hash IS NULL),
            FOREIGN KEY(owner_user_id) REFERENCES "user" (id) ON DELETE RESTRICT,
            FOREIGN KEY(family_id) REFERENCES family (id) ON DELETE RESTRICT,
            FOREIGN KEY(source_conversation_id) REFERENCES conversation (id) ON DELETE SET NULL,
            FOREIGN KEY(duplicate_of_id) REFERENCES signal_event (id) ON DELETE SET NULL,
            FOREIGN KEY(last_action_by) REFERENCES "user" (id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE INDEX ix_signal_dedupe ON signal_event (dedupe_key)
    """)
    op.execute("""
        CREATE INDEX ix_signal_family_owner ON signal_event (family_id, owner_user_id, detected_at)
    """)
    op.execute("""
        CREATE TABLE notification (
            id UUID NOT NULL,
            signal_event_id UUID,
            reminder_execution_id UUID,
            recipient_user_id UUID,
            recipient_contact_snapshot JSONB,
            channel VARCHAR(16) NOT NULL,
            status VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
            summary TEXT NOT NULL,
            policy_version VARCHAR(64) NOT NULL,
            provider VARCHAR(64),
            action VARCHAR(24) DEFAULT 'NONE' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            sent_at TIMESTAMP WITH TIME ZONE,
            delivered_at TIMESTAMP WITH TIME ZONE,
            read_at TIMESTAMP WITH TIME ZONE,
            action_at TIMESTAMP WITH TIME ZONE,
            error_code VARCHAR(64),
            dedupe_key VARCHAR(64),
            retention_until TIMESTAMP WITH TIME ZONE NOT NULL,
            dispatch_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
            deleted_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            CONSTRAINT ck_notification_channel CHECK (channel IN ('IN_APP','PUSH','SMS','PHONE')),
            CONSTRAINT ck_notification_status CHECK (status IN ('PENDING','QUEUED','SENT','DELIVERED','READ','FAILED','CANCELLED')),
            CONSTRAINT ck_notification_action CHECK (action IN ('NONE','ACKNOWLEDGED','CONTACTED','FALSE_POSITIVE')),
            CONSTRAINT ck_notification_minimal CHECK (length(summary) <= 240),
            CONSTRAINT ck_notification_retention CHECK (retention_until >= created_at AND dispatch_deadline >= created_at),
            FOREIGN KEY(signal_event_id) REFERENCES signal_event (id) ON DELETE SET NULL,
            FOREIGN KEY(reminder_execution_id) REFERENCES reminder_execution (id) ON DELETE SET NULL,
            FOREIGN KEY(recipient_user_id) REFERENCES "user" (id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE INDEX ix_notification_recipient ON notification (recipient_user_id, created_at)
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_notification_active_dedupe ON notification (dedupe_key) WHERE status <> 'CANCELLED' AND deleted_at IS NULL
    """)
    op.execute("""
        CREATE TABLE notification_attempt (
            id UUID NOT NULL,
            notification_id UUID NOT NULL,
            attempt_no INTEGER NOT NULL,
            provider VARCHAR(64) NOT NULL,
            status VARCHAR(16) DEFAULT 'STARTED' NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            finished_at TIMESTAMP WITH TIME ZONE,
            provider_message_id VARCHAR(160),
            error_code VARCHAR(64),
            error_detail_redacted TEXT,
            retry_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            CONSTRAINT uq_notification_attempt UNIQUE (notification_id, attempt_no),
            CONSTRAINT ck_notification_attempt_number CHECK (attempt_no > 0),
            CONSTRAINT ck_notification_attempt_status CHECK (status IN ('STARTED','SUCCEEDED','FAILED','RETRY_SCHEDULED')),
            FOREIGN KEY(notification_id) REFERENCES notification (id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE notification_preference (
            id UUID NOT NULL,
            family_id UUID NOT NULL,
            owner_user_id UUID NOT NULL,
            recipient_user_id UUID NOT NULL,
            channels JSONB NOT NULL,
            timezone VARCHAR(64) NOT NULL,
            quiet_hours_start TIME WITHOUT TIME ZONE,
            quiet_hours_end TIME WITHOUT TIME ZONE,
            version INTEGER DEFAULT '1' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_notification_preference UNIQUE (family_id, owner_user_id, recipient_user_id),
            CONSTRAINT ck_notification_preference_version CHECK (version > 0),
            CONSTRAINT ck_notification_preference_quiet CHECK ((quiet_hours_start IS NULL) = (quiet_hours_end IS NULL)),
            CONSTRAINT ck_notification_preference_channels CHECK (jsonb_typeof(channels) = 'array' AND channels <@ '["IN_APP","PUSH"]'::jsonb),
            FOREIGN KEY(family_id) REFERENCES family (id) ON DELETE RESTRICT,
            FOREIGN KEY(owner_user_id) REFERENCES "user" (id) ON DELETE RESTRICT,
            FOREIGN KEY(recipient_user_id) REFERENCES "user" (id) ON DELETE RESTRICT
        )
    """)
    op.drop_constraint('ck_task_kind', 'task_outbox', type_='check')
    op.create_check_constraint('ck_task_kind', 'task_outbox', "kind IN ('MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP','CONVERSATION_SUMMARY','CONVERSATION_SUMMARY_CLEANUP','NOTIFICATION_DISPATCH','SIGNAL_CLEANUP','NOTIFICATION_CLEANUP')")


def downgrade():
    conn = op.get_bind()
    names = ('notification_attempt','notification','signal_event','notification_preference','task_outbox')
    conn.execute(sa.text('LOCK TABLE ' + ','.join(names) + ' IN ACCESS EXCLUSIVE MODE'))
    if any(conn.execute(sa.text('SELECT EXISTS (SELECT 1 FROM ' + name + ')')).scalar() for name in names):
        raise RuntimeError('Downgrade requires an empty disposable database')
    op.drop_table('notification_preference')
    op.drop_table('notification_attempt')
    op.drop_table('notification')
    op.drop_table('signal_event')
    op.drop_constraint('ck_task_kind', 'task_outbox', type_='check')
    op.create_check_constraint('ck_task_kind', 'task_outbox', "kind IN ('MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP','CONVERSATION_SUMMARY','CONVERSATION_SUMMARY_CLEANUP')")
