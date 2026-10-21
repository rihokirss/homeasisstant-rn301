from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN, DATA_YAMAHA

# Since this integration supports both config entries and YAML configuration,
# we need to define a CONFIG_SCHEMA
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

def setup(hass, config):
    """Set up the Yamaha R-N301 component."""
    hass.data[DATA_YAMAHA] = {}

    # Here could be code for discovering receivers or other necessary setup

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Yamaha R-N301 receiver from a config entry."""
    await _async_migrate_unique_id(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, ["media_player"])

    # Listen for config entry updates
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def _async_migrate_unique_id(hass: HomeAssistant, entry: ConfigEntry):
    """Move the entity from the host-based unique ID to the config entry ID.

    Up to v1.4.3 the unique ID was built from the host, so changing the host
    in options created a new entity and orphaned the old one.
    """
    old_unique_id = f"yamaha_rn301_{entry.data[CONF_HOST].replace('.', '_')}"

    @callback
    def _migrate(entity_entry: er.RegistryEntry):
        if entity_entry.unique_id == old_unique_id:
            return {"new_unique_id": entry.entry_id}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle config entry update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Handle removal of receiver entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["media_player"])
