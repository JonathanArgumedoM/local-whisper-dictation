# TravelDesk Whisper 1.1.0

Dictado local para Windows 10/11 x64, con Whisper small en CPU/int8. El instalador y el ZIP incluyen Python, bibliotecas y modelo. No necesitas una API key ni conexión a internet para dictar.

Este repositorio contiene el código fuente de la versión 1.1.0 para revisión técnica. Los instaladores, modelos, herramientas descargadas, respaldos y archivos de uso local no forman parte del repositorio. `config.json` incluye una configuración de ejemplo sin vocabulario de clientes. Clonar el repositorio requiere instalar las dependencias y descargar el modelo antes del primer dictado.

## Instalar en otra computadora

1. Ejecuta TravelDeskWhisper-Setup-1.1.0-windows-x64.exe.
2. Sigue el asistente. Se instala para tu usuario, sin permisos de administrador.
3. Abre TravelDesk Whisper desde el escritorio o el menú Inicio.
4. Espera unos segundos mientras carga el modelo local.

Necesitas un micrófono y permisos de Windows para que las aplicaciones de escritorio lo utilicen. Esta distribución no se ha validado en ARM ni en macOS.

Para usar el ZIP portable, extrae toda la carpeta y abre TravelDeskWhisper.exe. Conserva _internal, models y config.json junto al ejecutable.

## Dictar

Coloca el cursor donde quieres escribir, mantén Ctrl+Espacio, habla y suelta para transcribir y pegar. Cada grabación se detiene a los 45 segundos.

El doble toque para manos libres está desactivado. La app permanece en la bandeja de Windows; desde su icono puedes consultar la ayuda, mostrar u ocultar la barra o salir. Doble clic sobre la barra la oculta; clic derecho abre la ayuda.

Puedes decir «nueva línea», «punto», «coma», «dos puntos», «abrir paréntesis» o «cerrar paréntesis». Nueva línea también funciona como único dictado. La frase «punto de venta» se conserva como texto literal. Los comandos admiten las variantes configuradas en inglés.

El dictado reemplaza el contenido del portapapeles para pegar el texto. El audio temporal se elimina al terminar la transcripción.

## Cambios de la versión 1.1.0

- CTranslate2 4.8.2 y sounddevice 0.5.6; faster-whisper permanece en 1.2.1.
- Comandos con acentos y mayúsculas; saltos de línea aislados.
- Recuperación al fallar la apertura o el cierre del micrófono: revisa o reconecta el dispositivo y vuelve a pulsar el atajo.
- Ayuda ajustada al proveedor, atajo y modo manos libres configurados.
- Modelo local incluido, instalador por usuario, accesos directos y desinstalador.
- Compilaciones en carpetas nuevas, dependencias fijadas y comprobación del ejecutable empaquetado.

## Configuración

Cierra la app antes de editar config.json y vuelve a abrirla después.

- transcription_provider: local por defecto; openai activa el proveedor de pago ya disponible.
- model_size: small está incluido. Otro modelo puede requerir descarga y más recursos.
- device y compute_type: cpu / int8. GPU requiere bibliotecas CUDA compatibles y pruebas adicionales.
- language: null detecta el idioma; es fija español.
- hotkey: ["ctrl", "space"]. Puede cambiarse, por ejemplo, a ["f8"].
- max_record_seconds: límite de cada grabación; predeterminado 45.
- enable_toggle_recording: false. Al activarlo, el doble toque inicia manos libres y el siguiente toque lo detiene.
- command_replacements, protected_phrases y custom_terms: comandos, frases literales y vocabulario personalizado.

OpenAI es opcional: requiere conexión, tu propia API key y genera cargos del proveedor. La app valida y guarda la llave solo si eliges ese modo. La distribución no contiene credenciales.

## Actualizar o desinstalar

Cierra la app desde la bandeja antes de ejecutar otra versión del instalador. Se conserva un config.json existente. Para desinstalar, usa Configuración de Windows > Aplicaciones > TravelDesk Whisper. Se eliminan la aplicación y el modelo incluido; se conservan la configuración y los archivos de usuario.

