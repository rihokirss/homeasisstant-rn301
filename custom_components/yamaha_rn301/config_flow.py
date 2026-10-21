import voluptuous as vol
import logging
from urllib.parse import urlparse
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.service_info.ssdp import ATTR_UPNP_SERIAL, SsdpServiceInfo
from .api import async_get_serial
from .const import DOMAIN, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)


class YamahaRN301ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Yamaha R-N301 configuration flow class."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    _discovered_host = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step of the configuration flow."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]

            # The abort helpers raise, so they must stay outside any try/except
            self._async_abort_entries_match({CONF_HOST: host})

            serial = await async_get_serial(self.hass, host)
            if serial is None:
                errors["base"] = "cannot_connect"
            else:
                # Re-adding a configured receiver at a new address updates its host
                await self.async_set_unique_id(serial or f"rn301_{host}")
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                name = user_input.get(CONF_NAME, DEFAULT_NAME)
                return self.async_create_entry(
                    title=name,
                    data={CONF_HOST: host, CONF_NAME: name}
                )

        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo):
        """Handle a receiver announced over SSDP.

        For a receiver that is already configured this keeps its host up to
        date when it gets a new IP address from DHCP.
        """
        host = urlparse(discovery_info.ssdp_location or "").hostname
        serial = discovery_info.upnp.get(ATTR_UPNP_SERIAL)
        if not host or not serial:
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        # Entries whose unique ID has not been migrated to the serial yet
        self._async_abort_entries_match({CONF_HOST: host})

        self._discovered_host = host
        self.context["title_placeholders"] = {"name": f"{DEFAULT_NAME} ({host})"}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        """Confirm adding a discovered receiver."""
        if user_input is not None:
            return self.async_create_entry(
                title=DEFAULT_NAME,
                data={CONF_HOST: self._discovered_host, CONF_NAME: DEFAULT_NAME},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"host": self._discovered_host},
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

            if host != self.config_entry.data.get(CONF_HOST):
                if any(
                    entry.data.get(CONF_HOST) == host
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                    if entry.entry_id != self.config_entry.entry_id
                ):
                    errors["base"] = "already_configured"
                elif await async_get_serial(self.hass, host) is None:
                    errors["base"] = "cannot_connect"

            if not errors:
                # Updating the entry reloads it through the update listener.
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=name,
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
