import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from typing import Optional

import voluptuous as vol
import aiohttp

from homeassistant.components.media_player import (
    MediaPlayerEntity, PLATFORM_SCHEMA)

from homeassistant.components.media_player.const import (
    MEDIA_TYPE_PLAYLIST, MEDIA_TYPE_CHANNEL)
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature)
from homeassistant.const import (
    CONF_HOST, CONF_NAME, STATE_OFF, STATE_IDLE, STATE_PLAYING, STATE_UNKNOWN)

import homeassistant.util.dt as dt_util
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

DOMAIN = 'yamaha_rn301'

ATTR_ENABLED = 'enabled'
ATTR_PORT = 'port'
DATA_YAMAHA = 'yamaha_known_receivers'
DEFAULT_NAME = 'Yamaha R-N301'
DEFAULT_TIMEOUT = 5
BASE_URL = 'http://{0}/YamahaRemoteControl/ctrl'

SERVICE_ENABLE_OUTPUT = 'yamaha_enable_output'
SUPPORT_YAMAHA = MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF | \
                 MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.STOP | \
                 MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK | MediaPlayerEntityFeature.SHUFFLE_SET

SUPPORTED_PLAYBACK = MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF | \
                     MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.SHUFFLE_SET

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string
})
SOURCE_MAPPING = {
    'Optical': 'OPTICAL',
    'CD': 'CD',
    'Spotify': 'Spotify',
    'Line 1': 'LINE1',
    'Line 2': 'LINE2',
    'Line 3': 'LINE3',
    'Net Radio': 'NET RADIO',
    'Server': 'SERVER',
    'Tuner': 'TUNER'
}

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_devices, discovery_info=None):
    devices = []
    device = YamahaRn301MP(config.get(CONF_NAME), config.get(CONF_HOST))
    devices.append(device)
    add_devices(devices)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the media player platform from a config entry."""
    host = entry.data[CONF_HOST]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    player = YamahaRn301MP(name, host)
    async_add_entities([player], True)


class YamahaRn301MP(MediaPlayerEntity):

    def __init__(self, name, host):
        self._data = None
        self._name = name
        self._host = host
        self._base_url = BASE_URL.format(self._host)
        self._pwstate = STATE_UNKNOWN
        self._volume = 0
        self._muted = False
        self._is_on = None
        self._current_state = -1
        self._current_operation = ''
        self._set_state = None
        self._source = None
        self._device_source = None
        self._source_list = list(SOURCE_MAPPING.keys())
        self._reverse_mapping = {val: key for key, val in SOURCE_MAPPING.items()}
        self._operation_list = ['On', 'Vol']

        self._media_meta = {}
        self._media_playing = False
        self._media_play_position = None
        self._media_play_position_updated = None
        self._media_play_shuffle = None
        self._media_play_repeat = None
        self._media_play_artist = None
        self._media_play_album = None
        self._media_play_song = None
        self._media_playback_state = None
        self._session = None
        _LOGGER.debug("YamahaRn301MP initialized")

    async def async_update(self) -> None:
        data = await self._do_api_get("<Main_Zone><Basic_Status>GetParam</Basic_Status></Main_Zone>")
        if not data:
            return
        try:
            tree = ET.fromstring(data)
            for node in tree[0][0]:
                if node.tag == "Power_Control":
                    self._pwstate = STATE_IDLE if (node[0].text) == "On" else STATE_OFF
                elif node.tag == "Volume":
                    for voln in node:
                        if voln.tag == "Lvl":
                            self._volume = int(voln.find("Val").text) / 50
                        elif voln.tag == "Mute":
                            self._muted = voln.text == "On"
                elif node.tag == "Input":
                    txt = node.find("Input_Sel").text
                    self._source = self._reverse_mapping[txt]
                    self._device_source = txt.replace(" ", "_")
            if self._pwstate != STATE_OFF:
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
        if self._source in ("Optical", "CD", "Line 1", "Line 2", "Line 3", "Tuner"):
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
    def name(self) -> str:
        return self._name

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
        if "song" in self._media_meta and "frequency" in self._media_meta:
            return self._media_meta["song"] if datetime.now().second < 20 else self._media_meta["frequency"]
        elif "song" in self._media_meta:
            return self._media_meta.get("song")
        elif "frequency" in self._media_meta:
            return self._media_meta.get("frequency")

    @property
    def media_album(self):
        """Album of currently playing track"""
        return self._media_meta.get('album')

    @property
    def media_artist(self) -> Optional[str]:
        """Artist of currently playing track"""
        return self._media_meta.get('artist')

    @property
    def media_content_type(self):
        if self._source == "Net Radio" or self._source == "Tuner":
            return MEDIA_TYPE_CHANNEL
        return MEDIA_TYPE_PLAYLIST

    @property
    def shuffle(self):
        return self._media_play_shuffle

    async def async_set_shuffle(self, shuffle):
        await self._media_play_control("Shuffle")

    async def async_turn_on(self):
        """Turn on the amplifier"""
        await self._set_power_state(True)

    async def async_turn_off(self):
        """Turn off the amplifier"""
        await self._set_power_state(False)

    async def async_set_volume_level(self, volume):
        await self._do_api_put(
            '<Main_Zone><Volume><Lvl><Val>{0}</Val><Exp>0</Exp><Unit></Unit></Lvl></Volume></Main_Zone>'.format(
                int(volume * 50)))

    async def async_select_source(self, source):
        await self._do_api_put(
            '<Main_Zone><Input><Input_Sel>{0}</Input_Sel></Input></Main_Zone>'.format(SOURCE_MAPPING[source]))

    async def async_mute_volume(self, mute):
        await self._do_api_put('<System><Volume><Mute>{0}</Mute></Volume></System>'.format('On' if mute else 'Off'))
        self._muted = mute

    async def _media_play_control(self, command):
        await self._do_api_put(
            '<{0}><Play_Control><Playback>{1}</Playback></Play_Control></{0}>'.format(self._device_source, command))

    async def async_media_play(self):
        """Play media"""
        await self._media_play_control("Play")

    async def async_media_pause(self):
        """Pause media"""
        await self._media_play_control("Pause")

    async def async_media_stop(self):
        """Stop media"""
        await self._media_play_control("Stop")

    async def async_media_next_track(self):
        await self._media_play_control("Skip Fwd")

    async def async_media_previous_track(self):
        await self._media_play_control("Skip Rev")

    async def _set_power_state(self, on):
        await self._do_api_put(
            '<System><Power_Control><Power>{0}</Power></Power_Control></System>'.format("On" if on else "Standby"))

    async def _do_api_request(self, data) -> str:
        data = '<?xml version="1.0" encoding="utf-8"?>' + data
        try:
            if self._session is None:
                self._session = async_get_clientsession(self.hass)
            
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            async with self._session.post(self._base_url, data=data, timeout=timeout) as req:
                if req.status != 200:
                    _LOGGER.warning("Error doing API request, %d, %s", req.status, data)
                else:
                    _LOGGER.debug("API request ok %d", req.status)
                return await req.text()
        except aiohttp.ClientError as e:
            _LOGGER.error("Request failed: %s", e)
            return ""
        except Exception as e:
            _LOGGER.error("Unexpected error during API request: %s", e)
            return ""

    async def _do_api_get(self, data) -> str:
        request = '<YAMAHA_AV cmd="GET">' + data + '</YAMAHA_AV>'
        _LOGGER.debug("Request:")
        _LOGGER.debug(request)
        response = await self._do_api_request(request)
        _LOGGER.debug("Response:")
        _LOGGER.debug(response)
        return response

    async def _do_api_put(self, data) -> str:
        data = '<YAMAHA_AV cmd="PUT">' + data + '</YAMAHA_AV>'
        return await self._do_api_request(data)

    def _nullify_media_fields(self) -> None:
        """Set media fields to null as we don't require them on certain channels"""
        self._media_meta = {}
        self._media_playing = False
        self._pwstate = STATE_IDLE if self._pwstate != STATE_OFF else STATE_OFF

    def _set_playback_info(self, text: str) -> None:
        """Set the playback info from xml"""
        if text == "Play" or text == "Assert":
            self._pwstate = STATE_PLAYING if self._pwstate != STATE_OFF else STATE_OFF
            self._media_playing = True
        elif text == "Pause":
            self._pwstate = STATE_IDLE if self._pwstate != STATE_OFF else STATE_OFF
            self._media_playing = True
        else:
            self._media_playing = False

    async def _update_media_playing(self):
        media_meta_mapping = {
            'Artist': 'artist',
            'Station': 'song',
            'Radio_Text_A': 'song',
            'Album': 'album',
            'Song': 'song',
            'Track': 'song',
        }
        device_mapping = {
            "Spotify": "Spotify",
            "NET_RADIO": "NET_RADIO",
            "SERVER": "SERVER",
            "TUNER": "Tuner"
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
                            self._media_play_repeat = node.text == "On"
                            self._media_play_shuffle = node.text == "On"
                        elif node.tag == "Play_Time":
                            self._media_play_position = int(node.text)
                            self._media_play_position_updated = dt_util.utcnow()
                        elif node.tag == "Meta_Info":
                            for meta in node:
                                if meta.tag in media_meta_mapping and meta.text:
                                    self._media_meta[media_meta_mapping[meta.tag]] = meta.text.replace('&amp;', '&')
                        elif node.tag == "Playback_Info":
                            self._set_playback_info(node.text)
                        elif node.tag == "Signal_Info":
                            tuned_node = node.find("Tuned")
                            if tuned_node is not None:
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
                    except Exception as e:
                        _LOGGER.warning("Error parsing media node: %s", e)

                _LOGGER.debug("Media metadata:")
                _LOGGER.debug(self._media_meta)
            else:
                self._nullify_media_fields()
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in media update: %s", e)
        except Exception as e:
            _LOGGER.exception("Error updating media info: %s", e)
