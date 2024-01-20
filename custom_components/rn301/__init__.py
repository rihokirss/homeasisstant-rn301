from homeassistant.helpers import discovery
from .const import DOMAIN, DATA_YAMAHA

def setup(hass, config):
    """Seadistage Yamaha R-N301 komponent."""
    hass.data[DATA_YAMAHA] = {}

    # Siin võiks olla kood ressiiverite avastamiseks või muuks vajalikuks

    return True

def async_setup_entry(hass, entry):
    """Seadistage Yamaha R-N301 ressiiver konfiguratsioonivoo kaudu."""
    hass.async_create_task(
        discovery.async_load_platform(hass, 'media_player', DOMAIN, {}, entry)
    )

    return True

def async_remove_entry(hass, entry):
    """Käsitsege ressiiveri eemaldamist."""
    # Siia võib lisada koodi, mis käsitseb ressiiveri eemaldamist
    pass