# Imprimir Ender

A Windows program (Python + tkinter) that **slices, arranges and prints** on the **Creality Ender-3 V3 SE** straight over USB, with a 3D bed, manual colour printing, a part editor, a camera "watchdog" with AI, a phone web page and an **MCP server** so an AI (Claude, Cursor, etc.) can control everything.

**Read in:** [Português](README.md) · English · [Español](README.es.md) · [Русский](README.ru.md)

> The interface comes in **Portuguese, English, Spanish and Russian**.

## Status: testing phase

What is already used in practice and works: printing (slicing with CuraEngine, sending over USB, STOP), the 3D bed, the phone page and the MCP server.

**NOT yet really tested on the printer** (the code exists but is still being tested): colour printing with filament changes, hardware diagnostic tests, the part editor, coloured 3MF import, part creation through Zoo and the AI camera watchdog. These were only checked against a simulated printer. Keep the printer in sight and expect adjustments. Reports and fixes are welcome.

## Features

**Printing**
- Opens STL or G-code, slices with CuraEngine (presets: ABS full, ABS fast, PLA), shows time and cost.
- Sends G-code line by line waiting for `ok`; on error it turns off nozzle and bed. A STOP button is always available.
- Safe start: bed first, G28, loads the saved levelling mesh, fan according to material.
- Pause, resume, filament change (M600), filament sensor, print queue.
- Finds the printer's port by itself.

**3D bed**
- Several parts, move/rotate/scale/copy, auto-arrange, fill the bed.
- Own 3D viewer (software renderer) that also shows the **supports**.
- Imports **coloured 3MF** (PrusaSlicer, Bambu/Orca best effort, standard 3MF): each part becomes an object with its colour.
- "Print only one colour": print one colour at a time, swap filament, repeat.
- Supports: tree or normal, pattern, density, Z/XY distance, roof.

**Manual colour printing**
- Set colour changes per layer; the program pauses, parks the nozzle in the corner, unloads/loads filament and waits for you.

**Part editor** (own tab)
- Hole, plane cut, shapes (add/subtract), raised or engraved text on 5 faces, hand-drawn polygons, undo, back to original. The original file is never changed: a copy is saved in `pecas_editadas`.

**Create a part from text (Zoo)**
- Generates a part from a description using Zoo (zoo.dev). Needs your own key and the permission ticked in the tab.

**Printer tests**
- 12 tests: communication, thermistors, end stops, filament sensor, SD card, display, part fan, CR Touch, heat nozzle, heat bed, motors, extruder. Tests that heat or move ask permission and heaters are always switched off at the end.

**Camera watchdog**
- Takes a photo of the printer every few minutes (IP camera) and sends it to an AI (JEV, OpenAI or Gemini, you pick the model) to spot failures. Optional Pushover alerts.

**Other**
- Warm-bed levelling, calibration (temperature, retraction), spool cost, history, time-lapse, Manual tab.
- **Phone web app** (PWA, 4 languages): status, colours, camera, bed and a STOP button. Protected by a token.
- Local HTTP server (ports 8101-8110) with the API the MCP uses.

## MCP (control the program with an AI)

`mcp_ender/server.py` exposes **61 tools**: status, print (needs confirmation), 3D bed, colours, part editing (the AI can *see* the part), diagnostics, Zoo, advanced mode, camera and watchdog. Full list in [`mcp_ender/MANUAL_MCP.md`](mcp_ender/MANUAL_MCP.md) (Portuguese).

It does not talk to the printer directly: it calls the program's API, so the safety locks apply to the AI too. In the **IA / MCP** tab you generate/copy the token, copy the ready command for Claude Code or the JSON for other clients, and can enable **read-only** mode.

## Installation

1. Windows with Python 3.12.
2. Install [UltiMaker Cura](https://ultimaker.com/software/ultimaker-cura/) (the program uses its CuraEngine; it is **not** included here). The path is in `base_ender.py` (`CURA = ...`).
3. `pip install -r requirements.txt`
4. Connect the printer by USB and run `Imprimir_Ender.bat` (or `pythonw imprimir_ender.py`).

Other similar Marlin printers may work by editing `perfil_impressora.json` (bed size, purge corner) and the presets in `base_ender.py`.

## Security and privacy

- AI keys (JEV/OpenAI/Gemini/Zoo) and the network token live in `_PRIVADO_*` files created on your PC, **ignored by git**. Never publish them.
- The program never uses a key you did not enter.
- Regenerating the token invalidates the previous one.
- **The AI only prints on your order**: `ender_imprimir` requires `confirmo=true`; `ender_peca_criar` and the tests that heat or move also need explicit confirmation/permission. The STOP button and the **read-only mode** (IA / MCP tab) apply to the AI too.
- **Talks only to your network**: the MCP only calls the program's local API (`ENDER_URL`, default `http://127.0.0.1:8101`) with your token; it sends no data to third parties. Only the optional AI features (camera watch, Zoo) call external services, and only with the key you entered.
- **Annotated tools**: every MCP tool declares `readOnlyHint` (read only) or `destructiveHint` (may heat, move, print, delete), so the AI client can ask for confirmation on the dangerous ones.
- Tests: `python -m pytest tests` (see [`tests/README.md`](tests/README.md)); none of them uses the printer.

## Translating to another language

`python traduzir_idiomas.py --codigo fr --nome "Français"` translates all texts using the Claude API (cheap model, batched; needs `ANTHROPIC_API_KEY`). `--simular` shows the cost without calling. Then add the language to `i18n.IDIOMAS`. Known limits: dropdown values and some dynamic messages stay in Portuguese.

## Known limitations

- Uniform scale only; parts larger than the bed (220 x 220 mm) are refused.
- Bambu/Orca 3MF not tested with real files.
- Colour printing is manual (filament swap), not automatic multi-material.

## Community

Questions, ideas or want to show your print? Join the WhatsApp group: https://chat.whatsapp.com/Jn09rWfySDpDnSkwaIcdDH

Issues and contributions here on GitHub are welcome.

## License

MIT (see `LICENSE`). CuraEngine is AGPL and is used as an external program that you install.

By [Edita Código](https://editacodigo.com.br).
