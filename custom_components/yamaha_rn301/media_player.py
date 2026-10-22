import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime

from typing import NamedTuple, Optional
from urllib.parse import quote, unquote
import asyncio
import time

import voluptuous as vol
import aiohttp

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA, BrowseMedia, MediaPlayerDeviceClass, MediaPlayerEntity, MediaPlayerEntityFeature,
    MediaPlayerState, RepeatMode)
from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.exceptions import HomeAssistantError

import homeassistant.util.dt as dt_util
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.storage import Store

from .api import async_get_system_info
from .const import DOMAIN, DEFAULT_NAME, DEFAULT_TIMEOUT

BASE_URL = 'http://{0}/YamahaRemoteControl/ctrl'
# Consecutive failed polls before the entity is reported unavailable; the
# receiver occasionally misses a poll in standby
MAX_FAILED_UPDATES = 3
# The receiver refuses commands with RC="4" in standby and for about half a
# second after turning on: commands refused within this many seconds of
# turning it on are sent again
POWER_ON_DELAY = 3
# The Tuner ignores preset selections (with RC="0") for about 0.7 seconds
# after the input is selected
TUNER_START_DELAY = 1
# The receiver may still report the old state for about 0.1 seconds after
# taking Play, Pause or Stop: seconds to wait for it to report the new state
PLAYBACK_WAIT = 1
# Why the receiver refuses a command, by its RC code
RC_ERRORS = {
    '3': "The receiver does not accept this value",
    '4': "The receiver is in standby",
}
# Polling while a NET RADIO or SERVER list is busy loading; a page takes
# about half a second, a media server waking up several seconds
LIST_BUSY_POLL_INTERVAL = 0.15
LIST_BUSY_TIMEOUT = 10
# Seconds before a Jump_Line the receiver did not act on is sent again
LIST_JUMP_RESEND = 2
# Seconds spent reading a list that was never read before showing what was
# read so far; a page of 8 takes 0.5-1 s
LIST_FIRST_VIEW_BUDGET = 2
# Lists read longer ago than this are read again in the background when
# opened, so the next view is current
LIST_REFRESH_AGE = 600
# Lists read longer ago than this are dropped from storage
LIST_STORAGE_MAX_AGE = 30 * 24 * 3600

_BASE_FEATURES = MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.VOLUME_STEP | \
                 MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF | MediaPlayerEntityFeature.SELECT_SOURCE

SUPPORT_YAMAHA = _BASE_FEATURES | MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.STOP | \
                 MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK

SUPPORTED_PLAYBACK = _BASE_FEATURES

SUPPORT_TUNER = _BASE_FEATURES | MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK

SUPPORT_NET_RADIO = _BASE_FEATURES | MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.BROWSE_MEDIA

SUPPORT_SERVER = _BASE_FEATURES | MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.BROWSE_MEDIA | \
                 MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.STOP | \
                 MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK | MediaPlayerEntityFeature.SHUFFLE_SET | \
                 MediaPlayerEntityFeature.REPEAT_SET

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string
})
SOURCE_MAPPING = {
    'AirPlay': 'AirPlay',
    'Optical': 'OPTICAL',
    'Coaxial': 'COAXIAL',
    'CD': 'CD',
    'Spotify': 'Spotify',
    'Line 1': 'LINE1',
    'Line 2': 'LINE2',
    'Line 3': 'LINE3',
    'Net Radio': 'NET RADIO',
    'Server': 'SERVER',
    'Tuner': 'TUNER'
}


class ListSource(NamedTuple):
    """An input whose menu is browsed through the List_Info/List_Control API."""

    tag: str
    prefix: str  # for media content IDs
    item_class: str
    item_type: str
    empty_title: str


LIST_SOURCES = {
    'Server': ListSource('SERVER', 'server', MediaClass.TRACK, MediaType.MUSIC, 'No servers available'),
    'Net Radio': ListSource('NET_RADIO', 'netradio', MediaClass.CHANNEL, MediaType.CHANNEL, 'No stations available'),
}

def _path_part(item):
    """Media ID part for a list item: its line number and, to find it again
    after the list changed, its name."""
    return f"{item['line_id']}~{quote(item['title'], safe='')}"


def _fix_encoding(text):
    """Undo UTF-8 text read as Latin-1, e.g. "PÃ¤ev" for "Päev".

    The receiver does this to the song titles NET RADIO stations send. Text
    that is not such a mix-up, such as a correct "ä", is returned as is.
    """
    try:
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _split_part(part):
    """Line number and name of a media ID part; IDs from before 1.5.2 have no name."""
    line_id, _, title = part.partition("~")
    return int(line_id[5:]), unquote(title) if title else None


REPEAT_MAPPING = {
    RepeatMode.OFF: 'Off',
    RepeatMode.ONE: 'One',
    RepeatMode.ALL: 'All',
}

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the media player platform from YAML."""
    async_add_entities([YamahaRn301MP(config.get(CONF_NAME), config.get(CONF_HOST), serial=None, version=None)], True)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the media player platform from a config entry."""
    host = entry.data[CONF_HOST]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    serial, version = await async_get_system_info(hass, host)
    player = YamahaRn301MP(name, host, entry.entry_id, serial, version)
    async_add_entities([player], True)

