# Yamaha R-N301 API Reference

This document provides comprehensive documentation for the Yamaha R-N301 XML control API as implemented in the Home Assistant integration.

## Table of Contents

- [API Overview](#api-overview)
- [Basic Communication](#basic-communication)
- [Main Zone Control](#main-zone-control)
- [Media Sources](#media-sources)
- [SERVER Media Browsing](#server-media-browsing)
- [NET RADIO Control](#net-radio-control)
- [TUNER Control](#tuner-control)
- [Error Handling](#error-handling)
- [Examples](#examples)

## API Overview

The Yamaha R-N301 uses an HTTP-based XML API for remote control. All requests are sent as POST requests to:
```
http://{receiver_ip}/YamahaRemoteControl/ctrl
```

### Request Format
All requests follow this XML structure:
```xml
<YAMAHA_AV cmd="GET|PUT">
  <!-- Command content -->
</YAMAHA_AV>
```

- `GET` commands retrieve information
- `PUT` commands change settings

### Response Format
All responses follow this XML structure:
```xml
<YAMAHA_AV rsp="GET|PUT" RC="0">
  <!-- Response content -->
</YAMAHA_AV>
```

- `RC="0"` indicates success
- Non-zero RC values indicate errors

## Basic Communication

### Power Control

#### Get Power Status
```xml
<YAMAHA_AV cmd="GET">
  <Main_Zone>
    <Basic_Status>GetParam</Basic_Status>
  </Main_Zone>
</YAMAHA_AV>
```

**Response:**
```xml
<YAMAHA_AV rsp="GET" RC="0">
  <Main_Zone>
    <Basic_Status>
      <Power_Control>
        <Power>On|Off</Power>
      </Power_Control>
      <!-- Additional status info -->
    </Basic_Status>
  </Main_Zone>
</YAMAHA_AV>
```

#### Set Power State
```xml
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Power_Control>
      <Power>On|Off</Power>
    </Power_Control>
  </Main_Zone>
</YAMAHA_AV>
```

### Volume Control

#### Set Volume Level
```xml
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Volume>
      <Lvl>
        <Val>{volume}</Val>
        <Exp>1</Exp>
        <Unit>dB</Unit>
      </Lvl>
    </Volume>
  </Main_Zone>
</YAMAHA_AV>
```

Volume range: -80.5 to +16.5 dB (multiply by 10 for API values)

#### Mute Control
```xml
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Volume>
      <Mute>On|Off</Mute>
    </Volume>
  </Main_Zone>
</YAMAHA_AV>
```

## Main Zone Control

### Input Source Selection

#### Set Input Source
```xml
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Input>
      <Input_Sel>{source}</Input_Sel>
    </Input>
  </Main_Zone>
</YAMAHA_AV>
```

**Available Sources:**
- `OPTICAL` - Optical digital input
- `CD` - CD player input  
- `LINE1`, `LINE2`, `LINE3` - Analog line inputs
- `Spotify` - Spotify Connect
- `NET RADIO` - Internet radio
- `SERVER` - Media server (DLNA/UPnP)
- `TUNER` - FM/AM radio tuner

### Media Information

#### Get Current Media Info
```xml
<YAMAHA_AV cmd="GET">
  <Main_Zone>
    <Play_Info>GetParam</Play_Info>
  </Main_Zone>
</YAMAHA_AV>
```

**Response Structure:**
```xml
<YAMAHA_AV rsp="GET" RC="0">
  <Main_Zone>
    <Play_Info>
      <Input_Name>{source}</Input_Name>
      <Playback_Info>
        <Track>{track}</Track>
        <Artist>{artist}</Artist>
        <Album>{album}</Album>
        <Station>{station}</Station>
        <Playback>{state}</Playback>
      </Playback_Info>
      <Meta_Info>
        <Program_Type>{type}</Program_Type>
        <Program_Service>{service}</Program_Service>
        <Audio_Mode>{mode}</Audio_Mode>
      </Meta_Info>
    </Play_Info>
  </Main_Zone>
</YAMAHA_AV>
```

## Media Sources

### Playback Control

#### Universal Playback Commands
```xml
<!-- Play -->
<YAMAHA_AV cmd="PUT">
  <{SOURCE}>
    <Play_Control>
      <Playback>Play</Playback>
    </Play_Control>
  </{SOURCE}>
</YAMAHA_AV>

<!-- Pause -->
<YAMAHA_AV cmd="PUT">
  <{SOURCE}>
    <Play_Control>
      <Playback>Pause</Playback>
    </Play_Control>
  </{SOURCE}>
</YAMAHA_AV>

<!-- Stop -->
<YAMAHA_AV cmd="PUT">
  <{SOURCE}>
    <Play_Control>
      <Playback>Stop</Playback>
    </Play_Control>
  </{SOURCE}>
</YAMAHA_AV>

<!-- Skip Forward -->
<YAMAHA_AV cmd="PUT">
  <{SOURCE}>
    <Play_Control>
      <Playback>Skip Fwd</Playback>
    </Play_Control>
  </{SOURCE}>
</YAMAHA_AV>

<!-- Skip Reverse -->
<YAMAHA_AV cmd="PUT">
  <{SOURCE}>
    <Play_Control>
      <Playback>Skip Rev</Playback>
    </Play_Control>
  </{SOURCE}>
</YAMAHA_AV>
```

Replace `{SOURCE}` with: `Spotify`, `NET_RADIO`, `SERVER`, etc.

## SERVER Media Browsing

The SERVER input provides DLNA/UPnP media browsing capabilities with a hierarchical structure.

### Get Current List
```xml
<YAMAHA_AV cmd="GET">
  <SERVER>
    <List_Info>GetParam</List_Info>
  </SERVER>
</YAMAHA_AV>
```

**Response Structure:**
```xml
<YAMAHA_AV rsp="GET" RC="0">
  <SERVER>
    <List_Info>
      <Menu_Status>Ready|Busy</Menu_Status>
      <Menu_Layer>{layer_number}</Menu_Layer>
      <Menu_Name>{current_menu_name}</Menu_Name>
      <Current_List>
        <Line_1>
          <Txt>{item_title}</Txt>
          <Attribute>Container|Item|Unselectable</Attribute>
        </Line_1>
        <!-- More Line_X entries up to Line_8 -->
      </Current_List>
      <Cursor_Position>
        <Current_Line>{current_position}</Current_Line>
        <Max_Line>{total_items}</Max_Line>
      </Cursor_Position>
    </List_Info>
  </SERVER>
</YAMAHA_AV>
```

### Navigation Structure

The SERVER browsing follows a hierarchical structure:

| Layer | Content Type | Example | Attribute |
|-------|-------------|---------|-----------|
| 1 | Media Servers | "ketas", "NAS" | Container |
| 2 | Media Types | "Music", "Photo", "Video" | Container |
| 3 | Categories | "By Artist", "By Album", "Playlist" | Container |
| 4 | Collections | Artist names, Album names | Container |
| 5+ | Items/Tracks | Song titles, File names | Item |

### Navigation Commands

#### Navigate to Item
```xml
<YAMAHA_AV cmd="PUT">
  <SERVER>
    <List_Control>
      <Direct_Sel>Line_{number}</Direct_Sel>
    </List_Control>
  </SERVER>
</YAMAHA_AV>
```

#### Go Back
```xml
<YAMAHA_AV cmd="PUT">
  <SERVER>
    <List_Control>
      <Cursor>Return</Cursor>
    </List_Control>
  </SERVER>
</YAMAHA_AV>
```

#### Pagination
```xml
<!-- Previous Page -->
<YAMAHA_AV cmd="PUT">
  <SERVER>
    <List_Control>
      <Page>Up</Page>
    </List_Control>
  </SERVER>
</YAMAHA_AV>

<!-- Next Page -->
<YAMAHA_AV cmd="PUT">
  <SERVER>
    <List_Control>
      <Page>Down</Page>
    </List_Control>
  </SERVER>
</YAMAHA_AV>
```

### Play Track
```xml
<YAMAHA_AV cmd="PUT">
  <SERVER>
    <List_Control>
      <Direct_Sel>Line_{number}</Direct_Sel>
    </List_Control>
  </SERVER>
</YAMAHA_AV>
```
*Note: Follow with playback command to start playing*

## NET RADIO Control

### Get Station List
```xml
<YAMAHA_AV cmd="GET">
  <NET_RADIO>
    <List_Info>GetParam</List_Info>
  </NET_RADIO>
</YAMAHA_AV>
```

### Navigate and Play Station
```xml
<!-- Select Station -->
<YAMAHA_AV cmd="PUT">
  <NET_RADIO>
    <List_Control>
      <Direct_Sel>Line_{number}</Direct_Sel>
    </List_Control>
  </NET_RADIO>
</YAMAHA_AV>

<!-- Start Playing -->
<YAMAHA_AV cmd="PUT">
  <NET_RADIO>
    <Play_Control>
      <Playback>Play</Playback>
    </Play_Control>
  </NET_RADIO>
</YAMAHA_AV>
```

## TUNER Control

### Preset Navigation
The TUNER source supports 8 presets (1-8) accessed via skip commands:

```xml
<!-- Next Preset -->
<YAMAHA_AV cmd="PUT">
  <TUNER>
    <Play_Control>
      <Playback>Skip Fwd</Playback>
    </Play_Control>
  </TUNER>
</YAMAHA_AV>

<!-- Previous Preset -->
<YAMAHA_AV cmd="PUT">
  <TUNER>
    <Play_Control>
      <Playback>Skip Rev</Playback>
    </Play_Control>
  </TUNER>
</YAMAHA_AV>
```

### Get TUNER Info
TUNER information is available in the main Play_Info response:
- `Station` - Station name or frequency
- `Radio_Text_A`, `Radio_Text_B` - RDS information
- `Program_Type` - RDS program type
- `Program_Service` - RDS service name

## Error Handling

### Common Response Codes
- `RC="0"` - Success
- `RC="1"` - General error
- `RC="2"` - Invalid parameter
- `RC="3"` - Operation not available

### Busy Status
When navigating SERVER or NET_RADIO, check for busy status:
```xml
<Menu_Status>Busy</Menu_Status>
```

Wait and retry when busy status is detected.

### Timeout Handling
- Use reasonable timeouts (2-5 seconds) for HTTP requests
- Implement retry logic for temporary failures
- Add delays between rapid API calls (200-500ms)

## Examples

### Complete Power On and Play Spotify
```xml
<!-- 1. Power On -->
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Power_Control>
      <Power>On</Power>
    </Power_Control>
  </Main_Zone>
</YAMAHA_AV>

<!-- 2. Switch to Spotify -->
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Input>
      <Input_Sel>Spotify</Input_Sel>
    </Input>
  </Main_Zone>
</YAMAHA_AV>

<!-- 3. Start Playing -->
<YAMAHA_AV cmd="PUT">
  <Spotify>
    <Play_Control>
      <Playback>Play</Playback>
    </Play_Control>
  </Spotify>
</YAMAHA_AV>
```

### Navigate SERVER to Artist and Play Album
```xml
<!-- 1. Switch to SERVER -->
<YAMAHA_AV cmd="PUT">
  <Main_Zone>
    <Input>
      <Input_Sel>SERVER</Input_Sel>
    </Input>
  </Main_Zone>
</YAMAHA_AV>

<!-- 2. Get root list -->
<YAMAHA_AV cmd="GET">
  <SERVER>
    <List_Info>GetParam</List_Info>
  </SERVER>
</YAMAHA_AV>

<!-- 3. Navigate: Server -> Music -> By Artist -> Artist Name -> Album -->
<YAMAHA_AV cmd="PUT">
  <SERVER>
    <List_Control>
      <Direct_Sel>Line_1</Direct_Sel>
    </List_Control>
  </SERVER>
</YAMAHA_AV>
<!-- Repeat navigation steps as needed -->

<!-- 4. Play selected track -->
<YAMAHA_AV cmd="PUT">
  <SERVER>
    <List_Control>
      <Direct_Sel>Line_1</Direct_Sel>
    </List_Control>
  </SERVER>
</YAMAHA_AV>

<YAMAHA_AV cmd="PUT">
  <SERVER>
    <Play_Control>
      <Playback>Play</Playback>
    </Play_Control>
  </SERVER>
</YAMAHA_AV>
```

## Implementation Notes

### Home Assistant Integration Specifics

1. **Async Operations**: All API calls should be async to prevent blocking
2. **Error Recovery**: Implement retry logic for network timeouts
3. **State Management**: Cache current source and playback state
4. **Media Browser**: Use hierarchical BrowseMedia objects for SERVER browsing
5. **Polling**: Update status every 30-60 seconds for current media info

### Performance Considerations

1. **Rate Limiting**: Don't send requests faster than every 200ms
2. **Busy Handling**: Always check Menu_Status before proceeding
3. **Connection Pooling**: Reuse HTTP connections when possible
4. **Caching**: Cache navigation state to reduce API calls

### Security Considerations

1. **Local Network Only**: R-N301 should only be accessible on local network
2. **No Authentication**: The API has no built-in authentication
3. **Input Validation**: Validate all user inputs before sending to receiver
4. **Error Logging**: Log errors without exposing sensitive information

## Changelog

- **v1.4.1**: Added intelligent media type detection based on menu layer and names
- **v1.4.0**: Added comprehensive SERVER media browsing support
- **v1.3.0**: Added NET RADIO browsing and TUNER preset support
- **v1.2.0**: Initial API documentation and Home Assistant integration