from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, DATA_YAMAHA

def setup(hass, config):
    """Set up the Yamaha R-N301 component."""
    hass.data[DATA_YAMAHA] = {}

    # Here could be code for discovering receivers or other necessary setup

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Yamaha R-N301 receiver from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, ["media_player"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Handle removal of receiver entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["media_player"])