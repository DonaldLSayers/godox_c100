# Updating the annoying sounds on my Godox C100

I'm not that much of a firmware tinkerer, but AI had no problem helping me do it XD

It helped a lot that the firmware and instructions to flash it are published: https://www.godox.com/product-e/C100.html

The firmware at this time is in `Godox_C100_V1.1.6.zip` (and extracted to `c100_v1.1.6_20260929/`).

It turns out it runs on a GeneralPlus (GP22B) chip, an ARM processor running FreeRTOS that is apparently often used for cheap dashcams and kids’ cameras and other gadgets like these.

Then, I downloaded my favorite two sounds from Super Mario from https://themushroomkingdom.net/media/smb/wav — Kick and Coin.

I let AI compress them, shorten them, and fade the longer Coin out, creating `build/{kick,coin}_11k.wav`

Then:

```sh
python3 tools/patch_res.py c100_v1.1.6_20260929/GP_CARDVR_UPGRADE.BIN CAMERA.wav build/kick_11k.wav build/GP_CARDVR_UPGRADE.BIN
CAMERA.wav: wrote 4040/7168 B at 0x171e00; 6288 bytes changed, all inside the slot -> build/GP_CARDVR_UPGRADE.BIN
python3 tools/patch_res.py build/GP_CARDVR_UPGRADE.BIN POWERON_AUDIO.wav build/coin_11k.wav build/GP_CARDVR_UPGRADE.BIN
POWERON_AUDIO.wav: wrote 16362/16384 B at 0x1b0400; 15715 bytes changed, all inside the slot -> build/GP_CARDVR_UPGRADE.BIN
```

Finally, flash the new firmware: place the `GP_CARDVR_UPGRADE.BIN` in the root of the SD, turn it back on, wait for it to flash, it automatically restarts, done ☺️
