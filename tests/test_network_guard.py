"""The agent never reads the editor's own machine or local network, whatever a page, a feed or a model asks
(webtools.public, webtools.connected_public, links.get): a name that answers a public address when checked and a
private one at the connection (DNS rebinding), an IPv6 address carrying a private IPv4, a redirection to the LAN."""

import http.server
import socket
import threading

import pytest

from vault_watch_agent import collect, webtools

ADMIN = "<html><title>Router</title><p>" + "the admin page of the router " * 20 + "</p></html>"


class Local(http.server.BaseHTTPRequestHandler):
    routes: dict = {}

    def do_GET(self):  # noqa: N802
        kind, value = Local.routes.get(self.path, ("page", ADMIN))
        if kind == "redirect":
            self.send_response(302)
            self.send_header("Location", value)
            self.end_headers()
            return
        body = value.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def lan(monkeypatch):
    """A page on 127.0.0.1 (the « router »), and a name that is public when checked, then local at the connection."""
    Local.routes = {}
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Local)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    real, asked = socket.getaddrinfo, []

    def rebinding(host, *a, **kw):
        if host == "rebind.example":
            asked.append(host)
            ip = "93.184.215.14" if len(asked) % 2 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, a[0] if a else 80))]
        return real(host, *a, **kw)

    monkeypatch.setattr(socket, "getaddrinfo", rebinding)
    yield httpd.server_address[1]
    httpd.shutdown()


def test_a_name_that_rebinds_to_the_lan_is_not_read(lan):
    with pytest.raises(webtools.WebError, match="private or local"):
        webtools.get(f"http://rebind.example:{lan}/admin")
    with pytest.raises(webtools.WebError, match="private or local"):
        webtools.WebTools().fetch(f"http://rebind.example:{lan}/admin")


def test_the_notes_of_an_item_never_come_from_the_lan(lan):
    Local.routes["/post"] = ("redirect", f"http://127.0.0.1:{lan}/admin")
    assert collect.Collector(feeds=[]).page_notes(f"http://rebind.example:{lan}/post") == ""


@pytest.mark.parametrize("address", ["127.0.0.1", "192.168.1.1", "10.0.0.1", "169.254.169.254", "::1", "fe80::1",
                                     "::ffff:192.168.1.1", "64:ff9b::c0a8:101", "2002:c0a8:101::", "fd00::1"])
def test_a_private_address_in_any_form_is_not_public(address):
    assert not webtools.is_public(address)


def test_a_public_address_is(address="93.184.215.14"):
    assert webtools.is_public(address) and webtools.is_public("2606:4700::1111")
