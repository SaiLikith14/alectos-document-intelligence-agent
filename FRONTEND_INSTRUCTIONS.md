# Paste this into AI Studio after configuring the gateway

Update the existing Alectos React frontend to use the new authentication gateway.

- Use Firebase Authentication with Google sign-in. Ask me for my Firebase web app's public configuration if it is missing. Never request or embed the backend shared secret or a Gemini server API key
- Require login before creating sessions, uploading files, or asking questions
- Send the current Firebase ID token from user.getIdToken() in Authorization: Bearer on each gateway request
- Set VITE_ALECTOS_API_BASE_URL to the gateway URL. Use that one endpoint; remove the direct backend fallback. Point any Vite development proxy at the gateway
- Create sessions after login. Reset user-specific documents, answers, sessions, and pending requests when the user signs out or switches accounts
- Add Idempotency-Key: crypto.randomUUID() to each new question submission, both normal and streamed. Retain that key for that submission. Never automatically replay a query with a new key after a timeout
- Fetch GET /api/v1/me/usage after login and after each query. Read agents[0].trial_enforced, remaining, and pending_requests. null remaining means no enforced trial limit; pending requests can still block a run
- Display one free request per agent only when trial_enforced is true. Show the upgrade message on detail.code=trial_exhausted. Handle 409 duplicate_request or request_pending without starting a new request automatically
- Disable all submit and quick-prompt buttons during a request
- Render meta/token/done/error events. Mark success only on done. On error or unexpected EOF show failure/interruption and refresh usage
- Preserve the existing UI, upload fields, citations, and response contract
- For uploads, use stable attachment IDs rather than array positions
- Login must remain enabled when backend trial enforcement is disabled

Do not claim that login works until it has been tested against my configured Firebase project and gateway. Do not label the simulated homepage agent preview as real retrieval.
