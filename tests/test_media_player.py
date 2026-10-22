"""Tests for the Yamaha R-N301 media player entity."""
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar, device_registry as dr, entity_registry as er, issue_registry as ir)
from homeassistant.helpers.entity_component import async_update_entity

from custom_components.yamaha_rn301.const import DOMAIN

from .conftest import ENTITY_ID, HOST, NET_RADIO_TREE, setup_entry


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


async def test_spotify_features(hass, receiver, config_entry):
    receiver.input = "Spotify"
    await setup_entry(hass, config_entry)

    features = hass.states.get(ENTITY_ID).attributes["supported_features"]
    assert features & MediaPlayerEntityFeature.PAUSE
    # The receiver has no shuffle or repeat for Spotify and AirPlay (HTTP 400)
    assert not features & MediaPlayerEntityFeature.SHUFFLE_SET
    with pytest.raises(HomeAssistantError, match="does not support this command"):
        await hass.data["media_player"].get_entity(ENTITY_ID).async_set_shuffle(True)


async def test_command_in_standby_raises(hass, receiver, config_entry):
    receiver.power = "Standby"
    await setup_entry(hass, config_entry)

    with pytest.raises(HomeAssistantError, match="The receiver is in standby"):
        await _call(hass, "volume_set", volume_level=0.3)
    assert receiver.volume == 25


async def test_command_right_after_turn_on_is_sent_again(hass, receiver, config_entry):
    receiver.power = "Standby"
    receiver.start_up_refusals = 2
    await setup_entry(hass, config_entry)

    # As in an automation that turns the receiver on and sets the volume
    await _call(hass, "turn_on")
    await _call(hass, "volume_set", volume_level=0.3)

    assert receiver.volume == 30


async def test_command_to_unreachable_receiver_raises(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)
    receiver.online = False

    with pytest.raises(HomeAssistantError, match="Cannot reach the receiver"):
        await _call(hass, "media_pause")


async def test_volume_set_rounds(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "volume_set", volume_level=0.29)

    assert receiver.volume == 29


async def test_volume_set_clamped_to_receiver_range(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)
    # The service schema rejects such values, so call the entity directly
    entity = hass.data["media_player"].get_entity(ENTITY_ID)

    await entity.async_set_volume_level(1.5)
    assert receiver.volume == 100

    await entity.async_set_volume_level(-0.2)
    assert receiver.volume == 0


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


async def test_tuner_presets_step_through_stored_presets(hass, receiver, config_entry):
    receiver.input = "TUNER"
    receiver.presets = ["1", "2", "5"]
    await setup_entry(hass, config_entry)

    await _call(hass, "media_next_track")
    assert receiver.preset == "5"
    await _call(hass, "media_next_track")
    assert receiver.preset == "1"
    await _call(hass, "media_previous_track")
    assert receiver.preset == "5"


async def test_tuner_without_presets(hass, receiver, config_entry):
    receiver.input = "TUNER"
    receiver.presets = []
    await setup_entry(hass, config_entry)

    with pytest.raises(HomeAssistantError, match="no Tuner presets"):
        await _call(hass, "media_next_track")


async def test_select_source(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    await _call(hass, "select_source", source="Coaxial")
    assert receiver.input == "COAXIAL"
    assert hass.states.get(ENTITY_ID).attributes["source"] == "Coaxial"

    # A raw input name the integration does not know is passed through as
    # is, for receivers with other inputs
    receiver.inputs.add("USB")
    await _call(hass, "select_source", source="USB")
    assert receiver.input == "USB"


async def test_select_source_shown_while_poll_runs(hass, receiver, config_entry, monkeypatch):
    await setup_entry(hass, config_entry)
    # A poll is running, so Home Assistant skips the refresh after the call
    monkeypatch.setattr(hass.data["media_player"].get_entity(ENTITY_ID), "async_update", AsyncMock())

    await _call(hass, "select_source", source="Tuner")

    assert hass.states.get(ENTITY_ID).attributes["source"] == "Tuner"
    await _call(hass, "media_next_track")
    assert receiver.preset == "3"


async def test_select_missing_source_raises(hass, receiver, config_entry):
    await setup_entry(hass, config_entry)

    with pytest.raises(HomeAssistantError, match="does not accept this value"):
        await _call(hass, "select_source", source="USB")
    assert receiver.input == "SERVER"


async def test_unique_id_migrated_from_host(hass, receiver, config_entry):
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "media_player", DOMAIN, f"yamaha_rn301_{HOST.replace('.', '_')}",
        config_entry=config_entry, suggested_object_id="elutuba_yamaha")

    await setup_entry(hass, config_entry)

    entities = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    assert [(e.entity_id, e.unique_id) for e in entities] == [(old.entity_id, config_entry.entry_id)]
    assert hass.states.get(old.entity_id).state == "playing"


