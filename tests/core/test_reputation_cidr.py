from azazel_edge.core.offline_ai_evaluator import get_offline_evaluator


def test_reputation_private_networks_low_risk():
    ev = get_offline_evaluator()
    for ip in [
        '10.0.0.1', '172.16.5.10', '192.168.0.100'
    ]:
        rep = ev._analyze_source_reputation(ip)
        assert rep['score'] <= 0.3
        assert rep['type'] in ('private', 'local')


def test_reputation_linklocal_and_invalid():
    ev = get_offline_evaluator()
    # link-local
    rep = ev._analyze_source_reputation('169.254.1.1')
    assert rep['score'] <= 0.3
    # invalid
    rep2 = ev._analyze_source_reputation('999.999.999.999')
    assert rep2['score'] >= 0.8
