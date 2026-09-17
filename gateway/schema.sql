-- Additive migration: no existing RAG data is modified or assigned to users.
CREATE TABLE IF NOT EXISTS gateway_users (
    subject VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS gateway_resources (
    kind VARCHAR(16) NOT NULL CHECK (kind IN ('session', 'document', 'upload')),
    resource_id UUID NOT NULL,
    subject VARCHAR(255) NOT NULL REFERENCES gateway_users(subject),
    session_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, resource_id)
);
CREATE INDEX IF NOT EXISTS gateway_resources_owner ON gateway_resources(subject, kind);
CREATE TABLE IF NOT EXISTS gateway_requests (
    subject VARCHAR(255) NOT NULL REFERENCES gateway_users(subject),
    agent VARCHAR(80) NOT NULL,
    request_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('reserved', 'completed', 'failed', 'uncertain')),
    metered BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (subject, agent, request_id)
);
CREATE INDEX IF NOT EXISTS gateway_requests_quota ON gateway_requests(subject, agent, status) WHERE metered;
