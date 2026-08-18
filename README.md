# StrikeWorks
StrikeWorks is a data extraction, validation, processing and model development tool for underwater passive sensor devices used in fish passage science.

Credit: 

Dr. Josh Norman (University of Hull)
Prof. Jeffrey Tuhtan (University of Talinn)

Copyright University of Hull (2026)

## Development

Environment: Python 3.13 (`.venv/`), PySide6.

Run the app:

```
.venv\Scripts\python.exe main.py
```

### Regenerating the UI

The layout lives in `main.ui` — edit it in Qt Designer (`.venv\Scripts\pyside6-designer.exe main.ui`).
`modules/ui_main.py` is **generated** from it and must never be edited by hand:

```
.venv\Scripts\pyside6-uic.exe main.ui -o modules\ui_main.py
```

After regenerating, change the resource import near the top of `modules/ui_main.py`
from `import resources_rc` back to:

```python
from . resources_rc import *
```

Icons and images are compiled from `resources.qrc`:

```
.venv\Scripts\pyside6-rcc.exe resources.qrc -o modules\resources_rc.py
```

## Licence

MIT — see `LICENSE`. The GUI is built on the PyDracula template by Wanderson M. Pimenta;
the project credit and link are available in the app under **Settings > About**.
