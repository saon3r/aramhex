# Third-party components and data

The application includes the following components under their respective licences:

| Component | Purpose | Licence |
|---|---|---|
| [Qt for Python (PySide6)](https://www.qt.io/qt-for-python) | Interface | LGPL-3.0; distributed as separate, replaceable dynamic libraries |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) and its PaddleOCR models | Text recognition | Apache-2.0 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | OCR model execution | MIT |
| [OpenCV](https://opencv.org/) | Image processing | Apache-2.0 |
| [NumPy](https://numpy.org/) | Numerical computation | BSD-3-Clause |
| [Pillow](https://python-pillow.org/) | Image processing | MIT-CMU |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | Fuzzy name matching | MIT |
| [python-mss](https://github.com/BoboTiG/python-mss) | Screen capture | MIT |
| [Requests](https://requests.readthedocs.io/) | HTTP requests | Apache-2.0 |
| [PyInstaller](https://pyinstaller.org/) | Packaging | GPL-2.0 with bootloader exception; does not change this application's licence |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Installer | Inno Setup License |

## Code and data attribution

- Upstream application: [czgreat/aramhex](https://github.com/czgreat/aramhex), MIT. Keep `LICENSE` and its copyright notice.
- `lolhex/data/bundled/`: Chinese-server statistics from [czgreat/aramhex-data](https://github.com/czgreat/aramhex-data), CC BY-NC 4.0. Personal, non-commercial use with attribution.
- `lolhex/data/hero_aliases.json`: aliases compiled from Hexdata (hexdata.com.cn).
- `lolhex/data/hero_nicknames.json`: manually compiled community nicknames.
- Runtime champion/item metadata and portraits come from Riot's Data Dragon; augment metadata comes from CommunityDragon. `static_fallback.json` records the pinned sources and hashes used for offline fallback. Game names, artwork and metadata belong to their respective rights holders, including Riot Games.
- Existing `hero_icons.json` contains legacy public Tencent portrait references; `client_icons.json` contains client portraits obtained through CommunityDragon. These bundled references remain for offline fallback and matching compatibility. The application does not contact Tencent to refresh them.
- Upstream official build, skill-order and unsupported letter-tier feeds have been removed. These data notices do not imply Riot endorsement or permission to publish an augment win-rate overlay.
