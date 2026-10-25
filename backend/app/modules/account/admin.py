"""Operator tools; no public administrator bypass endpoint."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.modules.account.backups import prune
from app.modules.account.models import AccountDeletion, ProviderCopy
from app.modules.account.service import confirm_copy, deletion_view
from app.platform.config import get_settings
from app.platform.runtime import configure_event_loop


async def run(args):
    from app.platform.db import session_factory
    async with session_factory() as db:
        if args.command == 'pending':
            rows = (await db.scalars(select(AccountDeletion).order_by(AccountDeletion.requested_at))).all()
            for row in rows:
                status = await deletion_view(db, row)
                if status['status'] != 'COMPLETED':
                    copies = (await db.scalars(select(ProviderCopy).where(ProviderCopy.user_id == row.user_id))).all()
                    status['provider_work'] = [dict(provider=copy.provider,
                        first_possible_send_at=copy.first_possible_send_at, last_possible_send_at=copy.last_possible_send_at,
                        resource_refs=copy.resource_refs) for copy in copies if not copy.confirmed_at]
                    print(json.dumps(jsonable_encoder(status), ensure_ascii=False))
        else:
            # Evidence is kept in the operator's access-controlled system. This
            # database stores only its digest, so it cannot retain personal text.
            evidence = hashlib.sha256(Path(args.evidence_file).read_bytes()).hexdigest()
            await confirm_copy(db, UUID(args.deletion_id), args.kind, args.operator + ':' + evidence, args.provider)
            await db.commit()
            print('COPY_CONFIRMATION_RECORDED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('pending', help='List outstanding deletion work without account names')
    confirm = sub.add_parser('confirm-copy', help='Record verified whole-scope erasure, never just request acceptance')
    confirm.add_argument('deletion_id')
    confirm.add_argument('kind', choices=['backup', 'provider'])
    confirm.add_argument('--provider')
    confirm.add_argument('--operator', required=True, help='Responsible operator reference')
    confirm.add_argument('--evidence-file', required=True, help='Verified deletion/inventory evidence; only its hash is saved')
    backups = sub.add_parser('prune-backups', help='Preview expired managed backups; --apply deletes them')
    backups.add_argument('--directory', required=True)
    backups.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    configure_event_loop()
    try:
        if args.command == 'prune-backups':
            removed = prune(args.directory, get_settings().backup_retention_days, apply=args.apply)
            print(json.dumps(dict(applied=args.apply, files=removed)))
        else:
            asyncio.run(run(args))
    except Exception:
        # No paths, database URLs, credentials or evidence text in failures.
        parser.exit(1, 'LIFECYCLE_OPERATION_FAILED\n')


if __name__ == '__main__':
    main()
