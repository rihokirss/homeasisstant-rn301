import logging
import xml.etree.ElementTree as ET

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


async def async_get_serial(hass, host):
    """Return the receiver's System_ID, or None if it cannot be reached.

    The System_ID is also the UPnP serial number the receiver announces over
    SSDP. An empty string means the receiver answered without one.
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
        return ET.fromstring(text).findtext("System/Config/System_ID") or ""
    except Exception:
        _LOGGER.debug("Could not read System_ID from %s", host, exc_info=True)
        return None
