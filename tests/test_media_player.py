"""Tests for the Yamaha R-N301 media player entity."""
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity

from custom_components.yamaha_rn301.const import DOMAIN

from .conftest import ENTITY_ID, HOST, setup_entry


async def _call(hass, service, **data):
    await hass.services.async_call(
        "media_player", service, {"entity_id": ENTITY_ID, **data}, blocking=True)


async def _browse(hass, hass_ws_client, content_id=None, content_type="folder"):
    client = await hass_ws_client(hass)
    msg = {"type": "media_player/browse_media", "entity_id": ENTITY_ID}
    if content_id is not None:
        msg.update(media_content_id=content_id, media_content_type=content_type)
    await client.send_json_auto_id(msg)
    return await client.receive_json()


def _children(response):
    assert response["success"], response
    return {c["title"]: c["media_content_id"] for c in response["result"]["children"]}


async def test_state(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert state.attributes["source"] == "Server"
    assert state.attributes["volume_level"] == 0.25
    assert state.attributes["media_artist"] == "Artist"
    assert state.attributes["media_album_name"] == "Album"
    assert state.attributes["media_content_type"] == "music"
    assert state.attributes["device_class"] == "receiver"


async def test_device(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    entity = er.async_get(hass).async_get(ENTITY_ID)
    device = dr.async_get(hass).async_get(entity.device_id)
    assert (device.manufacturer, device.model, device.name) == ("Yamaha", "R-N301", "Yamaha R-N301")
    assert device.identifiers == {(DOMAIN, config_entry.entry_id)}
    assert hass.states.get(ENTITY_ID).attributes["friendly_name"] == "Yamaha R-N301"


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
    # A single missed poll keeps the last state
    await async_update_entity(hass, ENTITY_ID)
    assert hass.states.get(ENTITY_ID).state == "playing"

    for _ in range(4):
        await async_update_entity(hass, ENTITY_ID)
    assert hass.states.get(ENTITY_ID).state == "unavailable"
    assert caplog.text.count("is unreachable") == 1

    receiver.online = True
    await async_update_entity(hass, ENTITY_ID)
    assert hass.states.get(ENTITY_ID).state == "playing"
    assert "is reachable again" in caplog.text


async def test_unreachable_at_startup_is_unavailable(hass, receiver, config_entry):
    receiver.online = False

    await setup_entry(hass, config_entry)

    assert hass.states.get(ENTITY_ID).state == "unavailable"


async def test_shuffle(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)
    assert hass.states.get(ENTITY_ID).attributes["shuffle"] is False

    await _call(hass, "shuffle_set", shuffle=True)

    assert "<SERVER><Play_Control><Play_Mode><Shuffle>On</Shuffle></Play_Mode></Play_Control></SERVER>" in receiver.puts
    assert hass.states.get(ENTITY_ID).attributes["shuffle"] is True

    await _call(hass, "shuffle_set", shuffle=False)
    assert hass.states.get(ENTITY_ID).attributes["shuffle"] is False


async def test_repeat(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)
    assert hass.states.get(ENTITY_ID).attributes["repeat"] == "off"

    await _call(hass, "repeat_set", repeat="all")
    assert receiver.repeat == "All"
    assert hass.states.get(ENTITY_ID).attributes["repeat"] == "all"

    await _call(hass, "repeat_set", repeat="one")
    assert receiver.repeat == "One"
    assert hass.states.get(ENTITY_ID).attributes["repeat"] == "one"


async def test_passive_input_features(hass, receiver, config_entry):
    receiver.input = "OPTICAL"
    await setup_entry(hass, config_entry)

    features = hass.states.get(ENTITY_ID).attributes["supported_features"]
    assert not features & MediaPlayerEntityFeature.SHUFFLE_SET
    assert not features & MediaPlayerEntityFeature.REPEAT_SET
    assert features & MediaPlayerEntityFeature.VOLUME_STEP


async def test_volume_set_rounds(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "volume_set", volume_level=0.29)

    assert receiver.volume == 29


async def test_volume_step(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "volume_up")
    assert receiver.volume == 27

    await _call(hass, "volume_down")
    assert receiver.volume == 25


async def test_mute(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "volume_mute", is_volume_muted=True)
    assert receiver.mute == "On"
    assert hass.states.get(ENTITY_ID).attributes["is_volume_muted"] is True

    await _call(hass, "volume_mute", is_volume_muted=False)
    assert receiver.mute == "Off"
    assert hass.states.get(ENTITY_ID).attributes["is_volume_muted"] is False


async def test_pause_state(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "media_pause")

    assert hass.states.get(ENTITY_ID).state == "paused"


async def test_select_source(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "select_source", source="Coaxial")
    assert receiver.input == "COAXIAL"
    assert hass.states.get(ENTITY_ID).attributes["source"] == "Coaxial"

    # A raw input name the integration does not know is passed through as is.
    await _call(hass, "select_source", source="USB")
    assert receiver.input == "USB"


async def test_unique_id_migrated_from_host(hass, receiver, config_entry):
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "media_player", DOMAIN, f"yamaha_rn301_{HOST.replace('.', '_')}",
        config_entry=config_entry, suggested_object_id="elutuba_yamaha")

    await setup_entry(hass, config_entry)

    entities = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    assert [(e.entity_id, e.unique_id) for e in entities] == [(old.entity_id, config_entry.entry_id)]
    assert hass.states.get(old.entity_id).state == "playing"


async def test_server_browse_page_two(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)

    music = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))
    assert "Folder 8" in music and "Folder 9" not in music
    next_page = music["⬇️ Next Page"]

    page_two = _children(await _browse(hass, hass_ws_client, next_page, "info"))
    # The receiver double-escapes "&"; titles are shown unescaped
    assert "Above & Beyond" in page_two

    folder = await _browse(hass, hass_ws_client, page_two["Folder 10"])
    assert folder["result"]["title"] == "Folder 10"
    assert "Track 10.1" in _children(folder)


async def test_server_play_track_on_page_two(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)

    folder = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_1"))
    page_two = _children(await _browse(hass, hass_ws_client, folder["⬇️ Next Page"], "info"))

    await _call(hass, "play_media", media_content_id=page_two["Track 1.10"], media_content_type="music")

    assert receiver.song == "Track 1.10"
    assert hass.states.get(ENTITY_ID).attributes["media_title"] == "Track 1.10"


async def test_server_browse_waits_for_busy_media_server(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)
    # A media server waking up stays busy for several seconds
    receiver.busy_polls = 8

    music = await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1")

    assert music["result"]["title"] == "Music"


async def test_server_browse_error_when_media_server_stays_busy(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)
    receiver.busy_polls = 1000

    response = await _browse(hass, hass_ws_client, "server_menu:root:Line_1")

    assert not response["success"]
    assert "did not respond" in response["error"]["message"]
