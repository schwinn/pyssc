import time
from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf
from .ssc_device import Ssc_device
from .ssc_device_setup import Ssc_device_setup

found_kh_devices = []
ssc_device_setup = None


def __on_service_state_change(zeroconf: Zeroconf,
                              service_type: str,
                              name: str,
                              state_change: ServiceStateChange) -> None:
    if state_change is ServiceStateChange.Added:
        info = zeroconf.get_service_info(service_type, name)
        if info:
            if info.type == '_ssc._tcp.local.':
                address = info.parsed_addresses()[0]
                name = info.name.replace('._ssc._tcp.local.', '')
                found_kh_devices.append(Ssc_device(name, address))
    global ssc_device_setup
    ssc_device_setup = Ssc_device_setup(found_kh_devices)


def scan(scan_time_seconds=1) -> Ssc_device_setup:
    # Query the SSC service directly.  Enumerating every DNS-SD service first
    # sends the broad `_services._dns-sd._udp.local` query, which some speakers
    # and direct laptop-to-speaker networks do not answer reliably.
    global found_kh_devices, ssc_device_setup
    found_kh_devices = []
    ssc_device_setup = Ssc_device_setup(found_kh_devices)
    zeroconf = Zeroconf(ip_version=IPVersion.V6Only)
    ServiceBrowser(zeroconf, '_ssc._tcp.local.', handlers=[__on_service_state_change])
    time.sleep(scan_time_seconds)
    zeroconf.close()
    return ssc_device_setup
