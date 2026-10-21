"""Tests for the Yamaha R-N301 config and options flows."""
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yamaha_rn301.const import DOMAIN

from .conftest import ENTITY_ID, HOST, NAME, setup_entry

NEW_HOST = "192.168.0.227"


async def _start_user_flow(hass, user_input):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def test_user_flow_creates_entry(hass, receiver):
    result = await _start_user_flow(hass, {CONF_HOST: HOST, CONF_NAME: "Elutuba"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Elutuba"
    assert result["data"] == {CONF_HOST: HOST, CONF_NAME: "Elutuba"}
    assert result["result"].unique_id == f"rn301_{HOST}"


async def test_user_flow_cannot_connect(hass, receiver):
    receiver.online = False

    result = await _start_user_flow(hass, {CONF_HOST: HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass, receiver, config_entry):
    result = await _start_user_flow(hass, {CONF_HOST: HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


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
    assert config_entry.unique_id == f"rn301_{NEW_HOST}"
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
    MockConfigEntry(domain=DOMAIN, unique_id=f"rn301_{NEW_HOST}",
                    data={CONF_HOST: NEW_HOST, CONF_NAME: "Other"}).add_to_hass(hass)
    await setup_entry(hass, config_entry)

    result = await _submit_options(hass, config_entry, {CONF_HOST: NEW_HOST, CONF_NAME: NAME})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured"}
    assert config_entry.data[CONF_HOST] == HOST