async def test_server_browse_continuous_list(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)

    # The 10 entries span two receiver pages but are shown as one list
    music = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))
    assert list(music) == [f"Folder {i}" for i in range(1, 9)] + [
        # The receiver double-escapes "&"; titles are shown unescaped
        "Above & Beyond", "Folder 10"]

    folder = await _browse(hass, hass_ws_client, music["Folder 10"])
    assert folder["result"]["title"] == "Folder 10"
    assert "Track 10.1" in _children(folder)


async def test_server_browse_uses_cache(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)
    music = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))
    await _browse(hass, hass_ws_client, music["Folder 10"])
    receiver.puts.clear()

    # Going back to a list read a moment ago does not read it again
    again = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))

    assert again == music
    assert receiver.puts == []


async def test_server_play_after_cached_browse(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)
    folder_one = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_1"))
    await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_2")
    # Shown from the cache while the receiver still shows Folder 2
    folder_one = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_1"))

    await _call(hass, "play_media", media_content_id=folder_one["Track 1.3"], media_content_type="music")

    assert receiver.song == "Track 1.3"


async def test_long_list_first_view_and_show_all(hass, hass_ws_client, receiver, config_entry, monkeypatch):
    # Only the first page fits in the time for the first view
    monkeypatch.setattr("custom_components.yamaha_rn301.media_player.LIST_FIRST_VIEW_BUDGET", 0)
    await setup_entry(hass, config_entry)

    music = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))
    assert list(music) == [f"Folder {i}" for i in range(1, 9)] + ["⬇️ Show all 10"]

    # The rest is read in the background meanwhile
    full = await _browse(hass, hass_ws_client, music["⬇️ Show all 10"])
    assert full["result"]["title"] == "Music"
    assert list(_children(full))[-2:] == ["Above & Beyond", "Folder 10"]

    # From now on the list opens whole
    assert len(_children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))) == 10


async def test_browsing_elsewhere_stops_background_read(hass, hass_ws_client, receiver, config_entry, monkeypatch):
    monkeypatch.setattr("custom_components.yamaha_rn301.media_player.LIST_FIRST_VIEW_BUDGET", 0)
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    receiver.busy_polls = 2

    genres = _children(await _browse(hass, hass_ws_client, "netradio_menu:root:Line_1:Line_1"))
    assert "⬇️ Show all 11" in genres
    estonia = _children(await _browse(hass, hass_ws_client, "netradio_menu:root:Line_1:Line_2:Line_1"))

    assert list(estonia) == ["Raadio 2", "Vikerraadio"]
    full = _children(await _browse(hass, hass_ws_client, genres["⬇️ Show all 11"]))
    assert list(full) == [f"Genre {i}" for i in range(1, 12)]


async def test_lists_are_kept_across_restarts(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)
    music = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    receiver.puts.clear()

    assert _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1")) == music
    assert receiver.puts == []


async def test_old_list_is_read_again_in_background(hass, hass_ws_client, receiver, config_entry, monkeypatch):
    monkeypatch.setattr("custom_components.yamaha_rn301.media_player.LIST_REFRESH_AGE", 0)
    await setup_entry(hass, config_entry)
    await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1")
    await hass.async_block_till_done(wait_background_tasks=True)
    music = receiver.server_tree[1][0][1][0][1]
    music.append(("New Folder", []))

    # The old list is shown at once and read again for next time
    assert "New Folder" not in _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "New Folder" in _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1"))


async def test_play_finds_station_after_list_changed(hass, hass_ws_client, receiver, config_entry):
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    estonia = _children(await _browse(hass, hass_ws_client, "netradio_menu:root:Line_1:Line_2:Line_1"))
    # A station is added at the top of the Radio Browser list later on
    receiver.net_radio_tree[1][0][1][1][1][0][1].insert(0, ("Elmar", None))

    await _call(hass, "play_media", media_content_id=estonia["Vikerraadio"], media_content_type="channel")

    assert receiver.station == "Vikerraadio"


async def test_server_play_after_stop_selects_track_again(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)
    folder = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_1"))
    await _call(hass, "play_media", media_content_id=folder["Track 1.2"], media_content_type="music")
    # The receiver plays on to the next track of the folder
    receiver.song = "Track 1.3"
    await async_update_entity(hass, ENTITY_ID)

    await _call(hass, "media_pause")
    await _call(hass, "media_play")
    assert receiver.playback == "Play"

    await _call(hass, "media_stop")
    assert hass.states.get(ENTITY_ID).state == "idle"
    # Browsing a list not read before moves the receiver's menu
    await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_2")
    await _call(hass, "media_play")

    assert (receiver.playback, receiver.song) == ("Play", "Track 1.3")
    assert hass.states.get(ENTITY_ID).state == "playing"