## Desarrollo

Usa Windows 10/11 x64 y Python 3.12 x64. Desde PowerShell:

```powershell
git clone https://github.com/JonathanArgumedoM/local-whisper-dictation.git
cd local-whisper-dictation
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.lock
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src\dictation_app.py
```

Las 18 pruebas cubren los comandos de puntuación, saltos de línea, frases protegidas y recuperación del micrófono. Usan simulaciones y no requieren grabar audio ni introducir una API key. No sustituyen una prueba manual de dictado y pegado en la aplicación de destino.

También puedes usar `install.bat` y `run.bat`. La ejecución desde código usa la caché de Hugging Face si el modelo no está junto a la aplicación: la primera carga del modelo requiere internet. Las siguientes cargas pueden funcionar sin conexión con el modelo ya descargado.

### Guía para revisar el código

| Archivo | Contenido |
| --- | --- |
| `src/dictation_app.py` | Atajo global, captura de micrófono, interfaz, transcripción local y proveedor opcional, comandos de texto y pegado. |
| `config.json` | Configuración de ejemplo, idioma, modelo, atajo y vocabulario. |
| `tests/test_clean_text.py` | Puntuación, acentos, saltos de línea y frases literales. |
| `tests/test_recording.py` | Fallos del dispositivo, limpieza del flujo y coordinación de transcripción. |
| `packaging/build_windows.py` | Compilación, inclusión del modelo, diagnóstico y comprobación del ZIP. |
| `packaging/installer.nsi` | Instalación por usuario, accesos directos y desinstalación. |
| `requirements-windows.lock` | Versiones del entorno usado para validar Windows. |

El flujo principal es: atajo → captura de audio → transcripción → sustitución de comandos → portapapeles y pegado. En el modo local se utiliza faster-whisper/CTranslate2. El proveedor OpenAI solo se utiliza al seleccionarlo en la configuración; ese modo envía el audio al servicio externo.

### Crear el instalador de Windows

build-windows.bat instala requirements-windows.lock y llama a packaging/build_windows.py. Requiere el compilador portable oficial NSIS 3.13 en packaging/tools/nsis-3.13 y el modelo Systran/faster-whisper-small en la caché local. No borra ni reemplaza el dist en uso.

Antes de compilar:

1. Descarga NSIS 3.13 de su distribución oficial y coloca `makensis.exe` junto con sus recursos en `packaging/tools/nsis-3.13/`.
2. Descarga a la caché de Hugging Face los archivos `config.json`, `model.bin`, `tokenizer.json` y `vocabulary.txt` de `Systran/faster-whisper-small`.
3. Crea `tmp/` y guarda una muestra de voz WAV no sensible en `tmp/openai-dictation-test.wav`. El script de compilación de 1.1.0 utiliza esa ruta para comprobar el EXE sin conexión. La muestra no se incluye en el instalador ni en Git.
4. Ejecuta `build-windows.bat`.

Cada compilación crea una carpeta nueva bajo `releases/` con instalador, ZIP, hashes, logs y prueba de transcripción del EXE. Las licencias de terceros se copian a `licenses/` dentro de la distribución; los avisos del modelo están en `packaging/licenses/` en este repositorio.

Diagnóstico del EXE sin grabar ni pegar texto: TravelDeskWhisper.exe --self-test resultado.json --audio prueba.wav. El argumento --audio es opcional; el resultado es un JSON con versiones y comprobaciones del motor local.

Los archivos de compilación para macOS se conservan como referencia y no están validados para esta versión. `build-macos.sh` borra las carpetas `build` y `dist` de su copia de trabajo: úsalo únicamente en un clon de desarrollo separado.

### Archivos locales y licencias

`.gitignore` excluye claves, grabaciones, logs, entornos virtuales, modelos y compilaciones. No agregues credenciales a `config.json`; el archivo `.env.example` solo contiene un marcador de ejemplo. El modo local no necesita `.env`.

Las licencias de terceros incluidas en `packaging/licenses/` corresponden a sus respectivos proyectos. El código propio de esta aplicación no tiene una licencia de código abierto asignada en este repositorio.
