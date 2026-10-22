# Yamaha R-N301 API Reference

The XML control API of the Yamaha R-N301 network receiver, as the Home Assistant integration uses it. Everything here was checked against an R-N301 with firmware 1.13/0.05 in October 2026. Other Yamaha network receivers of the same generation use the same API, but their inputs and details may differ.

## Table of Contents

- [API Overview](#api-overview)
- [Responses and Errors](#responses-and-errors)
- [System](#system)
- [Main Zone](#main-zone)
- [Input Status and Playback](#input-status-and-playback)
- [Browsing Lists (SERVER and NET RADIO)](#browsing-lists-server-and-net-radio)
- [Tuner](#tuner)
- [Examples](#examples)
- [How the Integration Uses the API](#how-the-integration-uses-the-api)

## API Overview

Requests are HTTP POSTs to port 80, without authentication:
```
http://{receiver_ip}/YamahaRemoteControl/ctrl
```

```xml
<YAMAHA_AV cmd="GET|PUT">
  <!-- Command -->
</YAMAHA_AV>
```

- `GET` reads a value: the element to read holds `GetParam`.
- `PUT` sends a command or sets a value.

The R-N301 has no `desc.xml` file that lists its commands (the request returns 404). Its UPnP description at `http://{receiver_ip}:8080/MediaRenderer/desc.xml` names the control URL and holds the serial number, which is the same as the `System_ID` below.

## Responses and Errors

```xml
<YAMAHA_AV rsp="GET|PUT" RC="0">
  <!-- For GET the values read; for PUT the command's elements, empty -->
</YAMAHA_AV>
```

`RC="0"` means that the receiver took the request. The other answers seen on the R-N301:

| Answer | Meaning | Seen for |
|--------|---------|----------|
| HTTP 200, `RC="2"` | The element cannot be read | `GET` of `<System><Power_Control>` or `<Main_Zone><Power_Control>` |
| HTTP 200, `RC="3"` | The value is not accepted | Volume `-5`, an input the receiver does not have, `<Mute>` other than `On`/`Off`, `Jump_Line` past the end of the list, `Direct_Sel` `Line_9`, `<Repeat>` other than `Off`/`One`/`All`, `Preset_Sel` `0`, `Pause` or `Skip` for NET RADIO |
| HTTP 200, `RC="4"` | Not in standby | Volume, mute, `Play_Control` and `List_Control` commands in standby and for about half a second after turning on |
| HTTP 400, empty body | The element does not exist for this zone or input | `<System><Volume>`, `<Main_Zone><Play_Info>`, `<TUNER>` (the element is `<Tuner>`), `Playback` for the Tuner, `Play_Mode` for Spotify and AirPlay |

`RC="0"` does not mean that the receiver acted on the command. It also answers `RC="0"` to:
- `Input_Sel` in standby (the receiver stays in standby)
- Playback commands for an input that is not selected
- `Direct_Sel`, `Jump_Line` and `Cursor` while a list is loading, which it ignores
- `Preset_Sel` with a preset number that has no station stored
- `Play` after `Stop` for SERVER or NET RADIO, which does not start the track or station again

`GET` requests are answered in standby too.

## System

### Configuration

```xml
<YAMAHA_AV cmd="GET"><System><Config>GetParam</Config></System></YAMAHA_AV>
```

```xml
<YAMAHA_AV rsp="GET" RC="0">
  <System>
    <Config>
      <Model_Name>R-N301</Model_Name>
      <System_ID>0E2FCAE3</System_ID>
      <Version>1.13/0.05</Version>
      <Feature_Existence>
        <Main_Zone>1</Main_Zone><Tuner>1</Tuner><Spotify>1</Spotify><Pandora>0</Pandora>
        <SERVER>1</SERVER><NET_RADIO>1</NET_RADIO><AirPlay>1</AirPlay>
      </Feature_Existence>
    </Config>
  </System>
</YAMAHA_AV>
```

`System_ID` is the serial number the receiver announces over SSDP. The integration uses it as the unique ID of the receiver.

### Power

```xml
<YAMAHA_AV cmd="PUT">
  <System>
    <Power_Control>
      <Power>On|Standby</Power>
    </Power_Control>
  </System>
</YAMAHA_AV>
```

`<Main_Zone><Power_Control>` also answers `On` with `RC="0"`. The power state is read from the [basic status](#basic-status).

After `On` the receiver refuses other commands with `RC="4"` for about half a second: in a test, a volume command was refused 0.3 s after turning on and taken 0.6 s after. NET RADIO does not resume the last station after turning on.

## Main Zone

### Basic Status

```xml
<YAMAHA_AV cmd="GET"><Main_Zone><Basic_Status>GetParam</Basic_Status></Main_Zone></YAMAHA_AV>
```

```xml
<YAMAHA_AV rsp="GET" RC="0">
  <Main_Zone>
    <Basic_Status>
      <Power_Control>
        <Power>On</Power>  <!-- On or Standby -->
      </Power_Control>
      <Volume>
        <Lvl><Val>18</Val><Exp>0</Exp><Unit></Unit></Lvl>
        <Mute>Off</Mute>
      </Volume>
      <Input>
        <Input_Sel>NET RADIO</Input_Sel>
        <Input_Sel_Item_Info>
          <Param>NET RADIO</Param>
          <RW>RW</RW>
          <Title></Title>
          <Icon><On>/YamahaRemoteControl/Icons/icon067.png</On><Off></Off></Icon>
          <Src_Name>NET_RADIO</Src_Name>
          <Src_Number>1</Src_Number>
        </Input_Sel_Item_Info>
      </Input>
    </Basic_Status>
  </Main_Zone>
</YAMAHA_AV>
```

### Volume

```xml
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Volume>
      <Lvl><Val>{volume}</Val><Exp>0</Exp><Unit></Unit></Lvl>
    </Volume>
  </Main_Zone>
</YAMAHA_AV>
```

The scale is 0 to 100; the integration multiplies Home Assistant's 0.0–1.0 volume level by 100. Values outside the scale are refused (`-5` was answered with `RC="3"`).

### Mute

```xml
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Volume>
      <Mute>On|Off</Mute>
    </Volume>
  </Main_Zone>
</YAMAHA_AV>
```

Volume and mute go under `<Main_Zone>`: the same commands under `<System>` are answered with HTTP 400.

### Inputs

```xml
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Input>
      <Input_Sel>{input}</Input_Sel>
    </Input>
  </Main_Zone>
</YAMAHA_AV>
```

The receiver lists its inputs with:
```xml
<YAMAHA_AV cmd="GET"><Main_Zone><Input><Input_Sel_Item>GetParam</Input_Sel_Item></Input></Main_Zone></YAMAHA_AV>
```

| `Input_Sel` | Element of the input's own commands (`Src_Name`) | Source in Home Assistant |
|-------------|--------------------------------------------------|--------------------------|
| `Spotify` | `Spotify` | Spotify |
| `NET RADIO` | `NET_RADIO` | Net Radio |
| `SERVER` | `SERVER` | Server |
| `AirPlay` | `AirPlay` | AirPlay |
| `TUNER` | `Tuner` | Tuner |
| `CD`, `OPTICAL`, `COAXIAL`, `LINE1`, `LINE2`, `LINE3` | none | CD, Optical, Coaxial, Line 1–3 |

An input name the receiver does not have is answered with `RC="3"`. When you switch to NET RADIO, its menu returns to the top level and the last station does not start again.

## Input Status and Playback

### Play Info

Each input has its own status. There is no `<Main_Zone><Play_Info>` (HTTP 400).

```xml
<YAMAHA_AV cmd="GET"><{Src_Name}><Play_Info>GetParam</Play_Info></{Src_Name}></YAMAHA_AV>
```

All inputs answer with `Feature_Availability` (`Ready` or `Not Ready`). The other fields:

| Input | Fields |
|-------|--------|
| `SERVER` | `Playback_Info`, `Play_Mode` (`Repeat`, `Shuffle`), `Play_Time` (seconds), `Meta_Info` (`Artist`, `Album`, `Song`), `Album_ART` |
| `NET_RADIO` | `Playback_Info`, `Play_Time`, `Meta_Info` (`Station`, `Album`, `Song`), `Album_ART` |
| `Spotify` | `Playback_Info`, `Meta_Info` (`Artist`, `Album`, `Track`), `Input_Logo` |
| `AirPlay` | `Playback_Info`, `Play_Time`, `Meta_Info` (`Artist`, `Album`, `Song`), `Input_Logo` |
| `Tuner` | `Search_Mode`, `Preset/Preset_Sel`, `Tuning` (`Band`, `Freq`), `FM_Mode`, `Signal_Info` (`Tuned`, `Stereo`), `Meta_Info` (`Program_Type`, `Program_Service`, `Radio_Text_A`, `Radio_Text_B`, `Clock_Time`) |

- `Playback_Info` is `Play`, `Pause` or `Stop`.
- For NET RADIO, `Song` is usually "Artist - Title" as the station sends it.
- `Album_ART` points to an image in Yamaha's own YMF format (`<Format>YMF</Format>`), which a browser cannot show.

NET RADIO example:
```xml
<YAMAHA_AV rsp="GET" RC="0">
  <NET_RADIO>
    <Play_Info>
      <Feature_Availability>Ready</Feature_Availability>
      <Playback_Info>Play</Playback_Info>
      <Play_Time>236</Play_Time>
      <Meta_Info>
        <Station>Raadio 2</Station>
        <Album></Album>
        <Song>BECK - Run Away</Song>
      </Meta_Info>
      <Album_ART><URL></URL><ID>4</ID><Format>YMF</Format></Album_ART>
    </Play_Info>
  </NET_RADIO>
</YAMAHA_AV>
```

### Playback

```xml
<YAMAHA_AV cmd="PUT">
  <{Src_Name}>
    <Play_Control>
      <Playback>Play|Pause|Stop|Skip Fwd|Skip Rev</Playback>
    </Play_Control>
  </{Src_Name}>
</YAMAHA_AV>
```

```xml
<!-- Shuffle and repeat: SERVER only -->
<YAMAHA_AV cmd="PUT">
  <SERVER>
    <Play_Control>
      <Play_Mode>
        <Shuffle>On|Off</Shuffle>
        <Repeat>Off|One|All</Repeat>
      </Play_Mode>
    </Play_Control>
  </SERVER>
</YAMAHA_AV>
```

| Input | `Play` | `Pause` | `Stop` | `Skip Fwd`, `Skip Rev` | `Play_Mode` |
|-------|--------|---------|--------|------------------------|-------------|
| `SERVER` | Yes, after `Pause` | Yes | Yes | Yes | Yes |
| `Spotify` | Taken | Taken | Taken | Taken | HTTP 400 |
| `AirPlay` | Taken | Taken | Taken | Taken | HTTP 400 |
| `NET_RADIO` | Taken | `RC="3"` | Yes | `RC="3"` | HTTP 400 |
| `Tuner` | HTTP 400 | HTTP 400 | HTTP 400 | HTTP 400 | HTTP 400 |

- "Taken": answered with `RC="0"`. The effect could not be checked because nothing was playing over Spotify or AirPlay during the test.
- After `Stop`, `Play` does not start a SERVER track or NET RADIO station again, although it is answered with `RC="0"`: select it in the list again.
- A NET RADIO station or SERVER track starts playing when it is selected with `Direct_Sel` (see below), so `Play` is not needed after it.
- The Tuner is controlled with [presets](#tuner).

## Browsing Lists (SERVER and NET RADIO)

The SERVER and NET RADIO inputs have a menu of lists. The receiver keeps one menu position per input, and the receiver's own display shows it too.

### Reading the List Shown

```xml
<YAMAHA_AV cmd="GET"><NET_RADIO><List_Info>GetParam</List_Info></NET_RADIO></YAMAHA_AV>
```

```xml
<YAMAHA_AV rsp="GET" RC="0">
  <NET_RADIO>
    <List_Info>
      <Menu_Status>Ready</Menu_Status>  <!-- Busy while the list loads -->
      <Menu_Layer>1</Menu_Layer>        <!-- 1 is the top level -->
      <Menu_Name>NET RADIO</Menu_Name>
      <Current_List>
        <Line_1><Txt>Radiobrowser</Txt><Attribute>Container</Attribute></Line_1>
        <Line_2><Txt>My Stations</Txt><Attribute>Container</Attribute></Line_2>
        <Line_3><Txt></Txt><Attribute>Unselectable</Attribute></Line_3>
        <!-- ... always up to Line_8 -->
      </Current_List>
      <Cursor_Position>
        <Current_Line>1</Current_Line>
        <Max_Line>2</Max_Line>
      </Cursor_Position>
    </List_Info>
  </NET_RADIO>
</YAMAHA_AV>
```

- **Pages:** `Current_List` holds one page of 8 lines, always numbered `Line_1` to `Line_8`. The page shown is the one that holds `Current_Line`, so line `n` of the page is line `(Current_Line - 1) // 8 * 8 + n` of the list. `Max_Line` is the length of the list.
- **Attributes:** `Container` is a folder, `Item` a station or track, and `Unselectable` an empty line that fills the page.
- **Escaping:** The receiver escapes `&` twice in `Txt` (`&amp;amp;`).
- **In standby:** `List_Info` is answered, `List_Control` is refused with `RC="4"`.

### Moving in the List

```xml
<!-- Select line 1-8 of the page shown: open a folder, or play a station or track -->
<YAMAHA_AV cmd="PUT"><NET_RADIO><List_Control><Direct_Sel>Line_{1-8}</Direct_Sel></List_Control></NET_RADIO></YAMAHA_AV>

<!-- Show the page that holds line n of the list (1 to Max_Line) -->
<YAMAHA_AV cmd="PUT"><NET_RADIO><List_Control><Jump_Line>{n}</Jump_Line></List_Control></NET_RADIO></YAMAHA_AV>

<!-- Previous or next page -->
<YAMAHA_AV cmd="PUT"><NET_RADIO><List_Control><Page>Up|Down</Page></List_Control></NET_RADIO></YAMAHA_AV>

<!-- One level up (also answered with RC="0" at the top level) -->
<YAMAHA_AV cmd="PUT"><NET_RADIO><List_Control><Cursor>Return</Cursor></List_Control></NET_RADIO></YAMAHA_AV>
```

The same commands work with `<SERVER>`.

### Timing

- **Loading:** After each `Direct_Sel` or `Jump_Line`, the list is `Busy` while it loads. For NET RADIO this takes 0.4–1 s per page. A media server that is waking up can take several seconds.
- **Ignored commands:** The receiver ignores selections while the list is busy, but still answers them with `RC="0"`.
- **Stale page:** Right after a `Jump_Line`, `List_Info` may still report the old page as `Ready` before it turns `Busy`.
- **Lost jumps:** Now and then the receiver ignores a `Jump_Line`.

So after a command, read `List_Info` until it is `Ready` and shows the page you wanted, and send a `Jump_Line` again if it does not.

### SERVER Menu

The levels below the server depend on the media server software. With the server used for testing:

| Layer | Content | Example |
|-------|---------|---------|
| 1 | Media servers | `ketas` |
| 2 | Media types | `Music`, `Photo`, `Video` |
| 3 | Categories | `By Folder`, `All music`, `Playlist`, `Smart Playlist`, `By Album`, `By Artist`, `By Genre`, `Artist/Album` |
| 4+ | Folders, artists, albums, then tracks (`Item`) | `By Folder` → `Albums` → an album → `CD1` → tracks |

### NET RADIO Menu

The receiver loads the NET RADIO menu from `radioyamaha.vtuner.com` and `radioyamaha2.vtuner.com`. vTuner no longer serves the R-N301, but [YCast](https://github.com/milaq/YCast) can take its place (see the README).

With YCast the top level is:
- **Radiobrowser**, with `Genres`, `Countries`, `Languages` and `Most Popular`
- **My Stations**, with the bookmarks from the YCast settings in a `Bookmarks` folder

The receiver cannot play HTTPS streams: it skips such a station and plays the next station in the list instead.

## Tuner

The input is `TUNER`, but its element is `<Tuner>`.

```xml
<!-- Stored presets -->
<YAMAHA_AV cmd="GET"><Tuner><Play_Control><Preset><Preset_Sel_Item>GetParam</Preset_Sel_Item></Preset></Play_Control></Tuner></YAMAHA_AV>

<!-- Select a preset -->
<YAMAHA_AV cmd="PUT"><Tuner><Play_Control><Preset><Preset_Sel>{n}</Preset_Sel></Preset></Play_Control></Tuner></YAMAHA_AV>
```

`Preset_Sel_Item` lists `No Preset` and then each stored preset, for example `<Param>2</Param>` with the title `2 : FM 97.80 MHz`.
- `Preset_Sel` `0` is refused with `RC="3"`.
- A number with no stored preset is answered with `RC="0"`, but the preset does not change.

The frequency is `Val` × 10^-`Exp` in `Unit`: `<Val>9780</Val><Exp>2</Exp><Unit>MHz</Unit>` is 97.80 MHz. The Tuner has no `Playback` commands (HTTP 400).

## Examples

### Turn On and Play Spotify

```xml
<YAMAHA_AV cmd="PUT"><System><Power_Control><Power>On</Power></Power_Control></System></YAMAHA_AV>
<!-- Commands are refused with RC="4" for about half a second: send again until RC="0" -->
<YAMAHA_AV cmd="PUT"><Main_Zone><Input><Input_Sel>Spotify</Input_Sel></Input></Main_Zone></YAMAHA_AV>
<YAMAHA_AV cmd="PUT"><Spotify><Play_Control><Playback>Play</Playback></Play_Control></Spotify></YAMAHA_AV>
```

### Play a YCast Bookmark

```xml
<YAMAHA_AV cmd="PUT"><Main_Zone><Input><Input_Sel>NET RADIO</Input_Sel></Input></Main_Zone></YAMAHA_AV>
<!-- The menu is at the top level after switching input; wait until List_Info is Ready -->
<YAMAHA_AV cmd="PUT"><NET_RADIO><List_Control><Direct_Sel>Line_2</Direct_Sel></List_Control></NET_RADIO></YAMAHA_AV>  <!-- My Stations -->
<!-- Wait until Ready -->
<YAMAHA_AV cmd="PUT"><NET_RADIO><List_Control><Direct_Sel>Line_1</Direct_Sel></List_Control></NET_RADIO></YAMAHA_AV>  <!-- Bookmarks -->
<!-- Wait until Ready -->
<YAMAHA_AV cmd="PUT"><NET_RADIO><List_Control><Direct_Sel>Line_2</Direct_Sel></List_Control></NET_RADIO></YAMAHA_AV>  <!-- The second station; it starts playing -->
```

The station name appears in `Play_Info` after 2–3 seconds.

## How the Integration Uses the API

- **Polling:** Every 10 seconds (Home Assistant's default for media players), the integration reads the basic status, and the input's `Play_Info` when the receiver is on.
- **Unreachable receiver:** Requests time out after 5 seconds. After 3 failed polls in a row, the entity becomes unavailable.
- **Failed commands:** When the receiver does not take a command (it cannot be reached, HTTP 400, or an `RC` other than `0`), the action in Home Assistant fails with a message such as "The receiver is in standby".
- **After turning on:** For 3 seconds after the integration turns the receiver on, commands refused with `RC="4"` are sent again every 0.2 seconds. So an automation can turn the receiver on and set the volume right after.
- **Lists:** While a list loads, `List_Info` is read every 0.15 seconds, for at most 10 seconds. A `Jump_Line` the receiver has not acted on is sent again after 2 seconds.
- **Saved lists:** Lists read for the media browser are kept, also across restarts. A list older than 10 minutes is read again in the background when it is opened.
- **Security:** The API has no authentication, so the receiver should only be reachable on the local network.

The integration's changelog is in the [README](../README.md#recent-updates).
