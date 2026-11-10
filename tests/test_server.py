"""Which requests the local search service answers."""
from semsearch import config, server


def _request(path, **headers):
    h = server.Handler.__new__(server.Handler)
    h.path = path
    h.headers = headers
    return h


def test_only_this_mac_and_never_another_site():
    host = f"127.0.0.1:{config.load()['port']}"
    assert _request("/search?q=x", Host=host)._trusted()                       # the app, ss
    assert _request("/search?q=x", Host=host, **{"Sec-Fetch-Site": "same-origin"})._trusted()  # the page
    assert not _request("/search?q=x", Host="evil.example:8799")._trusted()    # DNS rebinding
    assert not _request("/search?q=x", Host=host, **{"Sec-Fetch-Site": "cross-site"})._trusted()
    assert not _request("/search?q=x", Host=host, **{"Sec-Fetch-Site": "same-site"})._trusted()  # another local port
    assert not _request("/status", Host=host, Origin="https://evil.example")._trusted()
    assert _request("/", Host=host, **{"Sec-Fetch-Site": "cross-site"})._trusted(), "a link to the page itself is fine"


def test_every_account_gets_its_own_port(monkeypatch):
    for uid, port in [(501, 8799), (502, 8800), (510, 8808), (0, 8799), (1000, 8799)]:
        monkeypatch.setattr("os.getuid", lambda uid=uid: uid)
        assert config.default_port() == port
