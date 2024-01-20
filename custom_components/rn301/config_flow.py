import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN  # Importige vajalikud konstandid

class YamahaRN301ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Yamaha R-N301 konfiguratsioonivoo klass."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Käivitage konfiguratsioonivoo esimene samm."""
        errors = {}

        if user_input is not None:
            # Siin saate lisada koodi ressiiveri ühenduse kontrollimiseks
            # Kui kõik on korras, siis lõpetage voo samm
            return self.async_create_entry(title="Yamaha R-N301", data=user_input)

        data_schema = vol.Schema({
            vol.Required("host"): str,  # Küsib IP-aadressi
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Tagastage valikute voog selle sissejuhatuse jaoks."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Käitleb integratsiooni võimaluste voogu."""

    def __init__(self, config_entry):
        """Konstruktor, mis säilitab konfiguratsioonientri."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Võimaluste voo esimene samm."""
        # Siin saate pakkuda kasutajale täiendavaid konfiguratsioonivõimalusi
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                # Siin defineerige oma võimaluste vorm
            })
        )
