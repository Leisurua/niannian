from app.modules.audit.models import AuditLog
from app.modules.auth.models import DeviceSession, User
from app.modules.consent.models import Consent
from app.modules.device.models import DeviceBinding
from app.modules.family.models import Family, FamilyInvitation, FamilyMember

WEEK2_MODELS = (User, Family, AuditLog, FamilyMember, FamilyInvitation, Consent, DeviceBinding, DeviceSession)

from app.modules.memory.models import Memory, FileAsset
from app.modules.reminder.models import Reminder, ReminderExecution
from app.modules.conversation.models import Conversation

DOMAIN_MODELS = WEEK2_MODELS + (Memory, FileAsset, Reminder, ReminderExecution, Conversation)
from app.modules.memory.index_models import MemoryChunk, MemoryEmbedding
from app.platform.tasks import Task

DOMAIN_MODELS += (MemoryChunk, MemoryEmbedding, Task)
from app.modules.conversation.proactive_models import ProactivePreference, ProactiveDailyCounter

DOMAIN_MODELS += (ProactivePreference, ProactiveDailyCounter)
from app.modules.signal.models import SignalEvent
from app.modules.notification.models import Notification, NotificationAttempt, NotificationPreference

DOMAIN_MODELS += (SignalEvent, Notification, NotificationAttempt, NotificationPreference)
