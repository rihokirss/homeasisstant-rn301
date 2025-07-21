import voluptuous as vol
import aiohttp
import asyncio
import logging
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, DEFAULT_NAME, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

class YamahaRN301ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Yamaha R-N301 configuration flow class."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step of the configuration flow."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            
            # Test connection to the receiver
            try:
                if await self._test_connection(host, self.hass):
                    # Create unique ID
                    await self.async_set_unique_id(f"rn301_{host}")
                    self._abort_if_unique_id_configured()
                    
                    name = user_input.get(CONF_NAME, DEFAULT_NAME)
                    return self.async_create_entry(
                        title=name,
                        data={CONF_HOST: host, CONF_NAME: name}
                    )
                else:
                    errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

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

    async def _test_connection(self, host, hass):
        """Test connection to Yamaha receiver."""
        try:
            url = f"http://{host}/YamahaRemoteControl/ctrl"
            data = '<?xml version="1.0" encoding="utf-8"?><YAMAHA_AV cmd="GET"><Main_Zone><Basic_Status>GetParam</Basic_Status></Main_Zone></YAMAHA_AV>'
            
            session = async_get_clientsession(hass)
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            
            async with session.post(url, data=data, timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle integration options flow."""

    async def async_step_init(self, user_input=None):
        """Initial step of the options flow."""
        errors = {}
        
        if user_input is not None:
            # If host was changed, test the new connection
            if CONF_HOST in user_input:
                host = user_input[CONF_HOST]
                if host != self.config_entry.data.get(CONF_HOST):
                    # Test new host
                    if not await self._test_connection(host):
                        errors["base"] = "cannot_connect"
                    else:
                        # Update the config entry with new host
                        new_data = dict(self.config_entry.data)
                        new_data[CONF_HOST] = host
                        # Also update name if changed
                        if CONF_NAME in user_input:
                            new_data[CONF_NAME] = user_input[CONF_NAME]
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, data=new_data
                        )
            
            if not errors:
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
    
    async def _test_connection(self, host):
        """Test connection to Yamaha receiver."""
        try:
            url = f"http://{host}/YamahaRemoteControl/ctrl"
            data = '<?xml version="1.0" encoding="utf-8"?><YAMAHA_AV cmd="GET"><Main_Zone><Basic_Status>GetParam</Basic_Status></Main_Zone></YAMAHA_AV>'
            
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            
            async with session.post(url, data=data, timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False
