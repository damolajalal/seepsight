# Jira account linking

Seepsight can issue a short-lived, single-use pairing code for the authenticated company account. The separate Seepsight Intelligence for Jira API redeems this code against the signed Atlassian Jira user identity.

## User flow

1. Sign in to Seepsight with a verified Firebase account.
2. In the left sidebar, open **Connect Seepsight to Jira**.
3. Select **Generate Jira connection code**.
4. Copy the code and enter it in the Seepsight Intelligence for Jira app.
5. The code expires after 10 minutes and can be redeemed once.
6. Sign out of Seepsight when finished, especially on a shared device.

## Security properties

- The panel is rendered only after the existing authentication flow verifies the Firebase ID token, checks revocation, and re-resolves active company membership.
- The code issuer re-resolves the user's company and email membership again; it does not accept a company ID or role from the browser.
- Codes are generated using Python's cryptographically secure `secrets` module.
- Only a SHA-256 hash of the code is stored in Firestore at `_jira_pairing_codes/{code_hash}`; the raw code is displayed once in the authenticated Streamlit session.
- Codes expire after 10 minutes.
- Issuance is rate-limited to one code per account per 60 seconds.
- The Jira API consumes the code and creates the `_jira_account_links/{hash(cloudId:accountId)}` link in a Firestore transaction. It revalidates the Firebase user, email, company, and active membership.
- The Jira API rejects codes if the user's company membership changed after issuance.
- The raw code is cleared from Streamlit session state on logout or when the user hides it.
- The Jira API supports revoking the current Atlassian identity link; the Jira UI/disconnect action is not yet wired.

## Current limitations

- The Seepsight sidebar can issue pairing codes, and the separate API has redemption and revocation endpoints.
- The Forge Remote hostname and manifest configuration are not yet set because the API has not been deployed.
- The Jira app does not yet expose the pairing-code entry UI or live connection status.
- No production pairing has been completed or tested against live Firestore.
