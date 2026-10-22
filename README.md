# Home Assistant Yamaha R-N301 Integration

This custom component for Home Assistant provides integration with the Yamaha R-N301 network receiver, enabling control of various functions like power, volume, source selection, and media playback.

**Requires Home Assistant 2024.11 or later** (tested with 2026.10). Set up from the UI, with automatic discovery of the receiver on your network.

## Features

- **Power Control**: Turn your receiver on or off
- **Volume Control**: Adjust the volume, step it up or down, and mute
- **Source Selection**: Choose between inputs like Optical, CD, Line, and more
- **Media Playback**: Control media playback including play, pause, stop and track navigation, and shuffle and repeat for the Server input
- **Enhanced Media Information**: Display track info, station names, and frequencies
- **TUNER Preset Support**: Switch between the presets stored on the receiver using next/previous buttons (works even without signal lock)
- **Media Server Browsing**: Browse DLNA media servers (SERVER input) and play tracks directly in Home Assistant
- **NET RADIO Browse Media**: Browse and select internet radio stations directly in Home Assistant
- **Automatic Discovery**: Home Assistant finds the receiver on your network (SSDP) and offers to add it
- **Follows IP Changes**: When the receiver gets a new IP address from DHCP, Home Assistant updates it automatically
- **Config Flow**: Easy setup through Home Assistant UI with connection testing
- **Device Registry**: The receiver shows up as a device; the entity keeps its ID when settings change

## Installation

### Method 1: HACS (Home Assistant Community Store) - Recommended

