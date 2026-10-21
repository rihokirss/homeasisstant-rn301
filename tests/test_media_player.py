"""Tests for the Yamaha R-N301 media player entity."""
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity

from custom_components.yamaha_rn301.const import DOMAIN

from .conftest import ENTITY_ID, HOST, setup_entry


async def _call(hass, service, **data):
    await hass.services.async_call(
        "media_player", service, {"entity_id": ENTITY_ID, **data}, blocking=True)


async def test_state(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert state.attributes["source"] == "Server"
    assert state.attributes["volume_level"] == 0.25
    assert state.attributes["media_artist"] == "Artist"


async def test_airplay_input(hass, receiver, config_entry):
    receiver.input = "AirPlay"
    await setup_entry(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state.attributes["source"] == "AirPlay"
    assert state.attributes["media_title"] == "Song"


async def test_unknown_input_does_not_break_update(hass, receiver, config_entry):
    receiver.input = "USB"
    receiver.volume = 40
    await setup_entry(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state.attributes["source"] == "USB"
    assert state.attributes["volume_level"] == 0.4


async def test_unreachable_receiver_is_unavailable(hass, receiver, config_entry, caplog):
    await setup_entry(hass, config_entry)

    receiver.online = False
    for _ in range(3):
        await async_update_entity(hass, ENTITY_ID)
    assert hass.states.get(ENTITY_ID).state == "unavailable"
    assert caplog.text.count("is unreachable") == 1

    receiver.online = True
    await async_update_entity(hass, ENTITY_ID)
    assert hass.states.get(ENTITY_ID).state == "playing"
    assert "is reachable again" in caplog.text


async def test_shuffle(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)
    assert hass.states.get(ENTITY_ID).attributes["shuffle"] is False

    await _call(hass, "shuffle_set", shuffle=True)

    assert "<SERVER><Play_Control><Play_Mode><Shuffle>On</Shuffle></Play_Mode></Play_Control></SERVER>" in receiver.puts
    assert hass.states.get(ENTITY_ID).attributes["shuffle"] is True

    await _call(hass, "shuffle_set", shuffle=False)
    assert hass.states.get(ENTITY_ID).attributes["shuffle"] is False


async def test_passive_input_has_no_shuffle(hass, receiver, config_entry):
    receiver.input = "OPTICAL"
    await setup_entry(hass, config_entry)

    features = hass.states.get(ENTITY_ID).attributes["supported_features"]
    assert not features & MediaPlayerEntityFeature.SHUFFLE_SET


async def test_volume_set_rounds(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "volume_set", volume_level=0.29)

    assert receiver.volume == 29


async def test_pause_state(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "media_pause")

    assert hass.states.get(ENTITY_ID).state == "paused"


async def test_unique_id_migrated_from_host(hass, receiver, config_entry):
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "media_player", DOMAIN, f"yamaha_rn301_{HOST.replace('.', '_')}",
        config_entry=config_entry, suggested_object_id="elutuba_yamaha")

    await setup_entry(hass, config_entry)

    entities = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    assert [(e.entity_id, e.unique_id) for e in entities] == [(old.entity_id, config_entry.entry_id)]
    assert hass.states.get(old.entity_id).state == "playing"


async def test_select_source(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "select_source", source="Coaxial")
    assert receiver.input == "COAXIAL"
    assert hass.states.get(ENTITY_ID).attributes["source"] == "Coaxial"

    # A raw input name the integration does not know is passed through as is.
    await _call(hass, "select_source", source="USB")
    assert receiver.input == "USB"
