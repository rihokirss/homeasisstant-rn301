import voluptuous as vol
import aiohttp
import logging
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, DEFAULT_NAME, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


async def _async_test_connection(hass, host):
    """Test connection to Yamaha receiver."""
    try:
        url = f"http://{host}/YamahaRemoteControl/ctrl"
        data = '<?xml version="1.0" encoding="utf-8"?><YAMAHA_AV cmd="GET"><Main_Zone><Basic_Status>GetParam</Basic_Status></Main_Zone></YAMAHA_AV>'

        session = async_get_clientsession(hass)
        timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)

        async with session.post(url, data=data, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        _LOGGER.debug("Connection test to %s failed", host, exc_info=True)
        return False


class YamahaRN301ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Yamaha R-N301 configuration flow class."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step of the configuration flow."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]

            # Must stay outside any try/except: it aborts the flow by raising.
            await self.async_set_unique_id(f"rn301_{host}")
            self._abort_if_unique_id_configured()

            if await _async_test_connection(self.hass, host):
                name = user_input.get(CONF_NAME, DEFAULT_NAME)
                return self.async_create_entry(
                    title=name,
                    data={CONF_HOST: host, CONF_NAME: name}
                )
            errors["base"] = "cannot_connect"

        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow for this config entry."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle integration options flow."""

    async def async_step_init(self, user_input=None):
        """Initial step of the options flow."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            name = user_input[CONF_NAME]
            unique_id = f"rn301_{host}"

            if host != self.config_entry.data.get(CONF_HOST):
                if any(
                    entry.unique_id == unique_id
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                    if entry.entry_id != self.config_entry.entry_id
                ):
                    errors["base"] = "already_configured"
                elif not await _async_test_connection(self.hass, host):
                    errors["base"] = "cannot_connect"

            if not errors:
                # Updating the entry reloads it through the update listener.
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=name,
                    unique_id=unique_id,
                    data={**self.config_entry.data, CONF_HOST: host, CONF_NAME: name},
                )
                return self.async_create_entry(title="", data={})

        current_host = self.config_entry.data.get(CONF_HOST, "")
        current_name = self.config_entry.data.get(CONF_NAME, DEFAULT_NAME)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=current_host): str,
                vol.Required(CONF_NAME, default=current_name): str,
            }),
            errors=errors
        )
