package org.example.niannian.feature.auth

object InvitationPolicy {
    fun canConfirm(selectedFamily: String?, memberStatus: String?, invitationFamily: String): Boolean =
        memberStatus == "PENDING" && !selectedFamily.isNullOrBlank() && selectedFamily == invitationFamily
}
