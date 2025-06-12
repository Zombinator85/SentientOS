# SentientOS Avatar Demo

This Unity scene demonstrates driving a blend-shape slider using OSC.

## Running the OSC Pump
1. Install the `python-osc` package:
   ```bash
   pip install python-osc
   ```
2. Start the emotion pump from the repository root:
   ```bash
   python scripts/osc_emotion_pump.py
   ```
   By default it sends `/emotions` messages to `127.0.0.1:9001`. You can set `OSC_HOST` and `OSC_PORT` environment variables to change the target.

## Connecting in Unity
1. Open `BlendShapeSlider.unity` in the `SentientOSAvatar` folder.
2. Press Play. The slider will respond to incoming OSC `/emotions` vectors.

The scene uses the free [Unity OSC](https://github.com/jorgegarcia/UnityOSC) package to parse messages.
