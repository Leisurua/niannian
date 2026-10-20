"""Register implemented SQLAlchemy models for API, worker and Alembic."""
from app.modules.audit.models import AuditLog
from app.modules.auth.models import DeviceSession, User
from app.modules.consent.models import Consent
from app.modules.device.models import DeviceBinding
from app.modules.family.models import Family, FamilyInvitation, FamilyMember
from app.modules.memory.models import Memory, FileAsset
from app.modules.memory.index_models import MemoryChunk, MemoryEmbedding
from app.modules.reminder.models import Reminder, ReminderExecution
from app.modules.conversation.models import Conversation
from app.modules.conversation.proactive_models import ProactivePreference, ProactiveDailyCounter
from app.modules.signal.models import SignalEvent
from app.modules.notification.models import Notification, NotificationAttempt, NotificationPreference
from app.platform.tasks import Task

DOMAIN_MODELS = (
    User, Family, AuditLog, FamilyMember, FamilyInvitation, Consent, DeviceBinding,
    DeviceSession, Memory, FileAsset, Reminder, ReminderExecution, Conversation,
    MemoryChunk, MemoryEmbedding, Task, ProactivePreference, ProactiveDailyCounter,
    SignalEvent, Notification, NotificationAttempt, NotificationPreference,
)
