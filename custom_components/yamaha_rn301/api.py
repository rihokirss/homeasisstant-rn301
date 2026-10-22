import logging
import xml.etree.ElementTree as ET

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


async def _async_fetch_system_config_root(hass, host):
    """Single POST to <System><Config>GetParam</Config></System>; returns parsed Element or None.

    This is the only HTTP request made; callers can extract both serial and
    firmware version from the same response to avoid duplicate requests.
    """
    try:
        url = f"http://{host}/YamahaRemoteControl/ctrl"
        data = '<?xml version="1.0" encoding="utf-8"?><YAMAHA_AV cmd="GET"><System><Config>GetParam</Config></System></YAMAHA_AV>'

        session = async_get_clientsession(hass)
        timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)

        async with session.post(url, data=data, timeout=timeout) as response:
            if response.status != 200:
                return None
            text = await response.text()
        return ET.fromstring(text)
    except Exception:
        _LOGGER.debug("Could not read System config from %s", host, exc_info=True)
        return None


async def async_get_serial(hass, host):
    """Return the receiver's System_ID (serial number), or None if it cannot be reached.

    The System_ID is also the UPnP serial number the receiver announces over
    SSDP. An empty string means the receiver answered without one.
    """
    serial, _version = await async_get_system_info(hass, host)
    return serial


async def async_get_system_info(hass, host):
    """Return (serial, firmware_version) from a single GET request.

    Use this when both values are needed to avoid duplicate requests.
    Returns (None, None) when the receiver cannot be reached.
    """
    root = await _async_fetch_system_config_root(hass, host)
    if root is None:
        return None, None
    serial = root.findtext("System/Config/System_ID") or ""
    version = root.findtext("System/Config/Version") or None
    return serial, version
