"""Fixtures for Yamaha R-N301 tests."""
import asyncio
import copy
import re
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.yamaha_rn301.const import DOMAIN

HOST = "192.168.0.226"
NAME = "Yamaha R-N301"
SERIAL = "0E2FCAE3"
VERSION = "1.13/0.05"
ENTITY_ID = "media_player.yamaha_r_n301"

# Media server menu: (title, children) for folders, (title, None) for tracks.
# "Music" has 10 entries so the last two are on page 2, like on the real device.
SERVER_TREE = ("Media Server", [
    ("ketas", [
        ("Music", [(f"Folder {i}", [(f"Track {i}.{j}", None) for j in range(1, 12)]) for i in range(1, 9)]
         + [("Above & Beyond", [("Track AB.1", None)]), ("Folder 10", [("Track 10.1", None)])]),
    ]),
])
# NET RADIO menu as served by YCast; "Genres" has 11 entries (two pages)
NET_RADIO_TREE = ("NET RADIO", [
    ("Radiobrowser", [
        ("Genres", [(f"Genre {i}", [(f"Station {i}.{j}", None) for j in range(1, 4)]) for i in range(1, 12)]),
        ("Countries", [("Estonia", [("Raadio 2", None), ("Vikerraadio", None)])]),
    ]),
    ("My Stations", [("Bookmarks", [("Sky Plus", None), ("Raadio 2", None)])]),
])
# Inputs of an R-N301 (Main_Zone/Input/Input_Sel_Item)
INPUTS = {"Spotify", "NET RADIO", "SERVER", "AirPlay", "TUNER", "CD", "OPTICAL", "COAXIAL", "LINE1", "LINE2", "LINE3"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeReceiver:
    """Minimal stand-in for the receiver's YamahaRemoteControl XML API."""

    def __init__(self):
        self.hosts = {HOST}
        self.inputs = set(INPUTS)
        self.online = True
        # None: the receiver leaves System_ID out of its answer
        self.serial = SERIAL
        self.version = VERSION
        self.power = "On"
        self.volume = 25
        self.mute = "Off"
        self.input = "SERVER"
        self.playback = "Play"
        self.shuffle = "Off"
        self.repeat = "Off"
        self.song = "Song"
        self.station = "Station"
        self.radio_song = "Artist - Song"
        # Stored Tuner presets and the one selected
        self.presets = [str(i) for i in range(1, 9)]
        self.preset = "2"
        # Number of Play_Info polls after Play, Pause or Stop that still
        # report the old state
        self.playback_lag_polls = 0
        self._playback_lag = None
        # Seconds the Tuner ignores presets after it is selected
        self.tuner_start_time = 0
        self._tuner_selected_at = 0
        self.puts = []
        # Menu position per list input: stack of (node, current_line)
        # Own copies, so a test can change a list
        self.server_tree = copy.deepcopy(SERVER_TREE)
        self.net_radio_tree = copy.deepcopy(NET_RADIO_TREE)
        self.lists = {"SERVER": [(self.server_tree, 1)], "NET_RADIO": [(self.net_radio_tree, 1)]}
        # Number of List_Info polls answered with Menu_Status Busy after a selection
        self.busy_polls = 0
        self._busy_left = 0
        # Number of List_Info polls after a Jump_Line that still show the old
        # page as ready, before the receiver starts loading the new one
        self.jump_lag_polls = 0
        self._pending_jump = None
        # Number of Jump_Line commands to ignore, as the receiver now and then does
        self.ignore_jumps = 0
        # Number of commands refused with RC 4 after turning on, while the
        # receiver starts up
        self.start_up_refusals = 0
        self._refusals_left = 0

    async def handle(self, method, url, data):
        if not self.online or url.host not in self.hosts:
            raise asyncio.TimeoutError
        root = ET.fromstring(data.encode())
        section = root[0]
        if (section.tag == "System" and section.find("Volume") is not None
                or section.tag in ("Spotify", "AirPlay") and section.find("Play_Control/Play_Mode") is not None):
            # The real R-N301 answers HTTP 400 to elements it does not have
            return AiohttpClientMockResponse("post", url, status=400)
        rc = "0"
        if root.get("cmd") == "PUT":
            self.puts.append(ET.tostring(section, encoding="unicode"))
            rc = self._put(section)
            body = ""
        elif section.tag == "System" and section.find("Config") is not None:
            system_id = f"<System_ID>{self.serial}</System_ID>" if self.serial is not None else ""
            body = (f"<System><Config><Model_Name>R-N301</Model_Name>{system_id}"
                    f"<Version>{self.version}</Version></Config></System>")
        elif section.tag == "Main_Zone" and section.find("Basic_Status") is not None:
            body = self._basic_status()
        elif section.tag == "Tuner" and section.find("Play_Control/Preset/Preset_Sel_Item") is not None:
            body = self._preset_items()
        elif section.tag in self.lists and section.find("List_Info") is not None:
            body = self._list_info(section.tag)
        elif section.find("Play_Info") is not None:
            body = self._play_info(section.tag)
        else:
            body = ""
        return AiohttpClientMockResponse(
            "post", url, text=f'<YAMAHA_AV rsp="{root.get("cmd")}" RC="{rc}">{body}</YAMAHA_AV>')

    def _put(self, section):
        """Carry out a command like the receiver and return its RC code."""
        if (power := section.findtext("Power_Control/Power")) is not None:
            if power == "On" and self.power != "On":
                self._refusals_left = self.start_up_refusals
            self.power = power
            return "0"
        if (sel := section.findtext("Input/Input_Sel")) is not None:
            # Taken also in standby
            if sel not in self.inputs:
                return "3"
            if sel == "TUNER":
                self._tuner_selected_at = time.monotonic()
            self.input = sel
            return "0"
        if self.power != "On":
            return "4"
        if self._refusals_left:
            self._refusals_left -= 1
            return "4"
        if (val := section.findtext("Volume/Lvl/Val")) is not None and not 0 <= int(val) <= 100:
            return "3"
        return self._apply(section) or "0"

    def _apply(self, section):
        if (val := section.findtext("Volume/Lvl/Val")) is not None:
            self.volume = int(val)
        if (mute := section.findtext("Volume/Mute")) is not None:
            self.mute = mute
        if (shuffle := section.findtext("Play_Control/Play_Mode/Shuffle")) is not None:
            self.shuffle = shuffle
        if (repeat := section.findtext("Play_Control/Play_Mode/Repeat")) is not None:
            self.repeat = repeat
        if (playback := section.findtext("Play_Control/Playback")) is not None:
            # Like the real receiver, Play does not start again after Stop,
            # which clears the song
            if playback in ("Play", "Pause", "Stop") and self.playback_lag_polls:
                self._playback_lag = [self.playback, self.song, self.playback_lag_polls]
            if playback == "Stop":
                self.song = ""
            if not (playback == "Play" and self.playback == "Stop"):
                self.playback = playback
        if (preset := section.findtext("Play_Control/Preset/Preset_Sel")) is not None:
            if preset == "0":
                return "3"
            if preset in self.presets and time.monotonic() >= self._tuner_selected_at + self.tuner_start_time:
                self.preset = preset
        if section.tag in self.lists and section.find("List_Control") is not None:
            return self._list_control(self.lists[section.tag], section.find("List_Control"))
        return None

    def _list_control(self, stack, control):
        """Move in a list like the receiver; return "3" for a line it does not have."""
        node, line = stack[-1]
        items = node[1]
        page_start = (line - 1) // 8 * 8 + 1
        if (jump := control.findtext("Jump_Line")) is not None:
            if self.ignore_jumps:
                self.ignore_jumps -= 1
                return
            if not 1 <= int(jump) <= len(items):
                return "3"
            self._pending_jump = [stack, int(jump), self.jump_lag_polls]
        elif self._busy_left:
            # Like the real receiver, ignore selections while loading a list
            return
        elif (sel := control.findtext("Direct_Sel")) is not None:
            if not page_start + int(sel[5:]) - 1 <= len(items):
                return "3"
            title, children = items[page_start + int(sel[5:]) - 2]
            if children is None:
                self.song = self.station = title
                self.playback = "Play"
            else:
                stack.append(((title, children), 1))
                self._busy_left = self.busy_polls
        elif (page := control.findtext("Page")) is not None:
            if page == "Down" and page_start + 8 <= len(items):
                stack[-1] = (node, page_start + 8)
            elif page == "Up" and page_start > 8:
                stack[-1] = (node, page_start - 8)
        elif control.findtext("Cursor") == "Return" and len(stack) > 1:
            stack.pop()

    def _list_info(self, tag):
        if self._pending_jump:
            stack, line, lag = self._pending_jump
            if lag:
                self._pending_jump[2] -= 1
            else:
                stack[-1] = (stack[-1][0], line)
                self._pending_jump = None
                self._busy_left = self.busy_polls
        if self._busy_left:
            self._busy_left -= 1
            return f"<{tag}><List_Info><Menu_Status>Busy</Menu_Status></List_Info></{tag}>"
        stack = self.lists[tag]
        (name, items), line = stack[-1]
        page_start = (line - 1) // 8 * 8 + 1
        lines = ""
        for i in range(8):
            if page_start + i <= len(items):
                title, children = items[page_start + i - 1]
                # The receiver escapes "&" twice
                txt, attr = escape(escape(title)), "Container" if children is not None else "Item"
            else:
                txt, attr = "", "Unselectable"
            lines += f"<Line_{i + 1}><Txt>{txt}</Txt><Attribute>{attr}</Attribute></Line_{i + 1}>"
        return (
            f"<{tag}><List_Info><Menu_Status>Ready</Menu_Status>"
            f"<Menu_Layer>{len(stack)}</Menu_Layer><Menu_Name>{escape(name)}</Menu_Name>"
            f"<Current_List>{lines}</Current_List>"
            f"<Cursor_Position><Current_Line>{line}</Current_Line><Max_Line>{len(items)}</Max_Line></Cursor_Position>"
            f"</List_Info></{tag}>"
        )

    def _basic_status(self):
        return (
            "<Main_Zone><Basic_Status>"
            f"<Power_Control><Power>{self.power}</Power><Sleep>Off</Sleep></Power_Control>"
            f"<Volume><Lvl><Val>{self.volume}</Val><Exp>0</Exp><Unit></Unit></Lvl><Mute>{self.mute}</Mute></Volume>"
            f"<Input><Input_Sel>{self.input}</Input_Sel></Input>"
            "</Basic_Status></Main_Zone>"
        )

    def _preset_items(self):
        items = "<Item_1><Param>No Preset</Param><RW>R</RW><Title></Title></Item_1>"
        for i, preset in enumerate(self.presets, 2):
            items += f"<Item_{i}><Param>{preset}</Param><RW>RW</RW><Title>{preset} : FM 97.80 MHz</Title></Item_{i}>"
        return f"<Tuner><Play_Control><Preset><Preset_Sel_Item>{items}</Preset_Sel_Item></Preset></Play_Control></Tuner>"

    def _play_info(self, tag):
        if self._playback_lag:
            playback, song, self._playback_lag[2] = self._playback_lag[0], self._playback_lag[1], self._playback_lag[2] - 1
            if not self._playback_lag[2]:
                self._playback_lag = None
            return self._play_info_xml(tag, playback, song)
        return self._play_info_xml(tag, self.playback, self.song)

    def _play_info_xml(self, tag, playback, song):
        if tag == "Tuner":
            return (
                "<Tuner><Play_Info><Feature_Availability>Ready</Feature_Availability>"
                f"<Search_Mode>Preset</Search_Mode><Preset><Preset_Sel>{self.preset}</Preset_Sel></Preset>"
                "<Tuning><Band>FM</Band><Freq><Current><Val>9780</Val><Exp>2</Exp><Unit>MHz</Unit></Current></Freq></Tuning>"
                "<Signal_Info><Tuned>Assert</Tuned><Stereo>Assert</Stereo></Signal_Info>"
                "</Play_Info></Tuner>"
            )
        if tag == "NET_RADIO":
            meta = f"<Station>{escape(self.station)}</Station><Album></Album><Song>{escape(self.radio_song)}</Song>"
        else:
            meta = f"<Artist>Artist</Artist><Album>Album</Album><Song>{escape(song)}</Song>"
        return (
            f"<{tag}><Play_Info>"
            "<Feature_Availability>Ready</Feature_Availability>"
            f"<Playback_Info>{playback}</Playback_Info>"
            f"<Play_Mode><Repeat>{self.repeat}</Repeat><Shuffle>{self.shuffle}</Shuffle></Play_Mode>"
            f"<Meta_Info>{meta}</Meta_Info>"
            f"</Play_Info></{tag}>"
        )


@pytest.fixture
def receiver(aioclient_mock):
    fake = FakeReceiver()
    aioclient_mock.post(re.compile(r"http://[^/]+/YamahaRemoteControl/ctrl"), side_effect=fake.handle)
    return fake


@pytest.fixture
def config_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_NAME: NAME},
    )
    entry.add_to_hass(hass)
    return entry


async def setup_entry(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
