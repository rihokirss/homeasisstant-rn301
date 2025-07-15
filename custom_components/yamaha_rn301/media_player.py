import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from typing import Optional
import asyncio

import voluptuous as vol
import aiohttp

from homeassistant.components.media_player import (
    MediaPlayerEntity, PLATFORM_SCHEMA)

from homeassistant.components.media_player.const import (
    ATTR_MEDIA_CONTENT_ID, ATTR_MEDIA_CONTENT_TYPE, MediaType)
from homeassistant.components.media_player import BrowseMedia
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

SUPPORT_TUNER = MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF | \
                MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK

SUPPORT_NET_RADIO = MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF | \
                    MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.BROWSE_MEDIA

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
        self._current_preset = None
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
                if self._source == "Tuner":
                    await self._update_tuner_info()
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
        elif self._source in ("Optical", "CD", "Line 1", "Line 2", "Line 3"):
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
        if self._source == "Tuner" and self._current_preset:
            freq = self._media_meta.get("frequency", "")
            station = self._media_meta.get("station", "")
            
            title = f"Preset {self._current_preset}"
            if station:
                title += f" - {station}"
            if freq:
                title += f" ({freq})"
            
            return title
        elif "song" in self._media_meta and "frequency" in self._media_meta:
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
            return MediaType.CHANNEL
        return MediaType.PLAYLIST

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
        if self._source == "Tuner":
            await self._next_preset()
        else:
            await self._media_play_control("Skip Fwd")

    async def async_media_previous_track(self):
        if self._source == "Tuner":
            await self._previous_preset()
        else:
            await self._media_play_control("Skip Rev")

    async def async_play_media(self, media_type, media_id, **kwargs):
        """Play media - for TUNER presets and NET RADIO stations"""
        if self._source == "Tuner" and media_type == "preset":
            await self._do_api_put(f'<Tuner><Play_Control><Preset><Preset_Sel>{media_id}</Preset_Sel></Preset></Play_Control></Tuner>')
        elif self._source == "Net Radio" and media_type == "station":
            # Navigate to the station and play it
            await self._navigate_and_play_station(media_id)
        else:
            _LOGGER.warning("Play media not supported for source %s with type %s", self._source, media_type)

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
            'Program_Service': 'station',
            'Program_Type': 'genre',
            'Radio_Text_B': 'description',
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

    async def _update_tuner_info(self):
        """Update tuner-specific information including current preset"""
        try:
            data = await self._do_api_get("<Tuner><Play_Info>GetParam</Play_Info></Tuner>")
            if not data:
                return
            tree = ET.fromstring(data)
            for node in tree[0][0]:
                if node.tag == "Preset":
                    preset_node = node.find("Preset_Sel")
                    if preset_node is not None:
                        self._current_preset = preset_node.text
                        _LOGGER.debug("Current preset: %s", self._current_preset)
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in tuner update: %s", e)
        except Exception as e:
            _LOGGER.exception("Error updating tuner info: %s", e)

    async def _next_preset(self):
        """Switch to next preset (1-8, cycle back to 1)"""
        try:
            current = int(self._current_preset) if self._current_preset else 1
            next_preset = (current % 8) + 1  # Cycle 1-8
            
            result = await self._do_api_put(f'<Tuner><Play_Control><Preset><Preset_Sel>{next_preset}</Preset_Sel></Preset></Play_Control></Tuner>')
            _LOGGER.debug("Switched to next preset: %d (result: %s)", next_preset, result)
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Error switching to next preset: %s", e)

    async def _previous_preset(self):
        """Switch to previous preset (1-8, cycle back to 8)"""
        try:
            current = int(self._current_preset) if self._current_preset else 1
            prev_preset = ((current - 2) % 8) + 1  # Cycle 1-8
            
            result = await self._do_api_put(f'<Tuner><Play_Control><Preset><Preset_Sel>{prev_preset}</Preset_Sel></Preset></Play_Control></Tuner>')
            _LOGGER.debug("Switched to previous preset: %d (result: %s)", prev_preset, result)
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Error switching to previous preset: %s", e)


    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Browse NET RADIO stations"""
        if self._source != "Net Radio":
            return None
        
        try:
            if media_content_id is None:
                # Root level - show main menu
                return await self._browse_net_radio_root()
            else:
                # Browse specific menu item
                return await self._browse_net_radio_item(media_content_id)
        except Exception as e:
            _LOGGER.exception("Error browsing media: %s", e)
            return None

    async def _browse_net_radio_root(self):
        """Browse NET RADIO root menu"""
        data = await self._do_api_get("<NET_RADIO><List_Info>GetParam</List_Info></NET_RADIO>")
        if not data:
            _LOGGER.warning("No data received from NET RADIO browse")
            return None
        
        try:
            tree = ET.fromstring(data)
            children = []
            
            for node in tree[0][0]:
                if node.tag == "Current_List":
                    for line in node:
                        if line.tag.startswith("Line_"):
                            txt_node = line.find("Txt")
                            attr_node = line.find("Attribute")
                            
                            if txt_node is not None and attr_node is not None:
                                title = txt_node.text
                                attr = attr_node.text
                                
                                if title and attr == "Container":
                                    children.append(BrowseMedia(
                                        title=title,
                                        media_class=MediaType.CHANNEL,
                                        media_content_id=f"menu:{line.tag}",
                                        media_content_type="folder",
                                        can_play=False,
                                        can_expand=True,
                                    ))
            
            if not children:
                _LOGGER.warning("No browsable items found in NET RADIO menu")
                return BrowseMedia(
                    title="NET RADIO",
                    media_class=MediaType.CHANNEL,
                    media_content_id="root",
                    media_content_type="folder",
                    can_play=False,
                    can_expand=False,
                    children=[BrowseMedia(
                        title="No stations available",
                        media_class=MediaType.CHANNEL,
                        media_content_id="empty",
                        media_content_type="info",
                        can_play=False,
                        can_expand=False,
                    )],
                )
            
            return BrowseMedia(
                title="NET RADIO",
                media_class=MediaType.CHANNEL,
                media_content_id="root",
                media_content_type="folder",
                can_play=False,
                can_expand=True,
                children=children,
            )
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in browse: %s", e)
            return None

    async def _browse_net_radio_item(self, media_content_id):
        """Browse specific NET RADIO menu item"""
        if not media_content_id.startswith("menu:"):
            return None
        
        line_id = media_content_id.split(":", 1)[1]
        
        # Navigate to the menu item
        await self._do_api_put(f'<NET_RADIO><List_Control><Direct_Sel>{line_id}</Direct_Sel></List_Control></NET_RADIO>')
        
        # Get the new list
        data = await self._do_api_get("<NET_RADIO><List_Info>GetParam</List_Info></NET_RADIO>")
        if not data:
            return None
        
        try:
            tree = ET.fromstring(data)
            children = []
            menu_name = "NET RADIO"
            
            for node in tree[0][0]:
                if node.tag == "Menu_Name":
                    menu_name = node.text
                elif node.tag == "Current_List":
                    for line in node:
                        if line.tag.startswith("Line_"):
                            txt_node = line.find("Txt")
                            attr_node = line.find("Attribute")
                            
                            if txt_node is not None and attr_node is not None:
                                title = txt_node.text
                                attr = attr_node.text
                                
                                if title:
                                    if attr == "Container":
                                        children.append(BrowseMedia(
                                            title=title,
                                            media_class=MediaType.CHANNEL,
                                            media_content_id=f"menu:{line.tag}",
                                            media_content_type="folder",
                                            can_play=False,
                                            can_expand=True,
                                        ))
                                    elif attr == "Item":
                                        children.append(BrowseMedia(
                                            title=title,
                                            media_class=MediaType.CHANNEL,
                                            media_content_id=f"station:{line.tag}",
                                            media_content_type="station",
                                            can_play=True,
                                            can_expand=False,
                                        ))
            
            return BrowseMedia(
                title=menu_name,
                media_class=MediaType.CHANNEL,
                media_content_id=media_content_id,
                media_content_type="folder",
                can_play=False,
                can_expand=True,
                children=children,
            )
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in browse item: %s", e)
            return None

    async def _navigate_and_play_station(self, media_id):
        """Navigate to and play a NET RADIO station"""
        if not media_id.startswith("station:"):
            return
        
        line_id = media_id.split(":", 1)[1]
        
        # Select the station
        await self._do_api_put(f'<NET_RADIO><List_Control><Direct_Sel>{line_id}</Direct_Sel></List_Control></NET_RADIO>')
        
        # Start playing
        await self._do_api_put('<NET_RADIO><Play_Control><Playback>Play</Playback></Play_Control></NET_RADIO>')
