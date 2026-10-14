from uuid import uuid4

import anyio
import pytest

from app.modules.conversation.api import _connections, release_connection_lease


class Lease:
    def __init__(self, fail_rollback=False):
        self.fail_rollback = fail_rollback
        self.operations = []

    async def rollback(self):
        await anyio.lowlevel.checkpoint()
        self.operations.append('rollback')
        if self.fail_rollback:
            raise RuntimeError('fictional database failure')

    async def close(self):
        await anyio.lowlevel.checkpoint()
        self.operations.append('close')


def test_cancelled_scope_still_closes_lease_and_releases_connection_budget():
    async def scenario():
        actor = uuid4()
        lease = Lease()
        _connections[actor] = 1
        with anyio.CancelScope() as cancelled:
            cancelled.cancel()
            await release_connection_lease(lease, actor)
        assert lease.operations == ['rollback', 'close']
        assert actor not in _connections
    anyio.run(scenario)


def test_rollback_failure_still_closes_lease_and_preserves_other_connection():
    async def scenario():
        actor = uuid4()
        lease = Lease(fail_rollback=True)
        _connections[actor] = 2
        with pytest.raises(RuntimeError, match='fictional database failure'):
            await release_connection_lease(lease, actor)
        assert lease.operations == ['rollback', 'close']
        assert _connections[actor] == 1
        await release_connection_lease(Lease(), actor)
        assert actor not in _connections
    anyio.run(scenario)
