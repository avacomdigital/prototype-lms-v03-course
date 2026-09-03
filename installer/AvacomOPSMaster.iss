; ============================================================================
;  AVACOM OPS Master - Instalador wizard (Inno Setup 6)
;
;  Produce un unico Setup.exe en dist\ con el flujo pedido:
;
;    Bienvenido -> Informacion -> Carpeta -> Validacion del sistema ->
;    Listo -> Instalando -> Configuracion del backend -> Completado
;
;  El equipo del profesor NO compila nada: la carga la prepara antes
;  Build-AvacomOPSPackage.ps1 en la maquina de desarrollo. Aqui solo se copia,
;  se configura y se registra el servicio.
;
;  CONVIVENCIA CON AVACOM BIBLIOTECA
;  Los dos productos pueden estar en el mismo equipo del aula. Todo lo que este
;  instalador crea lleva nombre propio y ruta propia:
;
;    carpeta       {autopf}\AVACOM\OPS Master        (Biblioteca usa ...\Biblioteca)
;    datos         {commonappdata}\AVACOM\OPS Master (Biblioteca usa ...\contenido)
;    servicio      AVACOMOPSBackend                  (por nombre exacto)
;    puerto        TCP 8000 en 0.0.0.0               (Biblioteca usa loopback efimero)
;    firewall      AVACOM OPS Master Backend
;    accesos       grupo "AVACOM OPS Master"
;    AppId         GUID propio, entrada propia en Agregar o quitar programas
;
;  Ninguna tarea de este script enumera, detiene ni modifica nada de Biblioteca.
;
;  Compilar:
;    installer\Build-Installer.ps1
; ============================================================================

#define AppName        "AVACOM OPS Master"
#define AppVersion     "2.0.0"
#define AppPublisher   "AVACOM"
#define AppSuite       "AVACOM LMS 2.0"
#define ApiPort        "8000"
#define ApiHost        "0.0.0.0"
#define ServiceName    "AVACOMOPSBackend"
#define ServiceLabel   "AVACOM OPS Master Backend"
#define FirewallRule   "AVACOM OPS Master Backend"
#define PanelExe       "Avacom.OPS.Master.exe"
#define ServiceExe     "Avacom.OPS.Backend.Service.exe"
#define LauncherName   "Start-AvacomOPSMaster.bat"
; Datos escribibles FUERA de Program Files: ahi un usuario estandar no puede
; escribir, y la API moria al arrancar al crear su carpeta de registros.
#define DataDir        "{commonappdata}\AVACOM\OPS Master"

