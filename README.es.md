# Imprimir Ender

Programa para Windows (Python + tkinter) que **lamina, organiza e imprime** en la **Creality Ender-3 V3 SE** directamente por USB, con mesa 3D, impresión a color manual, editor de piezas, vigilancia por cámara con IA, página para el móvil y un **servidor MCP** para que una IA (Claude, Cursor, etc.) controle todo.

**Leer en:** [Português](README.md) · [English](README.en.md) · Español · [Русский](README.ru.md)

> La interfaz está en **portugués, inglés, español y ruso**.

## Estado: fase de pruebas

Lo que ya se usa en la práctica y funciona: imprimir (laminar con CuraEngine, enviar por USB, PARAR), la mesa 3D, la página del móvil y el servidor MCP.

**Aún NO probado de verdad en la impresora** (el código existe, pero está en pruebas): impresión a color con cambio de filamento, pruebas de diagnóstico, editor de piezas, importación de 3MF en color, creación de piezas con Zoo y vigilancia por cámara con IA. Solo se verificaron con una impresora simulada. Tenga la impresora a la vista y espere ajustes. Se agradecen reportes y correcciones.

## Recursos

**Imprimir**
- Abre STL o G-code, lamina con CuraEngine (ABS completo, ABS rápido, PLA), muestra tiempo y costo.
- Envía el G-code línea por línea esperando el `ok`; si hay error apaga boquilla y cama. Botón PARAR siempre disponible.
- Inicio seguro: cama primero, G28, carga el mapa de nivelación guardado, ventilador según el material.
- Pausa, continuar, cambio de filamento (M600), sensor de filamento, cola de impresión.
- Encuentra el puerto de la impresora solo.

**Mesa 3D**
- Varias piezas: mover, girar, escalar, copiar, organizar automático, llenar la mesa.
- Visor 3D propio que también muestra los **soportes**.
- Importa **3MF en color** (PrusaSlicer, Bambu/Orca en mejor esfuerzo, 3MF estándar): cada parte es una pieza con su color.
- "Imprimir solo un color": un color a la vez, cambia el filamento y repite.
- Soportes: árbol o normal, patrón, densidad, distancia Z/XY, techo.

**Impresión a color manual**
- Define cambios de color por capa; el programa pausa, lleva la boquilla a la esquina, descarga/carga filamento y espera.

**Editor de piezas** (pestaña propia)
- Agujero, corte por plano, formas (sumar/restar), texto en relieve o grabado en 5 caras, polígonos a mano, deshacer, volver al original. Nunca cambia el archivo original: guarda una copia en `pecas_editadas`.

**Crear pieza por texto (Zoo)**
- Genera una pieza desde una descripción con Zoo (zoo.dev). Necesita su propia clave y el permiso marcado en la pestaña.

**Pruebas de la impresora**
- 12 pruebas: comunicación, termistores, finales de carrera, sensor de filamento, tarjeta SD, pantalla, ventilador, CR Touch, calentar boquilla, calentar cama, motores, extrusor. Las que calientan o mueven piden permiso y al final se apagan los calentadores.

**Vigilancia por cámara**
- Foto de la impresora cada cierto tiempo (cámara IP) enviada a una IA (JEV, OpenAI o Gemini; usted elige el modelo) para detectar fallos. Avisos Pushover opcionales.

**Otros**
- Nivelación con cama tibia, calibración, costo del rollo, historial, time-lapse, pestaña Manual.
- **App en red para el móvil** (PWA, 4 idiomas): estado, colores, cámara, mesa y botón PARAR, protegida por token.
- Servidor HTTP local (puertos 8101-8110) con la API que usa el MCP.

## MCP (controlar el programa con una IA)

`mcp_ender/server.py` ofrece **61 herramientas**: estado, imprimir (pide confirmación), mesa 3D, colores, edición de piezas (la IA puede *ver* la pieza), diagnóstico, Zoo, modo avanzado, cámara y vigilancia. Lista completa en [`mcp_ender/MANUAL_MCP.md`](mcp_ender/MANUAL_MCP.md) (portugués).

No habla con la impresora directamente: llama a la API del programa, así que los bloqueos de seguridad también valen para la IA. En la pestaña **IA / MCP** genera/copia el token, copia el comando para Claude Code o el JSON para otros clientes, y puede activar el modo **solo lectura**.

## Instalación

1. Windows con Python 3.12.
2. Instale [UltiMaker Cura](https://ultimaker.com/software/ultimaker-cura/) (se usa su CuraEngine; **no** viene en este repositorio). La ruta está en `base_ender.py` (`CURA = ...`).
3. `pip install -r requirements.txt`
4. Conecte la impresora por USB y ejecute `Imprimir_Ender.bat` (o `pythonw imprimir_ender.py`).

Otras impresoras Marlin similares pueden funcionar editando `perfil_impressora.json` y los presets de `base_ender.py`.

## Seguridad y privacidad

- Las claves de IA (JEV/OpenAI/Gemini/Zoo) y el token de red están en archivos `_PRIVADO_*` creados en su PC, **ignorados por git**. Nunca los publique.
- El programa nunca usa una clave que usted no haya puesto.
- **La IA solo imprime con tu orden**: `ender_imprimir` exige `confirmo=true`; `ender_peca_criar` y las pruebas que calientan o mueven también piden permiso explícito. El botón PARAR y el modo **solo lectura** valen también para la IA.
- **Solo habla con tu red**: el MCP solo llama a la API local del programa (`ENDER_URL`, por defecto `http://127.0.0.1:8101`) con tu token; no envía datos a terceros.
- **Herramientas anotadas**: cada herramienta del MCP declara `readOnlyHint` (solo lee) o `destructiveHint` (puede calentar, mover, imprimir, borrar).
- Pruebas: `python -m pytest tests`; ninguna usa la impresora.

## Traducir a otro idioma

`python traduzir_idiomas.py --codigo fr --nome "Français"` traduce los textos con la API de Claude (modelo barato, por lotes; requiere `ANTHROPIC_API_KEY`). `--simular` muestra el costo sin llamar. Luego añada el idioma en `i18n.IDIOMAS`. Límites: los valores de listas desplegables y algunos mensajes dinámicos siguen en portugués.

## Limitaciones conocidas

- Solo escala uniforme; las piezas mayores que la mesa (220 x 220 mm) se rechazan.
- 3MF de Bambu/Orca no probado con archivos reales.
- La impresión a color es manual (cambio de filamento), no multimaterial automático.

## Comunidad

¿Dudas, ideas o quiere mostrar su impresión? Únase al grupo de WhatsApp: https://chat.whatsapp.com/Jn09rWfySDpDnSkwaIcdDH

Se aceptan issues y contribuciones en GitHub.

## Licencia

MIT (ver `LICENSE`). CuraEngine es AGPL y se usa como programa externo instalado por usted.

Por [Edita Código](https://editacodigo.com.br).
