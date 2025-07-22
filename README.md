# Home Assistant Yamaha R-N301 Integration

This custom component for Home Assistant provides integration with the Yamaha R-N301 network receiver, enabling control of various functions like power, volume, source selection, and media playback.

**Updated for Home Assistant 2025.10+** - This integration has been modernized with config flow support, async HTTP calls, and compatibility with the latest Home Assistant versions.

## Features

- **Power Control**: Turn your receiver on or off
- **Volume Control**: Adjust the volume and mute state
- **Source Selection**: Choose between inputs like Optical, CD, Line, and more
- **Media Playback**: Control media playback including play, pause, stop, and track navigation
- **Enhanced Media Information**: Display track info, station names, and frequencies
- **TUNER Preset Support**: Switch between radio presets using next/previous buttons (works even without signal lock)
- **NET RADIO Browse Media**: Browse and select internet radio stations directly in Home Assistant
- **Config Flow**: Easy setup through Home Assistant UI with connection testing
- **IP Address Management**: Change receiver IP address through Home Assistant UI (Settings → Configure)
- **Unique Entity ID**: Full UI management support for device settings
- **Modern Architecture**: Fully async implementation compatible with Home Assistant 2025.10+

## Installation

### Method 1: HACS (Home Assistant Community Store) - Recommended

1. Install [HACS](https://hacs.xyz/) if you haven't already
2. In HACS, go to **Integrations**
3. Search for "Yamaha R-N301" and click **Download**
4. Restart Home Assistant
5. Go to **Settings** → **Devices & Services** → **Integrations**
6. Click **Add Integration** and search for "Yamaha R-N301"
7. Enter your receiver's IP address and optional name

> 🎉 **Now available in HACS default repositories!** No need to add custom repository URL anymore.

### Method 2: Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/rn301` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant
4. Go to **Settings** → **Devices & Services** → **Integrations**
5. Click **Add Integration** and search for "Yamaha R-N301"
6. Enter your receiver's IP address and optional name

### Method 3: Legacy YAML Configuration

1. Install using Method 1 or 2 above
2. Add the following to your `configuration.yaml`:

   ```yaml
   media_player:
     - platform: rn301
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
  - **Full Control**: Spotify, Net Radio, Server (play/pause/stop/skip/shuffle)
  - **TUNER Control**: Power, volume, source, preset switching via next/previous track buttons
  - **Basic Control**: Optical, CD, Line inputs (power/volume/source only)

## Configuration Options

When using the UI configuration flow, you can set:
- **Host**: IP address of your Yamaha R-N301 (required, can be changed later)
- **Name**: Custom name for the device (optional, defaults to "Yamaha R-N301", can be changed later)

**Changing Configuration Later:**
You can modify the IP address and device name anytime through:
1. Go to **Settings** → **Devices & Services**
2. Find your Yamaha R-N301 integration
3. Click **Configure**
4. Update IP address and/or name
5. The integration will automatically reload with new settings

## Supported Models

This integration is developed for the Yamaha R-N301 but might work with other Yamaha receivers with similar XML control APIs.

## Compatibility

- **Home Assistant**: 2022.3.0 or later
- **Home Assistant Core**: 2025.10+ (with modernized features)
- **Python**: 3.9 or later
- **Network**: Receiver must be accessible via HTTP on your local network

## Recent Updates

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

**Setup Problems:**
- Try restarting Home Assistant after installation
- Check the Home Assistant logs for error messages
- Ensure no firewall is blocking HTTP requests to the receiver

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with Yamaha Corporation and is a community-driven project. Use at your own risk.