[Setup]
; GUID propio y distinto del de OPS Core 1.x: las dos versiones aparecen por
; separado en Agregar o quitar programas, y desinstalar una no toca la otra.
AppId={{9F2A6C41-58D7-4E93-B1A0-6C3E7D82F45B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments={#AppSuite}
DefaultDirName={autopf}\AVACOM\OPS Master
DefaultGroupName={#AppName}
; La salida va a dist\ en la raiz del repositorio, que es lo que se distribuye.
OutputDir=..\dist
OutputBaseFilename=AvacomOPSMaster-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; La carga trae un .exe x64 autocontenido y Python amd64: en x86 no arrancaria.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Hacen falta para Program Files, el servicio y la regla de firewall.
PrivilegesRequired=admin
InfoBeforeFile=INFORMACION.txt
DisableWelcomePage=no
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
spanish.AdditionalIcons=Accesos adicionales:
spanish.CreateDesktopIcon=Crear un acceso en el escritorio
spanish.LaunchAfter=Abrir %1 al terminar
spanish.ValidationCaption=Validacion del sistema
spanish.ValidationDesc=Se comprueba que este equipo puede alojar el nodo del aula.
spanish.ValidationRunning=Comprobando el equipo...
spanish.ValidationBlocked=Hay comprobaciones que impiden continuar. Resuelvelas y pulsa Reintentar.
spanish.ValidationOk=El equipo cumple los requisitos. Pulsa Siguiente para continuar.
spanish.Retry=Reintentar
spanish.BackendStep=Configuracion del backend

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "firewall";    Description: "Permitir que las tabletas del salon alcancen la API (TCP {#ApiPort}, redes privadas)"
Name: "autostart";   Description: "Iniciar la API automaticamente con Windows (recomendado)"

[Dirs]
; users-modify es imprescindible: el panel corre como usuario estandar y la API
; tiene que poder escribir la base SQLite y los registros aqui.
;
; Se declara TAMBIEN la carpeta padre. Si no, y el equipo ya tiene un
; ProgramData\AVACOM con permisos restrictivos -por ejemplo creado por AVACOM
; Biblioteca-, la carpeta hija no se puede crear y la instalacion falla sin
; dejar claro por que. Declararla no cambia los permisos de las carpetas
; hermanas: contenido\ de Biblioteca queda como estaba.
Name: "{commonappdata}\AVACOM";  Permissions: users-modify
Name: "{#DataDir}";              Permissions: users-modify
Name: "{#DataDir}\logs";         Permissions: users-modify

[Files]
; El panel del profesor, ya compilado y autocontenido.
Source: "payload\app\*";     DestDir: "{app}\app";     Flags: ignoreversion recursesubdirs createallsubdirs
; La API de Django.
Source: "payload\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs
; Python 3.12 embebido con las dependencias ya instaladas.
Source: "payload\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
; El servicio que mantiene la API en marcha.
Source: "payload\service\*"; DestDir: "{app}\service"; Flags: ignoreversion recursesubdirs createallsubdirs
; Los guiones que el asistente ejecuta. Van instalados porque el desinstalador
; tambien los necesita.
Source: "tools\Register-Backend-Service.ps1";   DestDir: "{app}\tools"; Flags: ignoreversion
Source: "tools\Unregister-Backend-Service.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
; La validacion corre ANTES de copiar nada, asi que viaja como archivo temporal.
Source: "tools\Validate-Node.ps1"; Flags: dontcopy

[Icons]
Name: "{group}\{#AppName}";             Filename: "{app}\app\{#PanelExe}"; WorkingDir: "{app}\app"; Comment: "Abre el panel del profesor"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";       Filename: "{app}\app\{#PanelExe}"; WorkingDir: "{app}\app"; Tasks: desktopicon

[Run]
; Aqui NO va nada cuyo fallo importe: [Run] descarta el codigo de salida, asi
; que un paso que falla no detiene ni avisa. El .env, las migraciones y el
; servicio viven en [Code], en orden y con su resultado comprobado.
;
; La regla de firewall si puede ir aqui: si falla, la API sigue funcionando en
; el propio equipo y el asistente lo dice en la ultima pantalla.
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""{#FirewallRule}"" dir=in action=allow protocol=TCP localport={#ApiPort} profile=private"; StatusMsg: "Permitiendo el acceso de las tabletas del salon..."; Flags: runhidden; Tasks: firewall
; Casilla final del asistente.
Filename: "{app}\app\{#PanelExe}"; Description: "{cm:LaunchAfter,{#AppName}}"; WorkingDir: "{app}\app"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Primero el servicio: mientras corre, sus archivos estan bloqueados y el
; desinstalador no podria borrarlos.
Filename: "powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\tools\Unregister-Backend-Service.ps1"" -Silencioso"; Flags: runhidden waituntilterminated; RunOnceId: "QuitarServicio"
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""{#FirewallRule}"""; Flags: runhidden; RunOnceId: "QuitarReglaFirewall"

[UninstallDelete]
Type: files;          Name: "{app}\{#LauncherName}"
Type: files;          Name: "{app}\.env"
; Los registros se borran porque se regeneran. La base NO: contiene el trabajo
; de los estudiantes y perderlo no se deshace.
Type: filesandordirs; Name: "{#DataDir}\logs"
; La API genera __pycache__ dentro de runtime\ y backend\ al ejecutarse; esos
; archivos no los puso el instalador, asi que hay que nombrarlos.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\service"
Type: filesandordirs; Name: "{app}\tools"
Type: dirifempty;     Name: "{app}"
; La carpeta padre solo si queda vacia: si AVACOM Biblioteca esta instalada al
; lado, {autopf}\AVACOM no esta vacia y no se toca.
Type: dirifempty;     Name: "{autopf}\AVACOM"

[Code]
var
  PaginaValidacion: TWizardPage;
  MemoValidacion: TNewMemo;
  EtiquetaValidacion: TNewStaticText;
  BotonReintentar: TNewButton;
  ValidacionCorrecta: Boolean;
  ResumenBackend: String;

{ ----------------------------------------------------------------------------
  PANTALLA 4 - Validacion del sistema

  Las comprobaciones las hace tools\Validate-Node.ps1 y no Pascal Script,
  porque PowerShell puede consultar de verdad el estado del equipo -que proceso
  tiene el puerto, cuanto espacio queda, si el servicio ya existe- y Pascal
  Script tendria que apoyarse en netstat y findstr, que fue lo que se hacia
  antes y solo permitia decir "el puerto esta ocupado" sin decir por quien.

  El guion escribe un informe CLAVE|ESTADO|MENSAJE y devuelve 1 si hay algun
  ERROR. Aqui se muestra tal cual y se decide si se puede continuar.
  ---------------------------------------------------------------------------- }

function EtiquetaDeEstado(Estado: String): String;
begin
  if Estado = 'OK' then Result := '  [ correcto ]  '
  else if Estado = 'AVISO' then Result := '  [ aviso ]    '
  else Result := '  [ IMPIDE ]   ';
end;

procedure EjecutarValidacion();
var
  Informe, Salida, Linea, Estado, Mensaje: String;
  Lineas: TArrayOfString;
  Codigo, i, Corte, Segundo: Integer;
begin
  MemoValidacion.Lines.Clear();
  EtiquetaValidacion.Caption := ExpandConstant('{cm:ValidationRunning}');
  BotonReintentar.Enabled := False;
  WizardForm.Refresh();

  ExtractTemporaryFile('Validate-Node.ps1');
  Informe := ExpandConstant('{tmp}\validacion.txt');
  DeleteFile(Informe);

  { -NonInteractive y -NoProfile: el requisito es que nada pida interaccion, y
    un perfil de PowerShell ajeno podria imprimir o preguntar. }
  if not Exec('powershell.exe',
              '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
              ExpandConstant('{tmp}\Validate-Node.ps1') + '" -Informe "' + Informe +
              '" -RutaDestino "' + WizardDirValue + '" -Puerto {#ApiPort}',
              ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, Codigo) then
  begin
    MemoValidacion.Lines.Add('No se pudo ejecutar la comprobacion del sistema.');
    MemoValidacion.Lines.Add('');
    MemoValidacion.Lines.Add('Windows PowerShell no respondio. Vuelve a ejecutar el');
    MemoValidacion.Lines.Add('instalador como administrador.');
    ValidacionCorrecta := False;
    EtiquetaValidacion.Caption := ExpandConstant('{cm:ValidationBlocked}');
    BotonReintentar.Enabled := True;
    Exit;
  end;

  { El informe lo escribe PowerShell en UTF-8. LoadStringsFromFile asume ANSI
    y destrozaria cualquier acento; la variante UTF8 existe justo para esto. }
  if LoadStringsFromUTF8File(Informe, Lineas) then
  begin
    for i := 0 to GetArrayLength(Lineas) - 1 do
    begin
      Linea := Lineas[i];
      Corte := Pos('|', Linea);
      if Corte > 0 then
      begin
        Salida := Copy(Linea, Corte + 1, Length(Linea));
        Segundo := Pos('|', Salida);
        if Segundo > 0 then
        begin
          Estado  := Copy(Salida, 1, Segundo - 1);
          Mensaje := Copy(Salida, Segundo + 1, Length(Salida));
          MemoValidacion.Lines.Add(EtiquetaDeEstado(Estado) + Mensaje);
        end;
      end;
    end;
  end
  else
    MemoValidacion.Lines.Add('La comprobacion no dejo informe.');

  ValidacionCorrecta := (Codigo = 0);
  if ValidacionCorrecta then
    EtiquetaValidacion.Caption := ExpandConstant('{cm:ValidationOk}')
  else
    EtiquetaValidacion.Caption := ExpandConstant('{cm:ValidationBlocked}');
  BotonReintentar.Enabled := True;
  WizardForm.NextButton.Enabled := ValidacionCorrecta;
end;

procedure AlPulsarReintentar(Sender: TObject);
begin
  EjecutarValidacion();
end;

procedure CrearPaginaValidacion();
begin
  PaginaValidacion := CreateCustomPage(wpSelectDir,
    ExpandConstant('{cm:ValidationCaption}'), ExpandConstant('{cm:ValidationDesc}'));

  MemoValidacion := TNewMemo.Create(PaginaValidacion);
  MemoValidacion.Parent := PaginaValidacion.Surface;
  MemoValidacion.SetBounds(0, 0, PaginaValidacion.SurfaceWidth, ScaleY(150));
  MemoValidacion.ScrollBars := ssVertical;
  MemoValidacion.ReadOnly := True;
  MemoValidacion.Color := clBtnFace;

  EtiquetaValidacion := TNewStaticText.Create(PaginaValidacion);
  EtiquetaValidacion.Parent := PaginaValidacion.Surface;
  EtiquetaValidacion.Top := MemoValidacion.Top + MemoValidacion.Height + ScaleY(12);
  EtiquetaValidacion.Width := PaginaValidacion.SurfaceWidth;
  EtiquetaValidacion.WordWrap := True;
  EtiquetaValidacion.Caption := '';

  BotonReintentar := TNewButton.Create(PaginaValidacion);
  BotonReintentar.Parent := PaginaValidacion.Surface;
  BotonReintentar.Top := EtiquetaValidacion.Top + ScaleY(34);
  BotonReintentar.Width := ScaleX(110);
  BotonReintentar.Height := ScaleY(24);
  BotonReintentar.Caption := ExpandConstant('{cm:Retry}');
  BotonReintentar.OnClick := @AlPulsarReintentar;
end;

{ ----------------------------------------------------------------------------
  Lanzador. Se genera durante la instalacion y no se empaqueta, porque incrusta
  rutas y el puerto que solo se conocen aqui.

  Ya NO arranca la API: eso lo hace el servicio. Queda por compatibilidad con
  accesos anclados de versiones anteriores.
  ---------------------------------------------------------------------------- }
procedure EscribirLanzador();
var
  Ruta: String;
  L: TArrayOfString;
begin
  Ruta := ExpandConstant('{app}\{#LauncherName}');
  SetArrayLength(L, 12);
  L[0]  := '@echo off';
  L[1]  := 'setlocal EnableExtensions';
  L[2]  := 'title {#AppName}';
  L[3]  := 'set "PANEL=%~dp0app\{#PanelExe}"';
  L[4]  := '';
  L[5]  := 'if not exist "%PANEL%" (';
  L[6]  := '    echo Instalacion incompleta: falta el panel del profesor.';
  L[7]  := '    pause';
  L[8]  := '    exit /b 1';
  L[9]  := ')';
  L[10] := '';
  L[11] := 'start "" "%PANEL%"';
  SaveStringsToFile(Ruta, L, False);
end;

{ Genera el .env con el Python embebido y COMPRUEBA que se haya creado.

  Se hace aqui y no en la seccion Run porque alli se descarta el codigo de
  salida: cuando make_env.py fallaba, la instalacion seguia como si nada, sin
  .env, y la API arrancaba con una configuracion incompleta. }
function GenerarEnv(): Boolean;
var
  Codigo: Integer;
  RutaEnv: String;
begin
  RutaEnv := ExpandConstant('{app}\.env');
  Result := False;

  if not Exec(ExpandConstant('{app}\runtime\python.exe'),
              ExpandConstant('"{app}\backend\tools\make_env.py" "{app}\.env" {#ApiPort} "{#DataDir}"'),
              ExpandConstant('{app}\backend'), SW_HIDE, ewWaitUntilTerminated, Codigo) then
  begin
    ResumenBackend := ResumenBackend + 'No se pudo ejecutar el generador de configuracion.' + #13#10;
    Exit;
  end;

  { Se comprueba el archivo y no solo el codigo de salida: es la unica prueba de
    que el paso hizo su trabajo. }
  if (Codigo <> 0) or not FileExists(RutaEnv) then
  begin
    ResumenBackend := ResumenBackend + 'La configuracion (.env) no se genero (codigo ' +
                      IntToStr(Codigo) + ').' + #13#10;
    Exit;
  end;

  ResumenBackend := ResumenBackend + 'Configuracion local creada.' + #13#10;
  Result := True;
end;

{ Prepara la base de datos: migraciones y curso demo. Ambos comandos son
  idempotentes, asi que reinstalar no duplica ni borra datos.

  Ojo al escribir comentarios aqui: una linea que empiece por un nombre entre
  corchetes se interpreta como etiqueta de seccion, aunque este dentro de un
  comentario, y aborta la compilacion con "invalid section tag". }
function PrepararBase(): Boolean;
var
  Codigo: Integer;
  Python, Backend, RutaBase: String;
begin
  Python   := ExpandConstant('{app}\runtime\python.exe');
  Backend  := ExpandConstant('{app}\backend');
  RutaBase := ExpandConstant('{#DataDir}\db.sqlite3');
  Result := False;

  if not Exec(Python, ExpandConstant('"{app}\backend\manage.py" migrate --noinput'),
              Backend, SW_HIDE, ewWaitUntilTerminated, Codigo) or (Codigo <> 0) then
  begin
    ResumenBackend := ResumenBackend + 'Las migraciones fallaron (codigo ' + IntToStr(Codigo) + ').' + #13#10;
    Exit;
  end;

  if not Exec(Python, ExpandConstant('"{app}\backend\manage.py" seed_exam'),
              Backend, SW_HIDE, ewWaitUntilTerminated, Codigo) or (Codigo <> 0) then
    ResumenBackend := ResumenBackend + 'El curso de ejemplo no se cargo; puedes cargarlo despues.' + #13#10;

  { Se comprueba el archivo y no solo el codigo de salida: si el .env no se leyo,
    migrate apunta a otra base y termina en 0 sin dejar nada aqui. Esa fue
    exactamente la forma en que el fallo paso inadvertido. }
  if not FileExists(RutaBase) then
  begin
    ResumenBackend := ResumenBackend + 'Las migraciones terminaron pero no aparecio la base de datos.' + #13#10;
    Exit;
  end;

  ResumenBackend := ResumenBackend + 'Base de datos preparada.' + #13#10;
  Result := True;
end;

{ Registra AVACOMOPSBackend, lo arranca y comprueba que la API responde.

  El guion devuelve 0 si /health/ contesta, 2 si el servicio quedo creado pero
  la API no respondio. Se distinguen porque no son lo mismo: en el segundo caso
  la instalacion esta completa y el problema se diagnostica con el registro de
  eventos, no reinstalando. }
function RegistrarServicio(): Boolean;
var
  Codigo: Integer;
begin
  Result := False;

  if not Exec('powershell.exe',
              '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
              ExpandConstant('{app}\tools\Register-Backend-Service.ps1') +
              '" -RutaEjecutable "' + ExpandConstant('{app}\service\{#ServiceExe}') +
              '" -Puerto {#ApiPort}',
              ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Codigo) then
  begin
    ResumenBackend := ResumenBackend + 'No se pudo ejecutar el registro del servicio.' + #13#10;
    Exit;
  end;

  if Codigo = 0 then
  begin
    ResumenBackend := ResumenBackend +
      'Servicio {#ServiceName} registrado y en marcha.' + #13#10 +
      'La API responde en http://127.0.0.1:{#ApiPort}/health/' + #13#10;
    Result := True;
  end
  else if Codigo = 2 then
    ResumenBackend := ResumenBackend +
      'El servicio {#ServiceName} quedo registrado, pero la API no respondio a tiempo.' + #13#10 +
      'Revisa el Visor de eventos y reinicia el servicio desde Servicios de Windows.' + #13#10
  else
    ResumenBackend := ResumenBackend +
      'El servicio no se pudo registrar (codigo ' + IntToStr(Codigo) + ').' + #13#10;

  { Si no se pidio arranque automatico, se deja en manual DESPUES de la
    comprobacion: asi el asistente puede verificar que la API funciona aunque el
    aula no quiera que arranque sola. }
  if not WizardIsTaskSelected('autostart') then
    Exec('sc.exe', 'config {#ServiceName} start= demand', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
end;

{ ----------------------------------------------------------------------------
  Ciclo del asistente
  ---------------------------------------------------------------------------- }

procedure InitializeWizard();
begin
  ValidacionCorrecta := False;
  ResumenBackend := '';
  CrearPaginaValidacion();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { La validacion se lanza al entrar en la pagina y no antes, porque necesita la
    carpeta de destino que el usuario acaba de elegir para medir el espacio. }
  if (PaginaValidacion <> nil) and (CurPageID = PaginaValidacion.ID) then
    EjecutarValidacion();

  { PANTALLA 8 - Completado. Se cuenta lo que de verdad quedo hecho, incluidos
    los pasos que fallaron: un asistente que termina en verde habiendo dejado la
    API sin arrancar es peor que uno que lo dice. }
  if (CurPageID = wpFinished) and (ResumenBackend <> '') then
    WizardForm.FinishedLabel.Caption :=
      'AVACOM OPS Master quedo instalado en este equipo.' + #13#10 + #13#10 +
      ResumenBackend + #13#10 +
      'Las tabletas del salon se conectan a la direccion de red de este equipo, ' +
      'puerto {#ApiPort}.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (PaginaValidacion <> nil) and (CurPageID = PaginaValidacion.ID) then
    Result := ValidacionCorrecta;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Progreso: TOutputProgressWizardPage;
begin
  { ssPostInstall y no ssInstall: aqui los archivos ya estan copiados, asi que
    el runtime embebido existe y se le puede pedir que genere el .env.

    Ojo: no se puede escribir una constante entre llaves en un comentario de
    Pascal Script; su llave de cierre termina el comentario y lo que sigue se
    compila como codigo. }
  if CurStep <> ssPostInstall then Exit;

  { PANTALLA 7 - Configuracion del backend. Es una pagina de progreso propia
    para que los cuatro pasos se vean, en vez de una barra parada mientras
    migrate trabaja. }
  Progreso := CreateOutputProgressPage(ExpandConstant('{cm:BackendStep}'),
    'Se prepara la API local del aula. No hace falta hacer nada.');
  Progreso.SetProgress(0, 4);
  Progreso.Show();
  try
    Progreso.SetText('Escribiendo el lanzador...', '');
    EscribirLanzador();
    Progreso.SetProgress(1, 4);

    { El orden importa: la base solo se puede preparar cuando el .env ya existe,
      porque de ahi sale la ruta de la base y la clave de Django. }
    Progreso.SetText('Creando la configuracion local...', '');
    if GenerarEnv() then
    begin
      Progreso.SetProgress(2, 4);
      Progreso.SetText('Preparando la base de datos...', '');
      PrepararBase();
    end;
    Progreso.SetProgress(3, 4);

    Progreso.SetText('Registrando el servicio de la API...', '');
    RegistrarServicio();
    Progreso.SetProgress(4, 4);
  finally
    Progreso.Hide();
  end;
end;

{ PANTALLA 5 - Listo para instalar. Se resume lo que va a quedar en el equipo,
  incluidos el servicio y el puerto, porque son lo que puede chocar con otro
  producto y quien instala tiene que poder verlo antes de aceptar. }
function GetReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine +
    'Servicio de Windows:' + NewLine +
    Space + '{#ServiceName} ({#ServiceLabel})' + NewLine + NewLine +
    'API local del aula:' + NewLine +
    Space + 'http://{#ApiHost}:{#ApiPort}/  (alcanzable desde la red del salon)' + NewLine + NewLine +
    'Datos y registros:' + NewLine +
    Space + ExpandConstant('{#DataDir}') + NewLine + NewLine +
    MemoTasksInfo;
end;