class YamahaRn301MP(MediaPlayerEntity):

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_has_entity_name = True
    _attr_name = None
    # Two steps on the receiver's 0-100 volume scale
    _attr_volume_step = 0.02

    def __init__(self, name, host, unique_id=None, serial=None, version=None):
        self._host = host
        # Config entries pass the entry ID so the entity survives a host change;
        # YAML setups have no entry and keep the host-based ID.
        self._unique_id = unique_id or f"yamaha_rn301_{host.replace('.', '_')}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._unique_id)},
            manufacturer="Yamaha",
            model="R-N301",
            name=name,
            serial_number=serial or None,
            sw_version=version,
            configuration_url=f"http://{host}/",
        )
        self._base_url = BASE_URL.format(self._host)
        self._pwstate = None
        self._volume = 0
        self._muted = False
        self._source = None
        self._device_source = None
        self._source_list = list(SOURCE_MAPPING.keys())
        self._reverse_mapping = {val: key for key, val in SOURCE_MAPPING.items()}

        self._media_meta = {}
        self._media_playing = False
        self._media_play_position = None
        self._media_play_position_updated = None
        self._media_play_shuffle = None
        self._media_play_repeat = None
        self._session = None
        self._current_preset = None
        self._failed_updates = 0
        # time.monotonic() when the receiver was last turned on, and when an
        # input was last selected
        self._turned_on_at = None
        self._selected_at = None
        # The Server track playing last, and the folders tracks were played
        # from in Home Assistant per list source tag, to select it again after Stop
        self._last_song = None
        self._played_from = {}
        # (menu path, menu name) of the list the receiver shows, per list source tag
        self._list_paths = {}
        # Lists read for browsing: "tag|path" -> {'time': ..., 'listing': ...}
        self._list_cache = {}
        self._list_store = None
        # The receiver has one menu position per input: one list operation at a time
        self._list_lock = asyncio.Lock()
        # (cache key, task) of the list being read in the background
        self._list_task = None

    async def async_will_remove_from_hass(self) -> None:
        await self._cancel_list_task()
        if self._list_store is not None:
            await self._list_store.async_save(self._list_cache)

    async def async_added_to_hass(self) -> None:
        """Load the browsing lists kept from before, and move an area set on the entity to its device.

        Before 1.5.0 there was no device, so an area could only be set on the
        entity. The entity now represents the device (it has no name of its
        own), and Home Assistant reports an area on such an entity as an issue.
        """
        await super().async_added_to_hass()
        self._list_store = Store(self.hass, 1, f"{DOMAIN}.{self._unique_id}.lists")
        stored = await self._list_store.async_load() or {}
        self._list_cache = {key: entry for key, entry in stored.items()
                            if time.time() - entry['time'] < LIST_STORAGE_MAX_AGE}

        entity_registry = er.async_get(self.hass)
        entry = entity_registry.async_get(self.entity_id)
        if entry is None or entry.area_id is None or entry.device_id is None:
            return
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get(entry.device_id)
        # Leave it to the user when the device is already in another area
        if device is None or device.area_id not in (None, entry.area_id):
            return
        device_registry.async_update_device(device.id, area_id=entry.area_id)
        entity_registry.async_update_entity(self.entity_id, area_id=None)

    async def async_update(self) -> None:
        data = await self._do_api_get("<Main_Zone><Basic_Status>GetParam</Basic_Status></Main_Zone>")
        if not data:
            self._failed_updates += 1
            # Before the first successful update there is no state to keep
            if self._attr_available and (
                    self._failed_updates >= MAX_FAILED_UPDATES or self._pwstate is None):
                _LOGGER.warning("Yamaha R-N301 at %s is unreachable", self._host)
                self._attr_available = False
            return
        if not self._attr_available:
            _LOGGER.info("Yamaha R-N301 at %s is reachable again", self._host)
        self._attr_available = True
        self._failed_updates = 0
        try:
            tree = ET.fromstring(data)
            for node in tree[0][0]:
                if node.tag == "Power_Control":
                    self._pwstate = MediaPlayerState.IDLE if (node[0].text) == "On" else MediaPlayerState.OFF
                elif node.tag == "Volume":
                    for voln in node:
                        if voln.tag == "Lvl":
                            self._volume = int(voln.find("Val").text) / 100
                        elif voln.tag == "Mute":
                            self._muted = voln.text == "On"
                elif node.tag == "Input":
                    txt = node.find("Input_Sel").text
                    self._source = self._reverse_mapping.get(txt, txt)
                    self._device_source = txt.replace(" ", "_")
            if self._pwstate != MediaPlayerState.OFF:
                await self._update_media_playing()
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response: %s", e)
        except Exception as e:
            _LOGGER.error("Error during update: %s", e)

    @property
    def state(self):
        return self._pwstate

    @property
    def supported_features(self):
        if self._source == "Tuner":
            return SUPPORT_TUNER
        elif self._source == "Net Radio":
            return SUPPORT_NET_RADIO
        elif self._source == "Server":
            return SUPPORT_SERVER
        elif self._source in ("Optical", "Coaxial", "CD", "Line 1", "Line 2", "Line 3"):
            return SUPPORTED_PLAYBACK
        return SUPPORT_YAMAHA

    @property
    def volume_level(self):
        return self._volume

    @property
    def source(self):
        return self._source

    @property
    def source_list(self):
        return self._source_list

    @property
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def is_volume_muted(self) -> bool:
        return self._muted

    @property
    def media_position(self):
        """Duration of current playing media"""
        return self._media_play_position

    @property
    def media_position_updated_at(self):
        """Duration of current playing media"""
        return self._media_play_position_updated

    @property
    def media_title(self):
        """Title of currently playing track"""
        if self._source == "Tuner":
            freq = self._media_meta.get("frequency", "")
            station = self._media_meta.get("station", "")
            song = self._media_meta.get("song", "")
            
            if self._current_preset:
                title = f"#{self._current_preset}"
            else:
                title = "Tuner"
            
            if station:
                title += f" {station}"
            if song:
                title += f" • {song}"
            if freq:
                title += f" ({freq})"
            
            return title
        elif "song" in self._media_meta and "frequency" in self._media_meta:
            return self._media_meta["song"] if datetime.now().second < 20 else self._media_meta["frequency"]
        elif "song" in self._media_meta:
            return self._media_meta.get("song")
        elif "frequency" in self._media_meta:
            return self._media_meta.get("frequency")
        # NET RADIO stations that send no song information
        return self._media_meta.get("station")

    @property
    def media_channel(self):
        """Station of the playing NET RADIO stream"""
        if self._source == "Tuner":
            return None
        return self._media_meta.get("station")

    @property
    def media_album_name(self):
        """Album of currently playing track"""
        return self._media_meta.get('album')

    @property
    def media_artist(self) -> Optional[str]:
        """Artist of currently playing track"""
        return self._media_meta.get('artist')

    @property
    def media_content_type(self):
        if self._source == "Net Radio" or self._source == "Tuner":
            return MediaType.CHANNEL
        return MediaType.MUSIC

    @property
    def shuffle(self):
        return self._media_play_shuffle

    async def async_set_shuffle(self, shuffle):
        await self._do_api_put(
            '<{0}><Play_Control><Play_Mode><Shuffle>{1}</Shuffle></Play_Mode></Play_Control></{0}>'.format(
                self._device_source, 'On' if shuffle else 'Off'))

    @property
    def repeat(self):
        return self._media_play_repeat

    async def async_set_repeat(self, repeat):
        await self._do_api_put(
            '<{0}><Play_Control><Play_Mode><Repeat>{1}</Repeat></Play_Mode></Play_Control></{0}>'.format(
                self._device_source, REPEAT_MAPPING[repeat]))

    async def async_turn_on(self):
        """Turn on the amplifier"""
        await self._set_power_state(True)

    async def async_turn_off(self):
        """Turn off the amplifier"""
        await self._set_power_state(False)

    async def async_set_volume_level(self, volume):
        # The receiver refuses values outside 0-100
        value = max(0, min(100, round(volume * 100)))
        await self._do_api_put(
            '<Main_Zone><Volume><Lvl><Val>{0}</Val><Exp>0</Exp><Unit></Unit></Lvl></Volume></Main_Zone>'.format(
                value))

    async def async_select_source(self, source):
        input_sel = SOURCE_MAPPING.get(source, source)
        await self._do_api_put('<Main_Zone><Input><Input_Sel>{0}</Input_Sel></Input></Main_Zone>'.format(input_sel))
        # Set at once: Home Assistant skips the refresh after this call while a
        # poll that may have read the old input is running
        self._source = self._reverse_mapping.get(input_sel, input_sel)
        self._device_source = input_sel.replace(" ", "_")
        self._selected_at = time.monotonic()

    async def async_mute_volume(self, mute):
        await self._do_api_put('<Main_Zone><Volume><Mute>{0}</Mute></Volume></Main_Zone>'.format('On' if mute else 'Off'))
        self._muted = mute

    async def _media_play_control(self, command):
        await self._do_api_put(
            '<{0}><Play_Control><Playback>{1}</Playback></Play_Control></{0}>'.format(self._device_source, command))
        if command in ("Play", "Pause", "Stop"):
            # So the state refreshed after this call, and Play right after
            # Stop, see the new state
            deadline = time.monotonic() + PLAYBACK_WAIT
            while f"<Playback_Info>{command}<" not in await self._do_api_get(
                    f"<{self._device_source}><Play_Info>GetParam</Play_Info></{self._device_source}>"):
                if time.monotonic() >= deadline:
                    break
                await asyncio.sleep(0.1)

    async def async_media_play(self):
        """Play media"""
        if self._source == "Server" and self._last_song and "<Playback_Info>Stop<" in await self._do_api_get(
                "<SERVER><Play_Info>GetParam</Play_Info></SERVER>"):
            # After Stop the receiver ignores Play: select the track again.
            # Asked from the receiver, as the state polled right after Stop
            # may still be playing
            await self._play_last_track(LIST_SOURCES["Server"])
            return
        await self._media_play_control("Play")

    async def async_media_pause(self):
        """Pause media"""
        await self._media_play_control("Pause")

    async def async_media_stop(self):
        """Stop media"""
        await self._media_play_control("Stop")

    async def async_media_next_track(self):
        if self._source == "Tuner":
            await self._step_preset(1)
        else:
            await self._media_play_control("Skip Fwd")

    async def async_media_previous_track(self):
        if self._source == "Tuner":
            await self._step_preset(-1)
        else:
            await self._media_play_control("Skip Rev")

    async def async_play_media(self, media_type, media_id, **kwargs):
        """Play media - for TUNER presets, NET RADIO stations, and SERVER tracks"""
        src = LIST_SOURCES.get(self._source)
        if self._source == "Tuner" and media_type == "preset":
            await self._select_preset(media_id)
        elif src is not None and media_id.startswith(f"{src.prefix}_track:"):
            # Navigate to the station or track and play it
            await self._navigate_and_play(src, media_id)
        elif media_type == "info":
            # Ignore info type media (like "No servers available", page info, etc.)
            return
        else:
            _LOGGER.warning("Play media not supported for source %s with type %s", self._source, media_type)

    async def _set_power_state(self, on):
        await self._do_api_put(
            '<System><Power_Control><Power>{0}</Power></Power_Control></System>'.format("On" if on else "Standby"))
        if on:
            self._turned_on_at = time.monotonic()

    async def _post(self, data):
        """Send a request and return the HTTP status and the response text."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        data = '<?xml version="1.0" encoding="utf-8"?>' + data
        async with self._session.post(self._base_url, data=data, timeout=timeout) as req:
            return req.status, await req.text()

    async def _do_api_request(self, data) -> str:
        try:
            status, text = await self._post(data)
            if status != 200:
                _LOGGER.warning("Error doing API request, %d, %s", status, data)
            return text
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # Logged at debug level: async_update reports the receiver going
            # offline once instead of on every poll.
            _LOGGER.debug("Request to %s failed: %r", self._host, e)
            return ""
        except Exception as e:
            _LOGGER.error("Unexpected error during API request: %s", e)
            return ""

    async def _do_api_get(self, data) -> str:
        request = '<YAMAHA_AV cmd="GET">' + data + '</YAMAHA_AV>'
        response = await self._do_api_request(request)
        return response

    async def _do_api_put(self, data) -> str:
        """Send a command, raising HomeAssistantError when the receiver does not carry it out."""
        data = '<YAMAHA_AV cmd="PUT">' + data + '</YAMAHA_AV>'
        while True:
            try:
                status, text = await self._post(data)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                raise HomeAssistantError(f"Cannot reach the receiver at {self._host}") from e
            # The receiver answers HTTP 200 with RC="0" when it takes a command,
            # also one it then ignores, such as a selection while a list loads
            rc = re.search(r'\bRC="(\d+)"', text)
            code = rc.group(1) if rc else None
            if status == 200 and code == '0':
                return text
            if (code == '4' and self._turned_on_at is not None
                    and time.monotonic() < self._turned_on_at + POWER_ON_DELAY):
                await asyncio.sleep(0.2)
                continue
            _LOGGER.debug("Receiver refused %s: HTTP %d, RC %s", data, status, code)
            if status != 200:
                # HTTP 400: the input has no such command, e.g. shuffle for Spotify
                raise HomeAssistantError("The receiver does not support this command")
            raise HomeAssistantError(RC_ERRORS.get(code, f"The receiver refused the command (RC {code})"))

    def _nullify_media_fields(self) -> None:
        """Set media fields to null as we don't require them on certain channels"""
        self._media_meta = {}
        self._media_playing = False
        self._pwstate = MediaPlayerState.IDLE if self._pwstate != MediaPlayerState.OFF else MediaPlayerState.OFF
        if self._source != "Tuner":
            self._current_preset = None

    def _set_playback_info(self, text: str) -> None:
        """Set the playback info from xml"""
        if text == "Play" or text == "Assert":
            self._pwstate = MediaPlayerState.PLAYING if self._pwstate != MediaPlayerState.OFF else MediaPlayerState.OFF
            self._media_playing = True
        elif text == "Pause":
            self._pwstate = MediaPlayerState.PAUSED if self._pwstate != MediaPlayerState.OFF else MediaPlayerState.OFF
            self._media_playing = True
        else:
            self._media_playing = False

    async def _update_media_playing(self):
        media_meta_mapping = {
            'Artist': 'artist',
            'Station': 'station',
            'Radio_Text_A': 'song',
            'Album': 'album',
            'Song': 'song',
            'Track': 'song',
            'Program_Service': 'station',
            'Program_Type': 'genre',
            'Radio_Text_B': 'description',
        }
        device_mapping = {
            "Spotify": "Spotify",
            "NET_RADIO": "NET_RADIO",
            "SERVER": "SERVER",
            "TUNER": "Tuner",
            "AirPlay": "AirPlay"
        }

        try:
            if self._device_source in device_mapping:
                data = await self._do_api_get(
                    "<{0}><Play_Info>GetParam</Play_Info></{0}>".format(device_mapping[self._device_source]))
                if not data:
                    return
                self._media_meta = {}
                tree = ET.fromstring(data)
                for node in tree[0][0]:
                    try:
                        if node.tag == "Play_Mode":
                            self._media_play_shuffle = node.findtext("Shuffle") == "On"
                            self._media_play_repeat = next(
                                (mode for mode, value in REPEAT_MAPPING.items()
                                 if value == node.findtext("Repeat")), None)
                        elif node.tag == "Play_Time":
                            self._media_play_position = int(node.text)
                            self._media_play_position_updated = dt_util.utcnow()
                        elif node.tag == "Meta_Info":
                            for meta in node:
                                if meta.tag in media_meta_mapping and meta.text:
                                    self._media_meta[media_meta_mapping[meta.tag]] = _fix_encoding(meta.text.replace('&amp;', '&'))
                        elif node.tag == "Playback_Info":
                            self._set_playback_info(node.text)
                        elif node.tag == "Signal_Info":
                            tuned_node = node.find("Tuned")
                            if tuned_node is not None:
                                if self._device_source == "TUNER":
                                    self._pwstate = MediaPlayerState.PLAYING if self._pwstate != MediaPlayerState.OFF else MediaPlayerState.OFF
                                    self._media_playing = True
                                else:
                                    self._set_playback_info(tuned_node.text)
                        elif node.tag == "Tuning":
                            band_node = node.find("Band")
                            freq_node = node.find("Freq")
                            if band_node is not None and freq_node is not None:
                                current = freq_node.find("Current")
                                if current is not None:
                                    val_node = current.find("Val")
                                    unit_node = current.find("Unit")
                                    if val_node is not None and unit_node is not None:
                                        val = float(val_node.text) / 100
                                        unit = unit_node.text
                                        self._media_meta["frequency"] = f"{band_node.text} {val} {unit}"
                        elif node.tag == "Preset":
                            preset_node = node.find("Preset_Sel")
                            if preset_node is not None:
                                self._current_preset = preset_node.text
                    except Exception as e:
                        _LOGGER.warning("Error parsing media node: %s", e)
                if self._device_source == "SERVER" and self._media_playing and self._media_meta.get('song'):
                    self._last_song = self._media_meta['song']

            else:
                self._nullify_media_fields()
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in media update: %s", e)
        except Exception as e:
            _LOGGER.exception("Error updating media info: %s", e)

    async def _step_preset(self, step):
        """Select the next (step 1) or previous (step -1) stored Tuner preset."""
        # The preset is read from the receiver too: the polled one may be
        # old, e.g. right after switching to the Tuner
        try:
            items = ET.fromstring(await self._do_api_get(
                '<Tuner><Play_Control><Preset><Preset_Sel_Item>GetParam</Preset_Sel_Item></Preset></Play_Control></Tuner>'
            )).find('Tuner/Play_Control/Preset/Preset_Sel_Item')
            current = ET.fromstring(await self._do_api_get(
                '<Tuner><Play_Info>GetParam</Play_Info></Tuner>')).findtext('Tuner/Play_Info/Preset/Preset_Sel')
        except ET.ParseError as e:
            raise HomeAssistantError(f"Cannot read the presets from the receiver at {self._host}") from e
        # The first item, "No Preset", is read-only; the others are the stored presets
        presets = [item.findtext('Param') for item in items if item.findtext('RW') == 'RW'] if items is not None else []
        if not presets:
            raise HomeAssistantError("The receiver has no Tuner presets stored")
        if current in presets:
            preset = presets[(presets.index(current) + step) % len(presets)]
        else:
            preset = presets[0 if step > 0 else -1]
        await self._select_preset(preset)

    async def _select_preset(self, preset):
        if self._selected_at is not None:
            # The Tuner may have been selected a moment ago
            await asyncio.sleep(self._selected_at + TUNER_START_DELAY - time.monotonic())
        await self._do_api_put(f'<Tuner><Play_Control><Preset><Preset_Sel>{preset}</Preset_Sel></Preset></Play_Control></Tuner>')
        self._current_preset = preset

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Browse the NET RADIO and SERVER menus"""
        src = LIST_SOURCES.get(self._source)
        if src is None:
            raise BrowseError(f"Browsing is not supported for source {self._source}")
        try:
            if media_content_id is None or media_content_id == f"{src.prefix}_root":
                return await self._browse_list(src, f"{src.prefix}_root")
            if media_content_id.startswith(f"{src.prefix}_all:"):
                return await self._browse_list(src, media_content_id.split(":", 1)[1], show_all=True)
            if media_content_id.startswith(f"{src.prefix}_menu:root:"):
                return await self._browse_list(src, media_content_id)
            raise BrowseError(f"Unknown media ID {media_content_id}")
        except BrowseError:
            raise
        except HomeAssistantError as e:
            # Such as the receiver being in standby: shown in the media browser
            raise BrowseError(str(e)) from e
        except Exception as e:
            _LOGGER.exception("Error browsing %s media: %s", src.tag, e)
            raise BrowseError(f"Browsing {self._source} failed") from e

    async def _browse_list(self, src, menu_id, show_all=False):
        """Browse a NET RADIO or SERVER folder as one continuous list.

        The receiver shows 8 lines at a time and takes 0.5-1 s per page, and
        the media browser cannot load a list bit by bit. So a list that was
        never read shows what could be read in LIST_FIRST_VIEW_BUDGET seconds,
        the rest is read in the background, and "Show all" shows it whole.
        Lists are kept, also across restarts, so they open at once next time;
        old ones are read again in the background. Moving up is left to the
        media browser's own back navigation.
        """
        path = menu_id.split(":")[2:]
        key = f"{src.tag}|{':'.join(path)}"
        if show_all and self._list_task and self._list_task[0] == key:
            # The rest of this list is being read: wait for it
            await asyncio.wait([self._list_task[1]])
        await self._cancel_list_task()

        entry = self._list_cache.get(key)
        if entry is None or (show_all and not entry['listing']['complete']):
            async with self._list_lock:
                await self._show_list(src, path)
                listing = await self._read_list(
                    src, entry['listing'] if entry else None, None if show_all else LIST_FIRST_VIEW_BUDGET)
            entry = self._store_list(key, listing)
        listing = entry['listing']

        # Skip a level that holds nothing but one folder, such as YCast's
        # "My Stations" with its single "Bookmarks" category, or a media
        # server list with one server
        items = listing['items']
        if listing['complete'] and len(items) == 1 and items[0]['attribute'] == "Container":
            only = await self._browse_list(src, f"{src.prefix}_menu:root:{':'.join(path + [_path_part(items[0])])}")
            only.media_content_id = menu_id
            only.title = listing['menu_name'] or only.title
            return only

        children = self._create_browse_media_children(src, items, path, listing['menu_layer'])
        if not children and listing['complete'] and listing['menu_layer'] == 1:
            children.append(BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id="empty",
                media_content_type="info",
                title=src.empty_title,
                can_play=False,
                can_expand=False,
            ))
        if not listing['complete']:
            children.append(BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id=f"{src.prefix}_all:{menu_id}",
                media_content_type="folder",
                title=f"⬇️ Show all {listing['max_line']}",
                can_play=False,
                can_expand=True,
            ))

        result = BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=f"{src.prefix}_all:{menu_id}" if show_all else menu_id,
            media_content_type="folder",
            title=listing['menu_name'] or self._source,
            can_play=False,
            can_expand=True,
            children=children,
        )
        # Started last: the task may run eagerly up to its first wait
        if not listing['complete'] or time.time() - entry['time'] > LIST_REFRESH_AGE:
            self._start_list_task(src, key, path)
        return result

    async def _read_list(self, src, listing=None, budget=None):
        """Read the list the receiver shows, continuing listing if it was read in part.

        Stops after budget seconds, or at the end when budget is None. The
        listing is updated page by page, so a read that is cancelled keeps
        what it read.
        """
        parsed = self._parse_list_info(await self._wait_for_list(src))
        if listing is None or listing['max_line'] != parsed['max_line']:
            listing = {
                'menu_name': parsed['menu_name'],
                'menu_layer': parsed['menu_layer'],
                'max_line': parsed['max_line'],
                'items': [],
                'next_line': 1,
                'complete': False,
            }
        deadline = None if budget is None else time.monotonic() + budget
        line = listing['next_line']
        while line <= parsed['max_line']:
            if deadline is not None and listing['items'] and time.monotonic() >= deadline:
                break
            shown_start = (parsed['current_line'] - 1) // 8 * 8 + 1
            if not shown_start <= line < shown_start + 8:
                parsed = await self._jump_to_line(src, line)
                continue
            listing['items'].extend(item for item in parsed['items'] if int(item['line_id'][5:]) >= line)
            line = shown_start + 8
            listing['next_line'] = line
        listing['complete'] = line > parsed['max_line']
        return listing

    def _store_list(self, key, listing):
        """Keep a listing for browsing and save it for after a restart."""
        entry = self._list_cache[key] = {'time': time.time(), 'listing': listing}
        if self._list_store is not None:
            self._list_store.async_delay_save(lambda: self._list_cache, 10)
        return entry

    def _start_list_task(self, src, key, path):
        """Read the rest of a list, or all of an old one, in the background."""
        self._list_task = (key, self.hass.async_create_background_task(
            self._read_list_in_background(src, key, path), f"{DOMAIN} read {key}"))

    async def _read_list_in_background(self, src, key, path):
        entry = self._list_cache[key]
        moving = True
        try:
            async with self._list_lock:
                await self._show_list(src, path)
                # From here on the receiver stays in this list, only its page changes
                moving = False
                if entry['listing']['complete']:
                    # Read an old list again; it is shown until the new one is done
                    listing = await self._read_list(src)
                else:
                    listing = await self._read_list(src, entry['listing'])
            self._store_list(key, listing)
        except asyncio.CancelledError:
            if moving:
                # The receiver may have stopped anywhere on the way
                self._list_paths.pop(src.tag, None)
            if self._list_store is not None:
                self._list_store.async_delay_save(lambda: self._list_cache, 10)
            raise
        except HomeAssistantError as err:
            _LOGGER.debug("Reading %s in the background failed: %s", key, err)

    async def _cancel_list_task(self):
        """Stop a background read; the receiver's menu is needed for something else."""
        if self._list_task is not None:
            task = self._list_task[1]
            self._list_task = None
            task.cancel()
            await asyncio.wait([task])

    async def _show_list(self, src, path):
        """Make the receiver show the list at path, walking there from the root if needed."""
        parsed = self._parse_list_info(await self._wait_for_list(src))
        shown = self._list_paths.get(src.tag)
        # Walking the menu from the root is slow, so skip it when the list
        # shown is the one browsed last (e.g. right after browsing in the UI),
        # or step down when it is the parent (opening a folder in it)
        if shown == (path, parsed['menu_name']) and parsed['menu_layer'] == len(path) + 1:
            pass
        elif path and shown == (path[:-1], parsed['menu_name']) and parsed['menu_layer'] == len(path):
            await self._select_list_line(src, path[-1])
            await asyncio.sleep(0.5)
            parsed = self._parse_list_info(await self._wait_for_list(src))
        else:
            parsed = self._parse_list_info(await self._navigate_to_list_path(src, path))
        self._list_paths[src.tag] = (path, parsed['menu_name'])

    async def _navigate_and_play(self, src, media_id):
        """Navigate to and play a NET RADIO station or SERVER track"""
        parts = media_id.split(":")
        if len(parts) < 3 or not parts[-1].startswith("Line_"):
            _LOGGER.warning("Could not extract line_id from %s", media_id)
            return

        await self._cancel_list_task()
        async with self._list_lock:
            # A stored media ID played from an automation may find the
            # receiver showing another list
            await self._show_list(src, parts[2:-1])
            await self._select_list_line(src, parts[-1])
            await asyncio.sleep(0.2)

            # Start playing
            await self._do_api_put(f'<{src.tag}><Play_Control><Playback>Play</Playback></Play_Control></{src.tag}>')
        self._played_from[src.tag] = parts[2:-1]

    async def _play_last_track(self, src):
        """Select the track that played last again, as the receiver ignores Play after Stop."""
        title = self._last_song
        folder = self._played_from.get(src.tag)
        # Tracks play on through their folder, so the track is in the folder
        # played from in Home Assistant, if that list was read whole
        entry = self._list_cache.get(f"{src.tag}|{':'.join(folder)}") if folder is not None else None
        line = next((int(item['line_id'][5:]) for item in entry['listing']['items']
                     if item['title'] == title), None) if entry else None
        await self._cancel_list_task()
        async with self._list_lock:
            if line is not None:
                await self._show_list(src, folder)
            else:
                # Played from the receiver: its menu still shows the folder
                # the track was selected in, unless it was moved since
                line = self._parse_list_info(await self._wait_for_list(src))['current_line']
            # Selecting a track starts playing it
            await self._select_list_line(src, f"Line_{line}~{quote(title, safe='')}")

    def _parse_list_info(self, data):
        """Parse a List_Info response"""
        tree = ET.fromstring(data)
        menu_name = None
        menu_layer = 1
        current_line = 1
        max_line = 1
        items = []

        for node in tree[0][0]:
            if node.tag == "Menu_Name":
                menu_name = node.text
            elif node.tag == "Menu_Layer":
                menu_layer = int(node.text) if node.text else 1
            elif node.tag == "Cursor_Position":
                for cursor_node in node:
                    if cursor_node.tag == "Current_Line":
                        current_line = int(cursor_node.text) if cursor_node.text else 1
                    elif cursor_node.tag == "Max_Line":
                        max_line = int(cursor_node.text) if cursor_node.text else 1
            elif node.tag == "Current_List":
                for line in node:
                    if line.tag.startswith("Line_"):
                        txt_node = line.find("Txt")
                        attr_node = line.find("Attribute")

                        if txt_node is not None and attr_node is not None and txt_node.text:
                            items.append({
                                'line_id': line.tag,
                                # The receiver escapes "&" twice ("&amp;amp;")
                                'title': html.unescape(txt_node.text),
                                'attribute': attr_node.text
                            })

        # Current_List holds one page of up to 8 lines, numbered Line_1..Line_8
        # on every page. Store absolute line numbers so the item can be
        # selected again from any page (see _select_list_line).
        page_start = (current_line - 1) // 8 * 8 + 1
        for item in items:
            item['line_id'] = f"Line_{page_start + int(item['line_id'][5:]) - 1}"

        return {
            'menu_name': menu_name,
            'menu_layer': menu_layer,
            'current_line': current_line,
            'max_line': max_line,
            'items': items
        }

    def _create_browse_media_children(self, src, items, base_path, menu_layer=1):
        """Create BrowseMedia children from parsed items"""
        children = []

        for item in items:
            path = ":".join(base_path + [_path_part(item)])
            if item['attribute'] == "Container":
                # Folder/Album - extend current path
                media_type = "album" if src.tag == "SERVER" and menu_layer > 4 else "folder"
                children.append(BrowseMedia(
                    title=item['title'],
                    # Use ALBUM for album-level containers, DIRECTORY for other folders
                    media_class=MediaClass.ALBUM if media_type == "album" else MediaClass.DIRECTORY,
                    media_content_id=f"{src.prefix}_menu:root:{path}",
                    media_content_type=media_type,
                    can_play=False,
                    can_expand=True,
                ))
            elif item['attribute'] == "Item":
                # Track or station
                children.append(BrowseMedia(
                    title=item['title'],
                    media_class=src.item_class,
                    media_content_id=f"{src.prefix}_track:root:{path}",
                    media_content_type=src.item_type,
                    can_play=True,
                    can_expand=False,
                ))

        return children

    async def _navigate_to_list_path(self, src, path_parts):
        """Navigate to a menu path from the root and return the list there"""
        # Always reset to root first to ensure consistency
        await self._reset_list_to_root(src)

        # Navigate through the path step by step, letting each list finish
        # loading before selecting the next step in it
        for step in path_parts:
            await self._select_list_line(src, step)
            await asyncio.sleep(0.5)
            await self._wait_for_list(src)

        return await self._wait_for_list(src)

    async def _select_list_line(self, src, part):
        """Select an item in the current list by a media ID part (line number and name)."""
        number, title = _split_part(part)
        # Direct_Sel only addresses the 8 lines of the page shown, so first
        # jump to the page that holds the item
        parsed = await self._jump_to_line(src, number)
        if title is not None and title not in (
                item['title'] for item in parsed['items'] if item['line_id'] == f"Line_{number}"):
            # The list changed since the media ID was made, e.g. stations were
            # added to a Radio Browser list: find the item by its name
            number = next((int(item['line_id'][5:]) for item in (await self._read_list(src))['items']
                           if item['title'] == title), None)
            if number is None:
                raise HomeAssistantError(f"{title} is no longer in the {self._source} list")
            await self._jump_to_line(src, number)
        await self._do_api_put(f'<{src.tag}><List_Control><Direct_Sel>Line_{(number - 1) % 8 + 1}</Direct_Sel></List_Control></{src.tag}>')

    async def _jump_to_line(self, src, line):
        """Show the page holding a line of the current list and return the list info."""
        # The receiver may still report the old page as ready right after the
        # jump, then is busy while it loads the new one (about half a second
        # for NET RADIO) and ignores selections until it is done. Now and then
        # it ignores the jump itself; it is absolute, so it is safe to resend.
        deadline = time.monotonic() + LIST_BUSY_TIMEOUT
        resend = 0
        while True:
            if time.monotonic() >= resend:
                await self._do_api_put(f'<{src.tag}><List_Control><Jump_Line>{line}</Jump_Line></List_Control></{src.tag}>')
                resend = time.monotonic() + LIST_JUMP_RESEND
            parsed = self._parse_list_info(await self._wait_for_list(src))
            shown_start = (parsed['current_line'] - 1) // 8 * 8 + 1
            if shown_start <= line < shown_start + 8:
                return parsed
            if time.monotonic() >= deadline:
                raise BrowseError(f"The receiver did not show line {line}, try again")
            await asyncio.sleep(LIST_BUSY_POLL_INTERVAL)

    async def _wait_for_list(self, src):
        """Return the current list once the receiver is no longer busy loading it."""
        deadline = time.monotonic() + LIST_BUSY_TIMEOUT
        while True:
            data = await self._do_api_get(f"<{src.tag}><List_Info>GetParam</List_Info></{src.tag}>")
            if data and 'Menu_Status>Busy<' not in data:
                return data
            if time.monotonic() >= deadline:
                raise BrowseError("The receiver did not respond, try again")
            await asyncio.sleep(LIST_BUSY_POLL_INTERVAL)

    async def _reset_list_to_root(self, src):
        """Return the menu to its root level"""
        data = await self._wait_for_list(src)
        menu_layer = self._parse_list_info(data)['menu_layer']
        # Bounded in case the receiver ignores Return
        for attempt in range(menu_layer - 1):
            await self._do_api_put(f'<{src.tag}><List_Control><Cursor>Return</Cursor></List_Control></{src.tag}>')
            data = await self._wait_for_list(src)
            if self._parse_list_info(data)['menu_layer'] == 1:
                break