1. Install [HACS](https://hacs.xyz/) if you haven't already
2. In HACS, go to **Integrations**
3. Search for "Yamaha R-N301" and click **Download**
4. Restart Home Assistant
5. Go to **Settings** → **Devices & Services** → **Integrations**
6. The receiver is usually discovered automatically: click **Add** on the discovered Yamaha R-N301. Otherwise click **Add Integration**, search for "Yamaha R-N301" and enter the receiver's IP address and an optional name

> 🎉 **Now available in HACS default repositories!** No need to add custom repository URL anymore.

### Method 2: Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/yamaha_rn301` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant
4. Go to **Settings** → **Devices & Services** → **Integrations**
5. Click **Add Integration** and search for "Yamaha R-N301"
6. Enter your receiver's IP address and optional name

### Method 3: Legacy YAML Configuration

1. Install using Method 1 or 2 above
2. Add the following to your `configuration.yaml`:

   ```yaml
   media_player:
     - platform: yamaha_rn301
       host: YOUR_RECEIVER_IP
       name: Yamaha R-N301
   ```

3. Replace `YOUR_RECEIVER_IP` with your receiver's IP address
4. Restart Home Assistant

## Usage

Once installed and configured, the Yamaha R-N301 will appear as a media player entity in Home Assistant. You can:

- Use the Lovelace UI to control power, volume, source selection, and media playback
- Create automations and scripts using the media player services
- Access different input sources with varying capabilities:
  - **Server**: Browse and play tracks; play/pause/stop/skip, shuffle and repeat
  - **Spotify, AirPlay**: Play/pause/stop/skip
  - **Net Radio**: Browse and play stations (see [NET RADIO After the vTuner Shutdown](#net-radio-after-the-vtuner-shutdown))
  - **TUNER Control**: Power, volume, source, preset switching via next/previous track buttons
  - **Basic Control**: Optical, Coaxial, CD, Line inputs (power/volume/source only)

## NET RADIO After the vTuner Shutdown

The receiver's built-in internet radio used the vTuner service, which no longer serves the R-N301. You can bring it back with [YCast](https://github.com/milaq/YCast), a self-hosted vTuner replacement that lists stations from the [Radio Browser](https://www.radio-browser.info/) directory. This was tested with an R-N301 (firmware 1.13/0.05):

1. Install the YCast app: add the repository `https://github.com/casperklein/homeassistant-addons` under **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, then install and start **YCast**. It listens on port 80 of your Home Assistant host.
2. Point `radioyamaha.vtuner.com` and `radioyamaha2.vtuner.com` to your Home Assistant host's IP address in the DNS server **the receiver uses**. Check the receiver's network settings: if it uses another DNS server than your router (for example a Pi-hole or a domain controller), add the records there.
3. Select the NET RADIO input. The receiver's menu, the remote and the Home Assistant media browser now show **Radiobrowser** (by genre, country, language and popularity) and **My Stations**.

Notes:
- The receiver cannot play HTTPS streams. Stations that only offer HTTPS (or redirect HTTP to HTTPS) are skipped, and the receiver plays the next working station in the list instead.
- Radio Browser lists change over time. Stations are found again by name, but a station that is removed from Radio Browser can no longer be played. For automations it is simplest to add your stations as YCast bookmarks, which show directly under **My Stations**. In the YCast app options, bookmarks look like this:

  ```yaml
  bookmarks:
    - "Vikerraadio: http://icecast.err.ee/vikerraadiokorge.mp3"
    - "Raadio 2: http://icecast.err.ee/raadio2korge.mp3"
  ```


When using the UI configuration flow, you can set:
- **Host**: IP address of your Yamaha R-N301 (required, can be changed later)
- **Name**: Custom name for the device (optional, defaults to "Yamaha R-N301", can be changed later)

**Changing Configuration Later:**
If the receiver gets a new IP address, Home Assistant normally picks it up automatically through discovery. You can also modify the IP address and device name anytime through:
1. Go to **Settings** → **Devices & Services**
2. Find your Yamaha R-N301 integration
3. Click **Configure**
4. Update IP address and/or name
5. The integration will automatically reload with new settings

## Supported Models

This integration is developed for the Yamaha R-N301 but might work with other Yamaha receivers with similar XML control APIs.

## Compatibility

- **Home Assistant**: 2024.11.0 or later (tested with 2026.10)
- **Network**: Receiver must be accessible via HTTP on your local network

## Recent Updates

### Unreleased
- **IMPROVED**: A command the receiver does not carry out now fails with a message instead of silently doing nothing, for example "The receiver is in standby" or "Cannot reach the receiver"
- **FIXED**: Commands sent right after turning the receiver on, for example setting the volume in the same automation, were refused while it started up. They are now sent again for up to 3 seconds
- **FIXED**: Shuffle is no longer offered for Spotify and AirPlay; the receiver has no shuffle for these inputs
- **FIXED**: Play after Stop on the Server input did nothing, because the receiver ignores it. The integration now selects the last track again
- **FIXED**: Next and previous on the Tuner step through the presets stored on the receiver. They counted 1 to 8 before and got stuck when fewer presets were stored
- **FIXED**: After selecting an input, the old input could be shown for up to 10 seconds, so a command right after it, such as next on the Tuner, went to the old input. Presets selected right after switching to the Tuner, which it ignores for a moment, now wait until it takes them
- **DOCS**: The API reference was checked against a real R-N301 and corrected: response codes, power, inputs, playback per input, list timing and the Tuner

### Version 1.5.2 - Continuous Browsing
- **IMPROVED**: NET RADIO and Server folders open as one continuous list instead of pages of 8. The receiver delivers 8 entries per 0.5–1 s, so a list opened for the first time shows its first entries within about 2 seconds, reads the rest in the background, and offers "Show all". Lists are kept (also across restarts) and open at once from then on; lists older than 10 minutes are refreshed in the background when opened
- **IMPROVED**: Station and track IDs include the name, so a station is found even after its position in a Radio Browser list changed, e.g. when played from an automation
- **IMPROVED**: Moving up uses the media browser's own back button instead of a "Back" entry in the list
- **IMPROVED**: A level that holds only one folder is skipped, so YCast bookmarks show directly under "My Stations"
- **FIXED**: Playing a station checks that the receiver shows the expected list by name, not only by menu depth
- **FIXED**: Jumps the receiver ignored or answered late made reading long lists fail or could select an item on the wrong page
- **FIXED**: The volume sent to the receiver is kept within its 0–100 range, which it otherwise rejects (thanks @Neubda, #6)

### Version 1.5.1 - NET RADIO Browsing
- **FIXED**: NET RADIO browsing read the list before the receiver finished loading it, showed only the first 8 entries, and did not return to the main menu. It now uses the same browsing as the Server input: pages, back navigation and waiting for the receiver
- **FIXED**: Playing a saved station or track (for example from an automation) now navigates to it even when the receiver's menu is somewhere else
- **IMPROVED**: The NET RADIO station name is shown as the media channel, with the current song as the title
- **DOCS**: How to bring NET RADIO back after the vTuner shutdown with YCast

### Version 1.5.0 - Discovery, Reliability and Modernization
- **NEW**: Automatic discovery over SSDP. When the receiver gets a new IP address from DHCP, the configured entry is updated automatically
- **NEW**: Repeat (off/one/all) for the Server input
- **NEW**: Volume up/down steps
- **NEW**: The receiver is added to the device registry. An area set on the entity is moved to the device, as Home Assistant now expects
- **FIXED**: Added missing AirPlay and Coaxial inputs. Selecting either input previously froze the entity with "Error during update: 'AirPlay'" in the log (thanks @Neubda, #5)
- **FIXED**: Unknown inputs reported by the receiver fall back to their raw name instead of breaking updates
- **FIXED**: Mute did nothing (the command was sent to the wrong zone and rejected by the receiver)
- **FIXED**: Shuffle now sends the correct command and shows the correct state; it is no longer offered for passive inputs
- **FIXED**: Album names are now shown
- **FIXED**: Media server folders and tracks past the first page opened the wrong item
- **FIXED**: Browsing a media server that is still waking up no longer fails after 2.5 seconds; a clear error is shown if it does not respond
- **FIXED**: The entity becomes unavailable when the receiver cannot be reached for 3 polls in a row, instead of keeping its last state forever; the outage is logged once
- **FIXED**: Adding an already configured receiver aborts with "already configured" instead of "Unknown error"
- **FIXED**: Changing only the name in the options is saved; changing the host no longer creates a new entity (existing entities are migrated and keep their entity ID)
- **FIXED**: Volume levels are rounded instead of truncated (29% no longer becomes 28%)
- **IMPROVED**: Paused playback is shown as "paused"; media server titles with "&" are shown correctly
- **IMPROVED**: English and Estonian translations; brand icon shown in Home Assistant
- **CHANGED**: Minimum Home Assistant version is 2024.11.0
- **TECHNICAL**: Uses current Home Assistant media player APIs (MediaPlayerState, device class, entity naming); tests with a simulated receiver

### Version 1.4.2 - Media Browsing Standards Compliance
- **FIXED**: Updated media browsing to use MediaClass instead of MediaType for proper Home Assistant standards compliance
- **IMPROVED**: NET RADIO browsing now uses MediaClass.DIRECTORY for folders and MediaClass.TRACK for stations
- **IMPROVED**: SERVER browsing now uses MediaClass.DIRECTORY/ALBUM for containers and MediaClass.TRACK for playable items
- **ENHANCED**: Intelligent media class selection - albums use MediaClass.ALBUM, other folders use MediaClass.DIRECTORY
- **TECHNICAL**: Follows Home Assistant's media player integration standards where MediaClass categorizes browsing hierarchy and MediaType identifies playback content type

### Version 1.4.1 - Code Refactoring and Cleanup
- **IMPROVED**: Major code quality improvements with ~250 fewer lines
- **REFACTORED**: Eliminated duplicate XML parsing logic (saved ~135 lines)
- **REFACTORED**: Added helper methods for pagination and navigation controls
- **REFACTORED**: Created factory methods for cleaner BrowseMedia object creation
- **CLEANED**: Removed redundant debug logging for better performance
- **TECHNICAL**: Simplified navigation path management system
- **TECHNICAL**: Better code organization and maintainability

### Version 1.4.0 - SERVER Media Browsing Release
- **NEW**: Full SERVER media browsing support with folder navigation
- **NEW**: Pagination controls for large media libraries  
- **NEW**: Back navigation and breadcrumb support
- **IMPROVED**: Enhanced media metadata display for SERVER content
- **IMPROVED**: Better error handling for network timeouts
- **TECHNICAL**: Modernized code for Home Assistant 2025.x compatibility

### Version 1.3.0
- **IP Address Management**: Change receiver IP address through Home Assistant UI without removing/re-adding integration
- **Unique Entity ID**: Added unique_id property for full UI management support
- **Enhanced TUNER Controls**: Preset navigation buttons now work even when frequency is not locked (weak signals)
- **Performance Improvements**: Eliminated duplicate API calls and optimized preset detection
- **Code Modernization**: Removed deprecated config_entry assignment warnings for Home Assistant 2025.12+ compatibility
- **Code Cleanup**: Streamlined codebase with better error handling and reduced logging overhead

### Version 1.2.1
- 🐛 **Bug Fix**: Fixed volume control mapping between Home Assistant and receiver
- 🔧 **Volume Scaling**: Corrected volume conversion to properly map 0-100% range

### Version 1.2.0
- ✅ **TUNER Preset Support**: Switch between 8 radio presets using next/previous track buttons
- ✅ **Enhanced Media Information**: Display station names, program info, and frequencies for TUNER source (e.g., "#4 RAADIO 2 • FKA TWIGS - Striptease_ (FM 101.6 MHz)")
- ✅ **NET RADIO Browse Media**: Browse and select internet radio stations directly in Home Assistant
- ✅ **Fully Async Implementation**: Complete conversion to async/await for better performance
- ✅ **Improved API Communication**: Better error handling and XML parsing
- ✅ **Modern MediaType Support**: Updated to use latest Home Assistant MediaType enum

### Version 1.1.0
- ✅ **Config Flow Support**: Easy setup through Home Assistant UI
- ✅ **Connection Testing**: Automatic validation during setup
- ✅ **Modern APIs**: Updated for Home Assistant 2025.10+ compatibility
- ✅ **Async HTTP**: Non-blocking HTTP calls in config flow
- ✅ **Improved Error Handling**: Better logging and error messages
- ✅ **Code Modernization**: English comments and updated architecture
- ✅ **HACS Compatible**: Easy installation through HACS custom repositories
- ✅ **Better Documentation**: Comprehensive README with multiple installation methods

## Troubleshooting

**Connection Issues:**
- Ensure your receiver is on the same network as Home Assistant
- Check that the IP address is correct and accessible
- Verify the receiver's network settings are properly configured

**A Command Fails With a Message:**
- "The receiver is in standby": turn the receiver on first. Volume, mute, playback and browsing need it on.
- "Cannot reach the receiver": check that the receiver is connected and its IP address is correct.
- "The receiver does not accept this value": the receiver refused the value, for example an input it does not have.

**Setup Problems:**
- Try restarting Home Assistant after installation
- Check the Home Assistant logs for error messages
- Ensure no firewall is blocking HTTP requests to the receiver

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes and run the tests (`pip install -r requirements_test.txt && pytest`)
4. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with Yamaha Corporation and is a community-driven project. Use at your own risk.