async def test_server_play_right_after_stop(hass, hass_ws_client, receiver, config_entry):
    """The receiver may still report playing when polled right after Stop."""
    await setup_entry(hass, config_entry)
    folder = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_1"))
    await _call(hass, "play_media", media_content_id=folder["Track 1.2"], media_content_type="music")
    receiver.playback, receiver.song = "Stop", ""
    assert hass.states.get(ENTITY_ID).state == "playing"

    await _call(hass, "media_play")

    assert (receiver.playback, receiver.song) == ("Play", "Track 1.2")


async def test_server_play_after_stop_of_track_started_on_receiver(hass, receiver, config_entry):
    tree = receiver.server_tree
    ketas = tree[1][0]
    music = ketas[1][0]
    receiver.lists["SERVER"] = [(tree, 1), (ketas, 1), (music, 1), (music[1][1], 4)]
    receiver.song = "Track 2.4"
    await setup_entry(hass, config_entry)

    await _call(hass, "media_stop")
    await _call(hass, "media_play")

    assert (receiver.playback, receiver.song) == ("Play", "Track 2.4")


async def test_server_play_track_on_page_two(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)

    folder = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_1"))

    await _call(hass, "play_media", media_content_id=folder["Track 1.10"], media_content_type="music")

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


async def test_entity_area_moved_to_device(hass, receiver, config_entry):
    area = ar.async_get(hass).async_create("Arvutituba")
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "media_player", DOMAIN, f"yamaha_rn301_{HOST.replace('.', '_')}",
        config_entry=config_entry, suggested_object_id="elutuba_yamaha")
    registry.async_update_entity(old.entity_id, area_id=area.id)

    await setup_entry(hass, config_entry)

    entity = registry.async_get(old.entity_id)
    assert entity.area_id is None
    assert dr.async_get(hass).async_get(entity.device_id).area_id == area.id
    assert not [i for i in ir.async_get(hass).issues.values()
                if i.translation_key == "entity_own_area_without_own_name"]


async def test_entity_area_kept_when_device_in_other_area(hass, receiver, config_entry):
    areas = ar.async_get(hass)
    room, other = areas.async_create("Arvutituba"), areas.async_create("Elutuba")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, config_entry.entry_id)})
    dr.async_get(hass).async_update_device(device.id, area_id=other.id)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "media_player", DOMAIN, f"yamaha_rn301_{HOST.replace('.', '_')}",
        config_entry=config_entry, suggested_object_id="elutuba_yamaha")
    registry.async_update_entity(old.entity_id, area_id=room.id)

    await setup_entry(hass, config_entry)

    # Conflicting areas are left for the user to resolve
    assert registry.async_get(old.entity_id).area_id == room.id
    assert dr.async_get(hass).async_get(device.id).area_id == other.id


