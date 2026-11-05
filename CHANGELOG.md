# Development changelog

This log summarizes the supplied local development reports. Commit identifiers refer to local development history; the website repository does not automatically contain those commits or the game code. Individual commit dates were not supplied.

## Latest reported milestone — `3555ea1` and `5971bd8`

- Corrected an incorrectly used write view for an sRGB texture.
- Displayed actual game video, the title screen, and the main menu in the tested startup path.
- Successfully tested opening the options menu and returning.
- Reduced Vulkan errors from **2 to 0** in the tested startup and menu path.
- Reduced shader error messages from **464 to 203**; remaining messages were documented.
- Reported **3,000 Vulkan presentations** followed by normal shutdown.
- Reported 13 runtime checks, 17 existing tests, and additional regression tests as passing.

The reported graphics test used a Radeon RX 7900 XTX. Controllable 3D gameplay, complete playability, and saving/loading remain unverified.

## Earlier reported milestone — `13c6c0e`

- Addressed all 58 outstanding PACGA sites.
- Added AV1 decoding.
- Linked the translated game code with the Windows runtime.
- Fixed a reproduced thread-switch crash and a shutdown hang.
- Reached 600 counted frames in an initial run, which still showed a black screen.

The reported foundation work also included native compilation of 551 generated C files and Debug and Release builds of the Windows test runtime.

## Reading the figures

Shader message counts do not necessarily identify distinct shaders or root causes. Earlier frame counts and later Vulkan presentation counts are different measurements. Neither demonstrates playable 3D gameplay or a particular frame rate.

[Back to the project overview](README.md)
