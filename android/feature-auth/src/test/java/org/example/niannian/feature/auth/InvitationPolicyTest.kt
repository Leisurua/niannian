package org.example.niannian.feature.auth

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InvitationPolicyTest {
    @Test fun switchingFamiliesRequiresReadingTheMatchingInvitation() {
        assertTrue(InvitationPolicy.canConfirm("family-a", "PENDING", "family-a"))
        assertFalse(InvitationPolicy.canConfirm("family-b", "PENDING", "family-a"))
    }

    @Test fun activeRevokedAndUnboundInvitationsCannotConfirm() {
        listOf("ACTIVE", "REVOKED", "LEFT", null).forEach {
            assertFalse(InvitationPolicy.canConfirm("family-a", it, "family-a"))
        }
        assertFalse(InvitationPolicy.canConfirm("family-a", "PENDING", ""))
        assertFalse(InvitationPolicy.canConfirm(null, "PENDING", "family-a"))
    }
}
