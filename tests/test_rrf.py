from app.services.rrf import reciprocal_rank_fusion


def test_rrf_rewards_items_present_in_multiple_rankings():
    dense = ['a', 'b', 'c']
    sparse = ['b', 'd', 'a']
    fused = reciprocal_rank_fusion([dense, sparse], k=60)
    assert fused[0][0] == 'b'
    assert dict(fused)['b'] > dict(fused)['c']
