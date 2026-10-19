"""Owner-scoped immutable artifacts in the existing SQLite transaction boundary."""
from netpilot.escalation.models import EscalationPackage
from netpilot.escalation.builder import package_digest
from netpilot.escalation.privacy import safe_package


def initialize(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS escalation_packages (
        package_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL,
        package_version INTEGER NOT NULL, generated_at TEXT NOT NULL, package_json TEXT NOT NULL,
        UNIQUE(user_id,session_id,package_version))""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_escalation_owner_session ON escalation_packages(user_id,session_id,package_version)")


def read(connection, owner, sid):
    packages=[]
    for row in connection.execute("SELECT package_json FROM escalation_packages WHERE user_id=? AND session_id=? ORDER BY package_version",(str(owner),str(sid))):
        p=EscalationPackage.model_validate_json(row["package_json"])
        if p.session_id != sid or package_digest(p) != p.package_digest: raise ValueError("corrupt artifact")
        packages.append(safe_package(p))
    return packages


def write(connection, owner, sid, packages):
    for p in packages:
        if p.session_id != sid or package_digest(p) != p.package_digest: raise ValueError("invalid artifact")
        p = safe_package(p)
        row=connection.execute("SELECT user_id,session_id,package_json FROM escalation_packages WHERE package_id=?",(str(p.package_id),)).fetchone()
        if row:
            stored = EscalationPackage.model_validate_json(row["package_json"])
            if (row["user_id"],row["session_id"]) != (str(owner),str(sid)) or safe_package(stored) != p: raise ValueError("immutable artifact conflict")
            continue
        connection.execute("INSERT INTO escalation_packages VALUES (?,?,?,?,?,?)",(str(p.package_id),str(owner),str(sid),p.package_version,p.generated_at.isoformat(),p.model_dump_json()))
    if packages:
        # Caller provides the configured bounded retained versions, not arbitrary IDs.
        oldest=min(p.package_version for p in packages)
        connection.execute("DELETE FROM escalation_packages WHERE user_id=? AND session_id=? AND package_version<?",(str(owner),str(sid),oldest))
