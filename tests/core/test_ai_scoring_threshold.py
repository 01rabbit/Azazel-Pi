from azazel_edge.monitor.main_suricata import calculate_threat_score


def test_high_risk_exceeds_t1():
    alert = {
        'signature': 'ET MALWARE Trojan.Gen C2 Communication',
        'src_ip': '203.0.113.10',
        'dest_ip': '192.168.1.10',
        'dest_port': 8080,
        'proto': 'TCP',
        'severity': 1,
        'payload_printable': 'POST /gate.php',
        'details': {'metadata': {'malware_family': 'trojan.gen'}},
    }
    score, detail = calculate_threat_score(alert, alert['signature'], use_ai=True)
    # 期待: マルウェアは最低60点保証のため t1(50)を上回る
    assert score >= 60
    assert detail.get('category') in ('malware', 'exploit', 'sqli', 'dos', 'bruteforce', 'scan', 'benign')


def test_benign_https_below_t1():
    alert = {
        'signature': 'ET INFO HTTPS request to legitimate CDN',
        'src_ip': '192.168.1.50',
        'dest_ip': '151.101.1.140',
        'dest_port': 443,
        'proto': 'TCP',
        'severity': 4,
        'payload_printable': 'TLS 1.3 handshake to cdn.example.com',
        'details': {}
    }
    score, detail = calculate_threat_score(alert, alert['signature'], use_ai=True)
    assert score < 50
    assert detail.get('category') == 'benign'
