; ============================================================================
;  AVACOM OPS Core - Instalador wizard (Inno Setup 6)
;
;  Produce un unico Setup.exe con el asistente clasico de Windows: Bienvenida,
;  licencia opcional, carpeta de destino, accesos directos, progreso y final.
;  Aparece en "Agregar o quitar programas" con su desinstalador.
;
;  Requisito: ejecutar antes Build-AvacomOPSPackage.ps1, que deja en payload\
;  el panel compilado, la API y Python embebido con las dependencias. Este
;  script SOLO empaqueta y copia: el equipo del profesor no compila nada.
;
;  Compilar:
;    & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\AvacomOPSCore.iss
; ============================================================================

#define AppName        "AVACOM OPS Core"
#define AppVersion     "1.0.0"
#define AppPublisher   "AVACOM"
#define ApiPort        "8000"
#define LauncherName   "Start-AvacomOPSCore.bat"
#define PanelExe       "Avacom.OPS.Master.exe"
; Datos escribibles FUERA de Program Files: ahi un usuario estandar no puede
; escribir, y la API moria al arrancar al crear su carpeta de registros.
#define DataDir        "{commonappdata}\AVACOM\ExamCore"

[Setup]
AppId={{7D4C1E92-3A8B-4F51-9C6D-AE2B45F80C13}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\AVACOM\ExamCore
DefaultGroupName={#AppName}
OutputDir=dist
OutputBaseFilename=AvacomOPSCore-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; La carga trae un .exe x64 autocontenido y Python amd64: en x86 no arrancaria.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Se instala en Program Files y se escribe en HKLM: requiere elevacion.
PrivilegesRequired=admin
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\app\{#PanelExe}
DisableProgramGroupPage=yes
ShowLanguageDialog=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
spanish.LaunchAfter=Iniciar %1 al finalizar
spanish.CreateDesktopIcon=Crear un acceso directo en el &escritorio
spanish.PortInUse=El puerto {#ApiPort} esta en uso en este equipo.%n%nLa instalacion puede continuar, pero antes de abrir el panel hay que cerrar el programa que lo ocupa (normalmente otra copia de la API ya en marcha).
spanish.FirewallNote=Se permitira el trafico entrante al puerto {#ApiPort} para que las tabletas alcancen la API.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "firewall";    Description: "{cm:FirewallNote}"

[Dirs]
; users-modify es imprescindible: el panel corre como usuario estandar y la
; API tiene que poder escribir la base SQLite y los registros aqui.
;
; Se declara TAMBIEN la carpeta padre. Si no, y el equipo ya tiene un
; ProgramData\AVACOM con permisos restrictivos -por ejemplo de una version
; anterior o de otro producto-, la carpeta hija no se puede crear y la
; instalacion falla sin dejar claro por que.
Name: "{commonappdata}\AVACOM";  Permissions: users-modify
Name: "{#DataDir}";              Permissions: users-modify

[Files]
; El panel del profesor, ya compilado y autocontenido.
Source: "payload\app\*";     DestDir: "{app}\app";     Flags: ignoreversion recursesubdirs createallsubdirs
; La API de Django.
Source: "payload\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs
; Python 3.12 embebido con las dependencias ya instaladas.
Source: "payload\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Los accesos apuntan al .exe y no al .bat: el panel levanta la API por si mismo,
; asi que ya no hay un camino "correcto" y otro que deja el panel sin API. El .bat
; se sigue generando por compatibilidad con accesos anclados de versiones previas.
Name: "{group}\{#AppName}";             Filename: "{app}\app\{#PanelExe}"; WorkingDir: "{app}\app"; Comment: "Abre el panel del profesor y levanta la API"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";       Filename: "{app}\app\{#PanelExe}"; WorkingDir: "{app}\app"; Tasks: desktopicon

[Run]
; Aqui NO va nada que dependa del .env ni cuyo fallo importe, por dos razones:
;
;  1. Orden. Las entradas de [Run] se ejecutan ANTES de CurStepChanged(ssPostInstall),
;     que es donde se genera el .env. Tener migrate aqui significaba migrar sin
;     configuracion y la base podia terminar en una ruta distinta.
;  2. Silencio. [Run] descarta el codigo de salida, asi que un paso que falla no
;     detiene ni avisa.
;
; El .env, las migraciones y el curso demo viven ahora en [Code], en orden
; y con su resultado comprobado.
;
; Regla de firewall para que las tabletas alcancen la API desde la LAN.
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""{#AppName} (TCP {#ApiPort})"" dir=in action=allow protocol=TCP localport={#ApiPort}"; StatusMsg: "Permitiendo el acceso de las tabletas..."; Flags: runhidden; Tasks: firewall
; Casilla final del asistente.
Filename: "{app}\app\{#PanelExe}"; Description: "{cm:LaunchAfter,{#AppName}}"; WorkingDir: "{app}\app"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""{#AppName} (TCP {#ApiPort})"""; Flags: runhidden; RunOnceId: "DelFirewallRule"

[UninstallDelete]
; Generados en tiempo de ejecucion, asi que [Files] no los conoce y no los borraria.
Type: files;          Name: "{app}\{#LauncherName}"
Type: files;          Name: "{app}\.env"
; La base y los registros viven ahora en la carpeta de datos, no en {app}.
; Los registros se borran porque se regeneran; la base NO, porque contiene los
; resultados de actividades ya realizadas y perderlos no se deshace. Para una
; limpieza completa con respaldo previo esta Uninstall-AvacomOPSCore.ps1.
Type: filesandordirs; Name: "{#DataDir}\logs"
; La API genera __pycache__ dentro de runtime\ y backend\ al ejecutarse; esos
; archivos no estan en [Files], asi que el desinstalador no los conoce y sin
; esto dejaria las carpetas atras.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\backend"
Type: dirifempty;     Name: "{app}"

[Code]
{ ------------------------------------------------------------------------------
  Genera el lanzador durante la instalacion en lugar de empaquetarlo, porque
  incrusta rutas y el puerto que solo se conocen aqui.

  El .env lo genera GenerateEnvFile mas abajo, invocando tools/make_env.py con
  el Python embebido: asi la clave de Django viene de `secrets` y no del Random
  de Pascal Script, que no es material criptografico. Se llama desde aqui y no
  desde [Run] porque esa seccion descarta el codigo de salida.
  ------------------------------------------------------------------------------ }

procedure WriteLauncher();
var
  Path: String;
  L: TArrayOfString;
begin
  Path := ExpandConstant('{app}\{#LauncherName}');
  { El lanzador ya NO arranca la API: eso lo hace el panel al abrirse, para que
    tambien funcione al ejecutar el .exe directamente. Aqui solo queda abrir el
    panel, asi que desaparece el for /f con PowerShell anidado cuyo escapado de
    comillas producia -FilePath '' -es decir, cadena vacia- y por eso la API
    nunca arrancaba. }
  SetArrayLength(L, 12);
  L[0]  := '@echo off';
  L[1]  := 'setlocal EnableExtensions';
  L[2]  := 'title ' + '{#AppName}';
  L[3]  := 'set "PANEL=%~dp0app\' + '{#PanelExe}"';
  L[4]  := '';
  L[5]  := 'if not exist "%PANEL%" (';
  L[6]  := '    echo Instalacion incompleta: falta el panel del profesor.';
  L[7]  := '    pause';
  L[8]  := '    exit /b 1';
  L[9]  := ')';
  L[10] := '';
  L[11] := 'start "" "%PANEL%"';
  SaveStringsToFile(Path, L, False);
end;

{ Genera el .env con el Python embebido y COMPRUEBA que se haya creado.

  Se hace aqui y no en [Run] porque [Run] descarta el codigo de salida: cuando
  make_env.py fallaba, la instalacion seguia como si nada, sin .env, y entonces
  la API podía arrancar con una configuración incompleta. }
procedure GenerateEnvFile();
var
  ResultCode: Integer;
  EnvPath: String;
begin
  EnvPath := ExpandConstant('{app}\.env');

  if not Exec(ExpandConstant('{app}\runtime\python.exe'),
              ExpandConstant('"{app}\backend\tools\make_env.py" "{app}\.env" {#ApiPort} "{#DataDir}"'),
              ExpandConstant('{app}\backend'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('No se pudo ejecutar el generador de configuracion.' + #13#10 +
           'La instalacion queda incompleta: la API no arrancara.', mbError, MB_OK);
    Exit;
  end;

  { Se comprueba el archivo y no solo el codigo de salida: es la unica prueba de
    que el paso hizo su trabajo. }
  if (ResultCode <> 0) or not FileExists(EnvPath) then
    MsgBox('El archivo de configuracion (.env) no se genero (codigo ' + IntToStr(ResultCode) + ').' + #13#10 + #13#10 +
           'La API no podra arrancar. Vuelve a ejecutar el instalador; si persiste, ' +
           'revisa que la carpeta de datos sea escribible.', mbError, MB_OK);
end;

{ Prepara la base de datos: migraciones y curso demo.

  Va DESPUES de GenerateEnvFile y fuera de la seccion Run, por el orden: sus
  entradas se ejecutan antes de CurStepChanged(ssPostInstall), asi que alli
  migrate corria sin .env y podía escribir SQLite fuera de la carpeta de datos.

  Ambos comandos son idempotentes, asi que reinstalar no duplica ni borra datos.

  Ojo al escribir comentarios aqui: una linea que empiece por un nombre entre
  corchetes se interpreta como etiqueta de seccion, aunque este dentro de un
  comentario, y aborta la compilacion con "invalid section tag". }
procedure PrepareDatabase();
var
  ResultCode: Integer;
  Python, Backend, DbPath: String;
begin
  Python  := ExpandConstant('{app}\runtime\python.exe');
  Backend := ExpandConstant('{app}\backend');
  DbPath  := ExpandConstant('{#DataDir}\db.sqlite3');

  if not Exec(Python, ExpandConstant('"{app}\backend\manage.py" migrate --noinput'),
              Backend, SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
  begin
    MsgBox('No se pudieron aplicar las migraciones de la base de datos (codigo ' +
           IntToStr(ResultCode) + ').' + #13#10 + #13#10 +
           'La API no podra atender cursos. Vuelve a ejecutar el instalador.', mbError, MB_OK);
    Exit;
  end;

  if not Exec(Python, ExpandConstant('"{app}\backend\manage.py" seed_exam'),
              Backend, SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    MsgBox('No se pudo cargar Algebra Octavo B (codigo ' + IntToStr(ResultCode) + ').' + #13#10 +
           'El panel abrira sin el curso demo; puedes cargarlo despues.', mbInformation, MB_OK);

  { Se comprueba el archivo y no solo el codigo de salida: si el .env no se leyo,
    migrate apunta a otra base y termina en 0 sin dejar nada aqui. Esa fue
    exactamente la forma en que el fallo paso inadvertido. }
  if not FileExists(DbPath) then
    MsgBox('Las migraciones terminaron pero no se creo la base de datos en:' + #13#10 +
           ExpandConstant('{#DataDir}') + #13#10 + #13#10 +
           'Suele indicar que no se leyo el archivo .env. La API respondera con ' +
           'error al abrir un curso.', mbError, MB_OK);
end;

{ Avisa si el puerto de la API ya esta ocupado. No bloquea: el equipo puede
  tener la API corriendo de una sesion anterior, y eso se resuelve cerrandola. }
procedure WarnIfPortBusy();
var
  ResultCode: Integer;
begin
  if Exec(ExpandConstant('{cmd}'),
          '/C netstat -ano -p TCP | findstr /R /C:":{#ApiPort} .*LISTENING" >nul',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    if ResultCode = 0 then
      MsgBox(ExpandConstant('{cm:PortInUse}'), mbInformation, MB_OK);
end;

function InitializeSetup(): Boolean;
begin
  WarnIfPortBusy();
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { ssPostInstall y no ssInstall: en ssPostInstall los archivos ya estan
    copiados, asi que la carpeta de destino existe y el lanzador se escribe
    junto a ellos. Ademas ocurre antes de las entradas de la seccion Run.

    Ojo: no se puede escribir una constante entre llaves en un comentario de
    Pascal Script; su llave de cierre termina el comentario y lo que sigue se
    compila como codigo. }
  { El orden importa: la base solo se puede preparar cuando el .env ya existe. }
  if CurStep = ssPostInstall then
  begin
    WriteLauncher();
    GenerateEnvFile();
    PrepareDatabase();
  end;
end;
