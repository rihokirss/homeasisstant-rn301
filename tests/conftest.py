"""Fixtures for Yamaha R-N301 tests."""
import asyncio
import re
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
    ("My Stations", []),
])


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeReceiver:
    """Minimal stand-in for the receiver's YamahaRemoteControl XML API."""

    def __init__(self):
        self.hosts = {HOST}
        self.online = True
        self.serial = SERIAL
        self.power = "On"
        self.volume = 25
        self.mute = "Off"
        self.input = "SERVER"
        self.playback = "Play"
        self.shuffle = "Off"
        self.repeat = "Off"
        self.song = "Song"
        self.puts = []
        # Menu position per list input: stack of (node, current_line)
        self.lists = {"SERVER": [(SERVER_TREE, 1)], "NET_RADIO": [(NET_RADIO_TREE, 1)]}
        # Number of List_Info polls answered with Menu_Status Busy after a selection
        self.busy_polls = 0
        self._busy_left = 0

    async def handle(self, method, url, data):
        if not self.online or url.host not in self.hosts:
            raise asyncio.TimeoutError
        root = ET.fromstring(data.encode())
        section = root[0]
        if section.tag == "System" and section.find("Volume") is not None:
            # The real R-N301 rejects volume commands under <System>.
            return AiohttpClientMockResponse("post", url, status=400)
        if root.get("cmd") == "PUT":
            self.puts.append(ET.tostring(section, encoding="unicode"))
            self._apply(section)
            body = ""
        elif section.tag == "System" and section.find("Config") is not None:
            body = f"<System><Config><Model_Name>R-N301</Model_Name><System_ID>{self.serial}</System_ID></Config></System>"
        elif section.tag == "Main_Zone" and section.find("Basic_Status") is not None:
            body = self._basic_status()
        elif section.tag in self.lists and section.find("List_Info") is not None:
            body = self._list_info(section.tag)
        elif section.find("Play_Info") is not None:
            body = self._play_info(section.tag)
        else:
            body = ""
        return AiohttpClientMockResponse(
            "post", url, text=f'<YAMAHA_AV rsp="{root.get("cmd")}" RC="0">{body}</YAMAHA_AV>')

    def _apply(self, section):
        if (val := section.findtext("Volume/Lvl/Val")) is not None:
            self.volume = int(val)
        if (mute := section.findtext("Volume/Mute")) is not None:
            self.mute = mute
        if (sel := section.findtext("Input/Input_Sel")) is not None:
            self.input = sel
        if (shuffle := section.findtext("Play_Control/Play_Mode/Shuffle")) is not None:
            self.shuffle = shuffle
        if (repeat := section.findtext("Play_Control/Play_Mode/Repeat")) is not None:
            self.repeat = repeat
        if (playback := section.findtext("Play_Control/Playback")) is not None:
            self.playback = playback
        if section.tag in self.lists and section.find("List_Control") is not None:
            self._list_control(self.lists[section.tag], section.find("List_Control"))

    def _list_control(self, stack, control):
        node, line = stack[-1]
        items = node[1]
        page_start = (line - 1) // 8 * 8 + 1
        if (jump := control.findtext("Jump_Line")) is not None:
            stack[-1] = (node, int(jump))
        elif (sel := control.findtext("Direct_Sel")) is not None:
            title, children = items[page_start + int(sel[5:]) - 2]
            if children is None:
                self.song, self.playback = title, "Play"
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

    def _play_info(self, tag):
        return (
            f"<{tag}><Play_Info>"
            "<Feature_Availability>Ready</Feature_Availability>"
            f"<Playback_Info>{self.playback}</Playback_Info>"
            f"<Play_Mode><Repeat>{self.repeat}</Repeat><Shuffle>{self.shuffle}</Shuffle></Play_Mode>"
            f"<Meta_Info><Artist>Artist</Artist><Album>Album</Album><Song>{escape(self.song)}</Song></Meta_Info>"
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