async def test_server_play_stored_track_from_other_menu(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)
    track_id = _children(await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_1"))["Track 1.10"]
    # Someone browses elsewhere before an automation plays the stored ID
    await _browse(hass, hass_ws_client, "server_menu:root:Line_1:Line_1:Line_10")

    await _call(hass, "play_media", media_content_id=track_id, media_content_type="music")

    assert receiver.song == "Track 1.10"


async def test_net_radio_browse(hass, hass_ws_client, receiver, config_entry):
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    # YCast pages take a moment to load after each jump or selection, and
    # right after a jump the receiver may still report the old page as ready
    receiver.busy_polls = 2
    receiver.jump_lag_polls = 1
    # The receiver is left deep in a station list
    receiver.lists["NET_RADIO"].append((NET_RADIO_TREE[1][0], 1))

    root = await _browse(hass, hass_ws_client)
    assert root["result"]["title"] == "NET RADIO"
    assert list(_children(root)) == ["Radiobrowser", "My Stations"]

    radiobrowser = _children(await _browse(hass, hass_ws_client, _children(root)["Radiobrowser"]))
    genres = _children(await _browse(hass, hass_ws_client, radiobrowser["Genres"]))
    assert list(genres) == [f"Genre {i}" for i in range(1, 12)]
    genre = await _browse(hass, hass_ws_client, genres["Genre 10"])

    assert genre["result"]["title"] == "Genre 10"
    station = genre["result"]["children"][0]
    assert (station["title"], station["media_class"], station["can_play"]) == ("Station 10.1", "channel", True)
    # Shown as a list of stations; moving up is the media browser's own back button
    assert genre["result"]["children_media_class"] == "channel"


async def test_net_radio_play_station(hass, hass_ws_client, receiver, config_entry):
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    estonia = _children(await _browse(hass, hass_ws_client, "netradio_menu:root:Line_1:Line_2:Line_1"))

    await _call(hass, "play_media", media_content_id=estonia["Raadio 2"], media_content_type="channel")

    assert receiver.station == "Raadio 2"
    attributes = hass.states.get(ENTITY_ID).attributes
    assert (attributes["media_channel"], attributes["media_title"]) == ("Raadio 2", "Artist - Song")


async def test_net_radio_play_stored_station(hass, receiver, config_entry):
    """An automation plays a station ID saved earlier, with the menu elsewhere."""
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    receiver.busy_polls = 2
    receiver.jump_lag_polls = 1

    await _call(hass, "play_media", media_content_id="netradio_track:root:Line_1:Line_2:Line_1:Line_2",
                media_content_type="channel")

    assert receiver.station == "Vikerraadio"


async def test_browse_in_standby_shows_error(hass, hass_ws_client, receiver, config_entry):
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    root = _children(await _browse(hass, hass_ws_client))
    receiver.power = "Standby"

    response = await _browse(hass, hass_ws_client, root["Radiobrowser"])

    assert not response["success"]
    assert response["error"]["message"] == "The receiver is in standby"


async def test_browse_not_supported_for_passive_input(hass, hass_ws_client, receiver, config_entry):
    receiver.input = "OPTICAL"
    await setup_entry(hass, config_entry)

    response = await _browse(hass, hass_ws_client)

    assert not response["success"]


async def test_net_radio_single_folder_is_skipped(hass, hass_ws_client, receiver, config_entry):
    """YCast puts bookmarks in a single "Bookmarks" category under My Stations."""
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    root = _children(await _browse(hass, hass_ws_client))

    my_stations = await _browse(hass, hass_ws_client, root["My Stations"])

    assert my_stations["result"]["title"] == "My Stations"
    assert my_stations["result"]["media_content_id"] == root["My Stations"]
    stations = _children(my_stations)
    assert list(stations) == ["Sky Plus", "Raadio 2"]

    await _call(hass, "play_media", media_content_id=stations["Raadio 2"], media_content_type="channel")
    assert receiver.station == "Raadio 2"


async def test_server_single_server_is_skipped(hass, hass_ws_client, receiver, config_entry):
    await setup_entry(hass, config_entry)

    root = await _browse(hass, hass_ws_client)

    # Media Server holds only "ketas", which holds only "Music": both are skipped
    assert root["result"]["title"] == "Media Server"
    assert list(_children(root))[:2] == ["Folder 1", "Folder 2"]


async def test_ignored_jump_is_sent_again(hass, hass_ws_client, receiver, config_entry, monkeypatch):
    monkeypatch.setattr("custom_components.yamaha_rn301.media_player.LIST_JUMP_RESEND", 0.3)
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    receiver.ignore_jumps = 1

    genres = _children(await _browse(hass, hass_ws_client, "netradio_menu:root:Line_1:Line_1"))

    assert list(genres) == [f"Genre {i}" for i in range(1, 12)]


async def test_opening_a_subfolder_steps_down(hass, hass_ws_client, receiver, config_entry):
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    genres = _children(await _browse(hass, hass_ws_client, "netradio_menu:root:Line_1:Line_1"))
    receiver.puts.clear()

    genre = await _browse(hass, hass_ws_client, genres["Genre 10"])

    assert genre["result"]["title"] == "Genre 10"
    # Selected in the list shown, without walking from the root again
    assert not [put for put in receiver.puts if "Return" in put]


async def test_opening_a_subfolder_while_parent_is_read_steps_down(hass, hass_ws_client, receiver, config_entry, monkeypatch):
    monkeypatch.setattr("custom_components.yamaha_rn301.media_player.LIST_FIRST_VIEW_BUDGET", 0)
    receiver.input = "NET RADIO"
    await setup_entry(hass, config_entry)
    receiver.busy_polls = 2
    # The rest of Genres is being read in the background
    genres = _children(await _browse(hass, hass_ws_client, "netradio_menu:root:Line_1:Line_1"))
    receiver.puts.clear()

    genre = await _browse(hass, hass_ws_client, genres["Genre 3"])

    assert genre["result"]["title"] == "Genre 3"
    assert not [put for put in receiver.puts if "Return" in put]
