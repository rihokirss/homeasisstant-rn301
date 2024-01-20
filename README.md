# Home Assistant Yamaha R-N301 Integration

This custom component for Home Assistant provides integration with the Yamaha R-N301 network receiver, enabling control of various functions like power, volume, source selection, and media playback.

## Features

- **Power Control**: Turn your receiver on or off.
- **Volume Control**: Adjust the volume and mute state.
- **Source Selection**: Choose between inputs like Optical, CD, Line, and more.
- **Media Playback**: Control media playback including play, pause, stop, and track navigation.
- **Media Information**: Display information about the currently playing track.

## Installation

1. Clone or download this repository.
2. Copy the `rn301` folder to your Home Assistant `custom_components` directory.
3. Restart Home Assistant.
4. Add the following configuration to your `configuration.yaml`:

   ```yaml
   media_player:
     - platform: rn301
       host: YOUR_RECEIVER_IP
       name: Yamaha R-N301
   
Replace `YOUR_RECEIVER_IP` with the IP address of your Yamaha R-N301.

## Usage

Once installed and configured, the Yamaha R-N301 will appear as a media player entity in Home Assistant. You can use the Lovelace UI to control it or automate its functions using Home Assistant scripts.

## Supported Models

This integration is developed for the Yamaha R-N301 but might work with other Yamaha receivers with similar APIs.

## Contributing

If you'd like to contribute to this project, please fork the repository and submit your changes as a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with Yamaha Corporation and is a community-driven project. Use at your own risk.
