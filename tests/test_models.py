from app.db.base import Base


def test_expected_tables_are_registered():
    expected = {'users', 'sessions', 'documents', 'document_chunks', 'messages', 'agent_runs'}
    assert expected.issubset(set(Base.metadata.tables.keys()))
