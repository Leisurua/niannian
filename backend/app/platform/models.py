from app.modules.audit.models import AuditLog
from app.modules.auth.models import DeviceSession, User
from app.modules.consent.models import Consent
from app.modules.device.models import DeviceBinding
from app.modules.family.models import Family, FamilyInvitation, FamilyMember

WEEK2_MODELS = (User, Family, AuditLog, FamilyMember, FamilyInvitation, Consent, DeviceBinding, DeviceSession)
