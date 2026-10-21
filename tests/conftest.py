"""Fixtures for Yamaha R-N301 tests."""
import asyncio
import re
import xml.etree.ElementTree as ET

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.yamaha_rn301.const import DOMAIN

HOST = "192.168.0.226"
NAME = "Yamaha R-N301"
ENTITY_ID = "media_player.yamaha_r_n301"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeReceiver:
    """Minimal stand-in for the receiver's YamahaRemoteControl XML API."""

    def __init__(self):
        self.hosts = {HOST}
        self.online = True
        self.power = "On"
        self.volume = 25
        self.mute = "Off"
        self.input = "SERVER"
        self.playback = "Play"
        self.shuffle = "Off"
        self.puts = []

    async def handle(self, method, url, data):
        if not self.online or url.host not in self.hosts:
            raise asyncio.TimeoutError
        root = ET.fromstring(data.encode())
        section = root[0]
        if root.get("cmd") == "PUT":
            self.puts.append(ET.tostring(section, encoding="unicode"))
            self._apply(section)
            body = ""
        elif section.tag == "Main_Zone" and section.find("Basic_Status") is not None:
            body = self._basic_status()
        elif section.find("Play_Info") is not None:
            body = self._play_info(section.tag)
        else:
            body = ""
        return AiohttpClientMockResponse(
            "post", url, text=f'<YAMAHA_AV rsp="{root.get("cmd")}" RC="0">{body}</YAMAHA_AV>')

    def _apply(self, section):
        if (val := section.findtext("Volume/Lvl/Val")) is not None:
            self.volume = int(val)
        if (sel := section.findtext("Input/Input_Sel")) is not None:
            self.input = sel
        if (shuffle := section.findtext("Play_Control/Play_Mode/Shuffle")) is not None:
            self.shuffle = shuffle
        if (playback := section.findtext("Play_Control/Playback")) is not None:
            self.playback = playback

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
            f"<Play_Mode><Repeat>Off</Repeat><Shuffle>{self.shuffle}</Shuffle></Play_Mode>"
            "<Meta_Info><Artist>Artist</Artist><Album>Album</Album><Song>Song</Song></Meta_Info>"
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
        unique_id=f"rn301_{HOST}",
        data={CONF_HOST: HOST, CONF_NAME: NAME},
    )
    entry.add_to_hass(hass)
    return entry


async def setup_entry(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
