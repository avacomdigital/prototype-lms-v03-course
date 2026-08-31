# AVACOM LMS · prototipo de cursos

Prototipo funcional para explorar la creación de un curso, su asignación a estudiantes y la ejecución de una actividad calificable. Contiene:

- **Backend:** Django 5 + DRF con `APIView`, Channels y SQLite.
- **AVACOM OPS Master:** .NET MAUI para Windows; crea cursos, asigna estudiantes y consolida progreso/notas.
- **AVACOM Student:** .NET MAUI para Windows y Android; abre el curso, navega secciones/lecciones/items y responde el quiz.

## Demo incluida

`seed_exam` carga **Álgebra Octavo B** con 2 secciones, 3 lecciones y 6 Lesson Items (2 por lección). El último item es el **Quiz de cultura general sobre México**, con las 5 preguntas definidas para el prototipo. También agrega tres intentos demostrativos para que el consolidado del Master tenga contenido desde el primer arranque.

## Inicio rápido en Windows

Requisitos de desarrollo: Python 3.12+, .NET SDK 9 con workloads MAUI/Android y PowerShell 5.1+.

```powershell
.\scripts\windows\Install-Backend.ps1 -IncludeDevDependencies
.\scripts\windows\Start-Backend.ps1
```

El backend escucha por defecto en `0.0.0.0:8000`. En otra terminal:

```powershell
dotnet run --project src\Avacom.OPS.Master\Avacom.OPS.Master.csproj -f net9.0-windows10.0.19041.0
dotnet run --project src\Avacom.Student\Avacom.Student.csproj -f net9.0-windows10.0.19041.0
```

En Student escribe el nombre y la URL que Master presenta, por ejemplo `http://192.168.1.20:8000`. En Android no uses `localhost`: esa dirección apunta al propio dispositivo.

Si Windows bloquea otros equipos de la LAN:

```powershell
.\scripts\windows\Open-MasterFirewall.ps1 -Port 8000
```

## Flujo del prototipo

1. Master presenta el curso demo y el estado de API/LAN.
2. En **Crear curso**, el wizard registra curso → secciones → lecciones mediante los CRUD de DRF.
3. En **Estudiantes**, el profesor asigna un nombre al curso.
4. Student se conecta, abre Álgebra Octavo B y recorre toda su jerarquía.
5. Al abrir el último item se crea/reanuda un intento. Cada cambio de pregunta se publica por HTTP y Channels lo difunde al Master por WebSocket.
6. Al finalizar se guarda cada respuesta, se calcula la nota sobre 100 y se actualiza el consolidado del profesor.

Las opciones enviadas a Student no contienen `es_correcta`; el detalle con la solución sólo se entrega desde los endpoints de resultados usados por Master.

## Validación

```powershell
.\scripts\Invoke-Tests.ps1
.\scripts\Invoke-EndpointProof.ps1 -BaseUrl http://127.0.0.1:8000

dotnet build src\Avacom.OPS.Master\Avacom.OPS.Master.csproj -f net9.0-windows10.0.19041.0
dotnet build src\Avacom.Student\Avacom.Student.csproj -f net9.0-windows10.0.19041.0
dotnet build src\Avacom.Student\Avacom.Student.csproj -f net9.0-android35.0
```

La prueba integral crea una inscripción y un intento `PoC`, comprueba CRUD, jerarquía, quiz, nota y WebSocket, y elimina el curso CRUD temporal.

## Instalador de OPS Master

Entregable listo para la pantalla OPS: [`installer/dist/AvacomOPSCore-Setup-1.0.0.exe`](installer/dist/AvacomOPSCore-Setup-1.0.0.exe). Pesa aproximadamente 79,5 MB e incluye el panel, .NET/Windows App SDK, Python, la API y las migraciones; no requiere Docker ni compilación en el host.

Hay dos caminos, ambos sin requerir teclado ni herramientas de desarrollo en la pantalla OPS:

- `installer\AvacomOPSCoreSetup.ps1`: asistente WinForms que prepara backend, SQLite, curso demo y panel.
- `installer\Build-AvacomOPSPackage.ps1` + `installer\AvacomOPSCore.iss`: genera un `Setup.exe` con el panel autocontenido, Python embebido, API, migraciones, regla opcional de firewall y accesos directos.

El panel inicia Daphne automáticamente, valida `/health/`, muestra éxito/falla y ofrece la URL LAN que debe escribirse en Student. Los registros quedan en `logs/api.log`; el diagnóstico visible evita depender de una consola en la pantalla interactiva.

## Diseño y recursos

Ambas apps usan el mismo sistema visual AVACOM: fondo degradado `#E9F6FA` → `#FBF8E7`, superficies blancas, radios 16–24, controles táctiles de 64 px y estados semánticos. El logo SVG se rasteriza por MAUI con una base de alta resolución. Geist Regular/Bold está embebida y su licencia OFL está en `docs/third-party/Geist-OFL.txt`.

## Documentación técnica

- [Contrato HTTP y WebSocket](docs/API.md)
- [Arquitectura y modelo de datos](docs/ARCHITECTURE.md)
