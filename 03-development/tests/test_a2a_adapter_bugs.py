import concurrent.futures
import ipaddress
import socket
import time

from app.services.aee.a2a_adapter import A2AAdapter, _is_public_address


def test_id_a2a_01_ipv6_6to4_ssrf_blocked():
    """a2a_adapter#1: 6to4 and Teredo addresses must be rejected."""
    ip_6to4 = ipaddress.IPv6Address("2002:0a0b:0c0d::1")
    assert not _is_public_address(ip_6to4), "6to4 address should be blocked"

    ip_teredo = ipaddress.IPv6Address("2001:0000:4136:e378:8000:63bf:3fff:fdd2")
    assert not _is_public_address(ip_teredo), "Teredo address should be blocked"


def test_id_a2a_11_dns_pinning_thread_safety():
    """a2a_adapter#11: concurrent DNS pinning should not pollute socket.getaddrinfo."""
    adapter1 = A2AAdapter("http://agent1.local")
    adapter2 = A2AAdapter("http://agent2.local")

    # Pre-populate validated IPs so they try to patch
    adapter1._validated_ips["agent1.local"] = ({"1.1.1.1"}, 1e10)
    adapter2._validated_ips["agent2.local"] = ({"2.2.2.2"}, 1e10)

    original_getaddrinfo = socket.getaddrinfo

    def task1():
        with adapter1._pinned_dns_lock("http://agent1.local"):
            time.sleep(0.1)

    def task2():
        with adapter2._pinned_dns_lock("http://agent2.local"):
            time.sleep(0.1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(task1)
        f2 = executor.submit(task2)
        concurrent.futures.wait([f1, f2])

    assert socket.getaddrinfo is original_getaddrinfo, "Global socket.getaddrinfo was not restored correctly!"
