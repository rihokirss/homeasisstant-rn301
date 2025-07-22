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
try:
    from homeassistant.components.media_player.browse_media import BrowseMedia
except ImportError:
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
                MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK

SUPPORT_NET_RADIO = MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF | \
                    MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.BROWSE_MEDIA

SUPPORT_SERVER = MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF | \
                 MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.BROWSE_MEDIA | \
                 MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.STOP | \
                 MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK | MediaPlayerEntityFeature.SHUFFLE_SET

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
        self._unique_id = f"yamaha_rn301_{host.replace('.', '_')}"
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
        self._server_navigation_path = []  # Track SERVER navigation path
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
                            self._volume = int(voln.find("Val").text) / 100
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
        if self._source == "Tuner":
            return SUPPORT_TUNER
        elif self._source == "Net Radio":
            return SUPPORT_NET_RADIO
        elif self._source == "Server":
            return SUPPORT_SERVER
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
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def device_class(self) -> str:
        return "receiver"

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
                int(volume * 100)))

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
        """Play media - for TUNER presets, NET RADIO stations, and SERVER tracks"""
        if self._source == "Tuner" and media_type == "preset":
            await self._do_api_put(f'<Tuner><Play_Control><Preset><Preset_Sel>{media_id}</Preset_Sel></Preset></Play_Control></Tuner>')
        elif self._source == "Net Radio" and media_type == "station":
            # Navigate to the station and play it
            await self._navigate_and_play_station(media_id)
        elif self._source == "Server" and media_type == "music":
            # Navigate to the track and play it
            await self._navigate_and_play_track(media_id)
        elif self._source == "Server" and media_type == "info":
            # Ignore info type media (like "No servers available", page info, etc.)
            _LOGGER.debug("Ignoring info type media for SERVER source")
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
        if self._source != "Tuner":
            self._current_preset = None

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
                                if self._device_source == "TUNER":
                                    self._pwstate = STATE_PLAYING if self._pwstate != STATE_OFF else STATE_OFF
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

                _LOGGER.debug("Media metadata:")
                _LOGGER.debug(self._media_meta)
            else:
                self._nullify_media_fields()
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in media update: %s", e)
        except Exception as e:
            _LOGGER.exception("Error updating media info: %s", e)

    async def _next_preset(self):
        """Switch to next preset (1-8, cycle back to 1)"""
        try:
            if self._current_preset:
                current = int(self._current_preset)
            else:
                current = 1
            
            next_preset = (current % 8) + 1  # Cycle 1-8
            
            await self._do_api_put(f'<Tuner><Play_Control><Preset><Preset_Sel>{next_preset}</Preset_Sel></Preset></Play_Control></Tuner>')
            self._current_preset = str(next_preset)
            await self.async_update()
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Error switching to next preset: %s", e)

    async def _previous_preset(self):
        """Switch to previous preset (1-8, cycle back to 8)"""
        try:
            if self._current_preset:
                current = int(self._current_preset)
            else:
                current = 1
            
            prev_preset = ((current - 2) % 8) + 1  # Cycle 1-8
            
            await self._do_api_put(f'<Tuner><Play_Control><Preset><Preset_Sel>{prev_preset}</Preset_Sel></Preset></Play_Control></Tuner>')
            self._current_preset = str(prev_preset)
            await self.async_update()
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Error switching to previous preset: %s", e)

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Browse NET RADIO stations and SERVER media"""
        _LOGGER.debug(f"async_browse_media called: source={self._source}, content_type={media_content_type}, content_id={media_content_id}")
        if self._source == "Net Radio":
            try:
                if media_content_id is None:
                    # Root level - show main menu
                    return await self._browse_net_radio_root()
                else:
                    # Browse specific menu item
                    return await self._browse_net_radio_item(media_content_id)
            except Exception as e:
                _LOGGER.exception("Error browsing NET RADIO media: %s", e)
                return None
        elif self._source == "Server":
            try:
                if media_content_id is None or media_content_id == "server_root":
                    # Root level - show server selection
                    return await self._browse_server_root()
                else:
                    # Browse specific server item
                    return await self._browse_server_item(media_content_id)
            except Exception as e:
                _LOGGER.exception("Error browsing SERVER media: %s", e)
                return None
        else:
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
                                        media_class=MediaType.CHANNEL,
                                        media_content_id=f"menu:{line.tag}",
                                        media_content_type="folder",
                                        title=title,
                                        can_play=False,
                                        can_expand=True,
                                    ))
            
            if not children:
                _LOGGER.warning("No browsable items found in NET RADIO menu")
                return BrowseMedia(
                    media_class=MediaType.CHANNEL,
                    media_content_id="root",
                    media_content_type="folder",
                    title="NET RADIO",
                    can_play=False,
                    can_expand=False,
                    children=[BrowseMedia(
                        media_class=MediaType.CHANNEL,
                        media_content_id="empty",
                        media_content_type="info",
                        title="No stations available",
                        can_play=False,
                        can_expand=False,
                    )],
                )
            
            return BrowseMedia(
                media_class=MediaType.CHANNEL,
                media_content_id="root",
                media_content_type="folder",
                title="NET RADIO",
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
                                            media_class=MediaType.CHANNEL,
                                            media_content_id=f"menu:{line.tag}",
                                            media_content_type="folder",
                                            title=title,
                                            can_play=False,
                                            can_expand=True,
                                        ))
                                    elif attr == "Item":
                                        children.append(BrowseMedia(
                                            media_class=MediaType.CHANNEL,
                                            media_content_id=f"station:{line.tag}",
                                            media_content_type="station",
                                            title=title,
                                            can_play=True,
                                            can_expand=False,
                                        ))
            
            return BrowseMedia(
                media_class=MediaType.CHANNEL,
                media_content_id=media_content_id,
                media_content_type="folder",
                title=menu_name,
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

    async def _navigate_and_play_track(self, media_id):
        """Navigate to and play a SERVER track"""
        if not media_id.startswith("server_track:"):
            return
        
        _LOGGER.debug(f"Playing track with ID: {media_id}")
        
        # SIMPLIFIED APPROACH: Just play the track directly
        # The API should already be in the correct position due to browsing context
        # We extract the line_id and play it directly
        
        parts = media_id.split(":")
        if len(parts) < 3:
            return
        
        # Extract Line_X from the path - it should be the last part
        line_id = parts[-1] if parts[-1].startswith("Line_") else None
        
        if not line_id:
            # Fallback - find any part that looks like Line_X
            for part in reversed(parts):
                if part.startswith("Line_"):
                    line_id = part
                    break
        
        if not line_id:
            _LOGGER.warning(f"Could not extract line_id from {media_id}")
            return
        
        _LOGGER.debug(f"Playing line: {line_id}")
        
        # Play the track directly - API should be in correct location
        await self._do_api_put(f'<SERVER><List_Control><Direct_Sel>{line_id}</Direct_Sel></List_Control></SERVER>')
        await asyncio.sleep(0.2)
        
        # Start playing
        await self._do_api_put('<SERVER><Play_Control><Playback>Play</Playback></Play_Control></SERVER>')

    async def _browse_server_root(self):
        """Browse SERVER root menu (server selection)"""
        _LOGGER.debug("_browse_server_root called")
        # Reset to root level first
        await self._reset_server_to_root()
        
        # Get current server list
        data = await self._do_api_get("<SERVER><List_Info>GetParam</List_Info></SERVER>")
        if not data:
            _LOGGER.warning("No data received from SERVER browse")
            return None
        
        try:
            tree = ET.fromstring(data)
            children = []
            menu_name = "Media Server"
            
            for node in tree[0][0]:
                if node.tag == "Menu_Name":
                    menu_name = node.text or "Media Server"
                elif node.tag == "Current_List":
                    for line in node:
                        if line.tag.startswith("Line_"):
                            txt_node = line.find("Txt")
                            attr_node = line.find("Attribute")
                            
                            if txt_node is not None and attr_node is not None and txt_node.text:
                                title = txt_node.text
                                attr = attr_node.text
                                
                                if attr == "Container":
                                    children.append(BrowseMedia(
                                        title=title,
                                        media_class=MediaType.MUSIC,
                                        media_content_id=f"server_menu:root:{line.tag}",
                                        media_content_type="folder",
                                        can_play=False,
                                        can_expand=True,
                                    ))
            
            if not children:
                children.append(BrowseMedia(
                    media_class=MediaType.MUSIC,
                    media_content_id="empty",
                    media_content_type="info",
                    title="No servers available",
                    can_play=False,
                    can_expand=False,
                ))
            
            return BrowseMedia(
                media_class=MediaType.MUSIC,
                media_content_id="server_root",
                media_content_type="folder",
                title=menu_name,
                can_play=False,
                can_expand=True,
                children=children,
            )
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in server browse: %s", e)
            return None

    async def _browse_server_item(self, media_content_id):
        """Browse specific SERVER menu item (folders/albums/tracks)"""
        _LOGGER.debug(f"_browse_server_item called with: {media_content_id}")
        
        # Handle pagination commands
        if media_content_id.startswith("server_page_up:"):
            original_id = media_content_id[15:]  # Remove "server_page_up:" prefix
            await self._do_api_put('<SERVER><List_Control><Page>Up</Page></List_Control></SERVER>')
            await asyncio.sleep(0.2)
            # Get the updated list without resetting navigation
            return await self._get_current_server_list(original_id)
        elif media_content_id.startswith("server_page_down:"):
            original_id = media_content_id[17:]  # Remove "server_page_down:" prefix
            await self._do_api_put('<SERVER><List_Control><Page>Down</Page></List_Control></SERVER>')
            await asyncio.sleep(0.2)
            # Get the updated list without resetting navigation
            return await self._get_current_server_list(original_id)
        
        if not media_content_id.startswith("server_menu:"):
            return await self._browse_server_back(media_content_id)
        
        # Parse the path: server_menu:root:Line_1 or server_menu:root:Line_1:Line_2:...
        parts = media_content_id.split(":")
        if len(parts) < 3:
            return None
        
        path_parts = parts[2:]  # Skip 'server_menu' and 'root'
        
        # IMPORTANT: Always reset to root first to ensure consistency
        await self._reset_server_to_root()
        
        # Navigate through the path step by step
        for step in path_parts:
            await self._do_api_put(f'<SERVER><List_Control><Direct_Sel>{step}</Direct_Sel></List_Control></SERVER>')
            # Wait a bit for navigation to complete
            await asyncio.sleep(0.5)
        
        # Get the final list after navigation - with retry for Busy status
        data = None
        for attempt in range(5):  # Max 5 attempts
            data = await self._do_api_get("<SERVER><List_Info>GetParam</List_Info></SERVER>")
            if data and 'Menu_Status>Busy<' not in data:
                break
            await asyncio.sleep(0.5)
        
        if not data:
            return None
        
        try:
            tree = ET.fromstring(data)
            children = []
            menu_name = "Server"
            menu_layer = 1
            current_line = 1
            max_line = 1
            
            # Reconstruct current path from media_content_id
            current_path = ":".join(parts[2:])  # parts from earlier
            
            for node in tree[0][0]:
                if node.tag == "Menu_Name":
                    menu_name = node.text or "Server"
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
                                title = txt_node.text
                                attr = attr_node.text
                                
                                if attr == "Container":
                                    # Folder/Album - extend current path
                                    new_path = f"{current_path}:{line.tag}" if current_path else line.tag
                                    children.append(BrowseMedia(
                                        media_class=MediaType.MUSIC,
                                        media_content_id=f"server_menu:root:{new_path}",
                                        media_content_type="album" if menu_layer > 4 else "folder",
                                        title=title,
                                        can_play=False,
                                        can_expand=True,
                                    ))
                                elif attr == "Item":
                                    # Track/File - simple ID without pagination complexity
                                    track_path = f"{current_path}:{line.tag}" if current_path else line.tag
                                    children.append(BrowseMedia(
                                        media_class=MediaType.TRACK,
                                        media_content_id=f"server_track:root:{track_path}",
                                        media_content_type="music",
                                        title=title,
                                        can_play=True,
                                        can_expand=False,
                                        thumbnail=None,
                                    ))
            
            # Add pagination controls if there are more items than displayed
            if max_line > 8:
                # Add "Previous Page" if not on first page
                if current_line > 1:
                    children.append(BrowseMedia(
                        media_class=MediaType.MUSIC,
                        media_content_id=f"server_page_up:{media_content_id}",
                        media_content_type="info",
                        title="⬆️ Previous Page",
                        can_play=False,
                        can_expand=True,
                        thumbnail=None,
                    ))
                
                # Add "Next Page" if not on last page
                if current_line + 7 < max_line:  # 8 items per page, so +7 from current
                    children.append(BrowseMedia(
                        media_class=MediaType.MUSIC,
                        media_content_id=f"server_page_down:{media_content_id}",
                        media_content_type="info",
                        title="⬇️ Next Page",
                        can_play=False,
                        can_expand=True,
                        thumbnail=None,
                    ))
                
                # Add page info
                current_page = (current_line - 1) // 8 + 1
                total_pages = (max_line - 1) // 8 + 1
                children.append(BrowseMedia(
                    media_class=MediaType.MUSIC,
                    media_content_id="page_info",
                    media_content_type="info",
                    title=f"📄 Page {current_page} of {total_pages} ({max_line} items)",
                    can_play=False,
                    can_expand=False,
                    thumbnail=None,
                ))

            # Add back navigation if not at root level
            if menu_layer > 1:
                # Create parent path by removing last element
                parent_parts = parts[2:-1] if len(parts) > 3 else []
                parent_path = ":".join(parent_parts)
                back_id = f"server_menu:root:{parent_path}" if parent_path else "server_root"
                
                children.insert(0, BrowseMedia(
                    media_class=MediaType.MUSIC,
                    media_content_id=back_id,
                    media_content_type="folder",
                    title="🔙 Back",
                    can_play=False,
                    can_expand=True,
                ))
            
            return BrowseMedia(
                media_class=MediaType.MUSIC,
                media_content_id=media_content_id,
                media_content_type="folder",
                title=menu_name,
                can_play=False,
                can_expand=True,
                children=children,
            )
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in server browse item: %s", e)
            return None

    async def _browse_server_back(self, media_content_id):
        """Handle SERVER back navigation"""
        if media_content_id.startswith("server_back:"):
            # Navigate back using Return command
            await self._do_api_put('<SERVER><List_Control><Cursor>Return</Cursor></List_Control></SERVER>')
            
            # Get the current list after going back
            data = await self._do_api_get("<SERVER><List_Info>GetParam</List_Info></SERVER>")
            if not data:
                return None
            
            try:
                tree = ET.fromstring(data)
                menu_layer = 1
                
                # Check menu layer to determine content ID format
                for node in tree[0][0]:
                    if node.tag == "Menu_Layer":
                        menu_layer = int(node.text) if node.text else 1
                        break
                
                # Return browse result for the new level
                if menu_layer == 1:
                    return await self._browse_server_root()
                else:
                    return await self._browse_server_item("server_menu:current")
                    
            except ET.ParseError as e:
                _LOGGER.error("Failed to parse XML response in server back navigation: %s", e)
                return None
        
        return None

    async def _get_current_server_list(self, media_content_id):
        """Get current SERVER list without navigation reset - used for pagination"""
        _LOGGER.debug(f"_get_current_server_list called with: {media_content_id}")
        
        try:
            # Parse the original path for context
            parts = media_content_id.split(":")
            
            # Get the current list state after pagination
            data = None
            for attempt in range(5):  # Max 5 attempts
                data = await self._do_api_get("<SERVER><List_Info>GetParam</List_Info></SERVER>")
                if data and 'Menu_Status>Busy<' not in data:
                    break
                await asyncio.sleep(0.5)
            
            if not data:
                _LOGGER.warning("No data received in _get_current_server_list")
                return None

            tree = ET.fromstring(data)
            children = []
            menu_name = "Server"
            menu_layer = 1
            current_line = 1
            max_line = 1
            
            # Get current path for context
            current_path = ":".join(parts[2:]) if len(parts) > 2 else ""
            
            for node in tree[0][0]:
                if node.tag == "Menu_Name":
                    menu_name = node.text or "Server"
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
                                title = txt_node.text
                                attr = attr_node.text
                                
                                if attr == "Container":
                                    # Folder/Album - extend current path
                                    new_path = f"{current_path}:{line.tag}" if current_path else line.tag
                                    children.append(BrowseMedia(
                                        media_class=MediaType.MUSIC,
                                        media_content_id=f"server_menu:root:{new_path}",
                                        media_content_type="album" if menu_layer > 4 else "folder",
                                        title=title,
                                        can_play=False,
                                        can_expand=True,
                                        thumbnail=None,
                                    ))
                                elif attr == "Item":
                                    # Track/File - simple ID without pagination complexity
                                    track_path = f"{current_path}:{line.tag}" if current_path else line.tag
                                    children.append(BrowseMedia(
                                        media_class=MediaType.TRACK,
                                        media_content_id=f"server_track:root:{track_path}",
                                        media_content_type="music",
                                        title=title,
                                        can_play=True,
                                        can_expand=False,
                                        thumbnail=None,
                                    ))
            
            # Add pagination controls if there are more items than displayed
            if max_line > 8:
                # Add "Previous Page" if not on first page
                if current_line > 1:
                    children.append(BrowseMedia(
                        media_class=MediaType.MUSIC,
                        media_content_id=f"server_page_up:{media_content_id}",
                        media_content_type="info",
                        title="⬆️ Previous Page",
                        can_play=False,
                        can_expand=True,
                        thumbnail=None,
                    ))
                
                # Add "Next Page" if not on last page
                if current_line + 7 < max_line:  # 8 items per page, so +7 from current
                    children.append(BrowseMedia(
                        media_class=MediaType.MUSIC,
                        media_content_id=f"server_page_down:{media_content_id}",
                        media_content_type="info",
                        title="⬇️ Next Page",
                        can_play=False,
                        can_expand=True,
                        thumbnail=None,
                    ))
                
                # Add page info
                current_page = (current_line - 1) // 8 + 1
                total_pages = (max_line - 1) // 8 + 1
                children.append(BrowseMedia(
                    media_class=MediaType.MUSIC,
                    media_content_id="page_info",
                    media_content_type="info",
                    title=f"📄 Page {current_page} of {total_pages} ({max_line} items)",
                    can_play=False,
                    can_expand=False,
                    thumbnail=None,
                ))

            # Add back navigation if not at root level
            if menu_layer > 1:
                # Create parent path by removing last element
                parent_parts = parts[2:-1] if len(parts) > 3 else []
                parent_path = ":".join(parent_parts)
                back_id = f"server_menu:root:{parent_path}" if parent_path else "server_root"
                
                children.insert(0, BrowseMedia(
                    media_class=MediaType.MUSIC,
                    media_content_id=back_id,
                    media_content_type="folder",
                    title="🔙 Back",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                ))
            
            result = BrowseMedia(
                media_class=MediaType.MUSIC,
                media_content_id=media_content_id,
                media_content_type="folder",
                title=menu_name,
                can_play=False,
                can_expand=True,
                children=children,
                thumbnail=None,
            )
            _LOGGER.debug(f"_get_current_server_list returning BrowseMedia with {len(children)} children")
            return result
            
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse XML response in get current server list: %s", e)
            return None
        except Exception as e:
            _LOGGER.error("Unexpected error in _get_current_server_list: %s", e)
            return None

    async def _reset_server_to_root(self):
        """Reset SERVER navigation to root level"""
        data = await self._do_api_get("<SERVER><List_Info>GetParam</List_Info></SERVER>")
        if data:
            try:
                tree = ET.fromstring(data)
                menu_layer = 1
                for node in tree[0][0]:
                    if node.tag == "Menu_Layer":
                        menu_layer = int(node.text) if node.text else 1
                        break
                
                # Navigate back to root level if not already there
                while menu_layer > 1:
                    await self._do_api_put('<SERVER><List_Control><Cursor>Return</Cursor></List_Control></SERVER>')
                    data = await self._do_api_get("<SERVER><List_Info>GetParam</List_Info></SERVER>")
                    if not data:
                        break
                    tree = ET.fromstring(data)
                    menu_layer = 1
                    for node in tree[0][0]:
                        if node.tag == "Menu_Layer":
                            menu_layer = int(node.text) if node.text else 1
                            break
            except ET.ParseError:
                pass
