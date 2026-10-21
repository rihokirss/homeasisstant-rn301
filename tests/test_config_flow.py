"""Tests for the Yamaha R-N301 config and options flows."""
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yamaha_rn301.const import DOMAIN

from .conftest import ENTITY_ID, HOST, NAME, SERIAL, setup_entry

NEW_HOST = "192.168.0.88"


async def _start_user_flow(hass, user_input):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


def _ssdp_info(host, serial=SERIAL):
    return SsdpServiceInfo(
        ssdp_usn=f"uuid:5f9ec1b3::urn:schemas-upnp-org:device:MediaRenderer:1",
        ssdp_st="urn:schemas-upnp-org:device:MediaRenderer:1",
        ssdp_location=f"http://{host}:8080/MediaRenderer/desc.xml",
        upnp={"manufacturer": "Yamaha Corporation", "modelName": "R-N301",
              "friendlyName": "Arvutituba", "serialNumber": serial},
    )


async def test_user_flow_creates_entry(hass, receiver):
    result = await _start_user_flow(hass, {CONF_HOST: HOST, CONF_NAME: "Elutuba"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Elutuba"
    assert result["data"] == {CONF_HOST: HOST, CONF_NAME: "Elutuba"}
    assert result["result"].unique_id == SERIAL


async def test_user_flow_without_serial_uses_host(hass, receiver):
    receiver.serial = ""

    result = await _start_user_flow(hass, {CONF_HOST: HOST, CONF_NAME: NAME})

    assert result["result"].unique_id == f"rn301_{HOST}"


async def test_user_flow_cannot_connect(hass, receiver):
    receiver.online = False

    result = await _start_user_flow(hass, {CONF_HOST: HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass, receiver, config_entry):
    receiver.online = False

    result = await _start_user_flow(hass, {CONF_HOST: HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_new_host_updates_entry(hass, receiver, config_entry):
    receiver.hosts.add(NEW_HOST)

    result = await _start_user_flow(hass, {CONF_HOST: NEW_HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == NEW_HOST


async def test_ssdp_discovery_creates_entry(hass, receiver):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=_ssdp_info(HOST))
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_NAME: NAME}
    assert result["result"].unique_id == SERIAL


async def test_ssdp_discovery_updates_host_after_dhcp_change(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)
    receiver.hosts.add(NEW_HOST)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=_ssdp_info(NEW_HOST))
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == NEW_HOST
    assert hass.states.get(ENTITY_ID).state == "playing"


async def test_ssdp_discovery_without_serial(hass, receiver):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=_ssdp_info(HOST, serial=""))

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_entry_unique_id_migrated_to_serial(hass, receiver):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=f"rn301_{HOST}",
                            data={CONF_HOST: HOST, CONF_NAME: NAME})
    entry.add_to_hass(hass)

    await setup_entry(hass, entry)

    assert entry.unique_id == SERIAL


async def test_entry_unique_id_kept_while_offline(hass, receiver):
    receiver.online = False
    entry = MockConfigEntry(domain=DOMAIN, unique_id=f"rn301_{HOST}",
                            data={CONF_HOST: HOST, CONF_NAME: NAME})
    entry.add_to_hass(hass)

    await setup_entry(hass, entry)

    assert entry.unique_id == f"rn301_{HOST}"


async def _submit_options(hass, entry, user_input):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)
    await hass.async_block_till_done()
    return result


async def test_options_rename_only(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    result = await _submit_options(hass, config_entry, {CONF_HOST: HOST, CONF_NAME: "Elutuba"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.data == {CONF_HOST: HOST, CONF_NAME: "Elutuba"}
    assert config_entry.title == "Elutuba"
    assert hass.states.get(ENTITY_ID).attributes["friendly_name"] == "Elutuba"


async def test_options_change_host_keeps_entity(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)
    receiver.hosts.add(NEW_HOST)

    result = await _submit_options(hass, config_entry, {CONF_HOST: NEW_HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.data[CONF_HOST] == NEW_HOST
    assert config_entry.unique_id == SERIAL
    entities = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)
    assert [e.entity_id for e in entities] == [ENTITY_ID]
    assert hass.states.get(ENTITY_ID).state == "playing"


async def test_options_change_host_cannot_connect(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    result = await _submit_options(hass, config_entry, {CONF_HOST: NEW_HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert config_entry.data[CONF_HOST] == HOST


async def test_options_change_host_already_configured(hass, receiver, config_entry):
    receiver.hosts.add(NEW_HOST)
    MockConfigEntry(domain=DOMAIN, unique_id="OTHER",
                    data={CONF_HOST: NEW_HOST, CONF_NAME: "Other"}).add_to_hass(hass)
    await setup_entry(hass, config_entry)

    result = await _submit_options(hass, config_entry, {CONF_HOST: NEW_HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured"}
    assert config_entry.data[CONF_HOST] == HOST
