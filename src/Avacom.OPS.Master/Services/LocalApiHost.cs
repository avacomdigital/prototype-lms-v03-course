using System.Diagnostics;
using Avacom.OPS.Core.Services;

namespace Avacom.OPS.Master.Services;

/// <summary>
/// Levanta la API de Django junto al panel cuando el equipo tiene una instalación
/// completa, y la apaga al cerrar.
/// </summary>
/// <remarks>
/// <para>
/// Antes, arrancar la API era responsabilidad del <c>Start-AvacomOPSCore.bat</c>
/// que escribía el instalador. Ese reparto falla por lo obvio: cualquiera abre
/// <c>Avacom.OPS.Master.exe</c> directamente —está ahí, tiene icono y se puede
/// anclar a la barra de tareas— y entonces el panel arranca sin API detrás y sin
/// explicación. Ahora el panel es autosuficiente y el .bat es sólo comodidad.
/// </para>
/// <para>
/// Se enlaza a <c>0.0.0.0</c> y no a <c>127.0.0.1</c>: la API tiene que ser
/// alcanzable desde las tabletas del aula, y escuchar sólo en el bucle local la
/// dejaría accesible únicamente desde este equipo. Que el panel se conecte luego
/// a 127.0.0.1 es otra cosa y es correcto: es la dirección con la que un proceso
/// habla con un servidor de su propia máquina, y funciona aunque el equipo cambie
/// de red o se quede sin ella.
/// </para>
/// </remarks>
public sealed class LocalApiHost(ILmsApiClient api, ILocalLog log) : IAsyncDisposable
{
    /// <summary>Cuánto se espera a que la API responda antes de dar por fallido el arranque.</summary>
    private static readonly TimeSpan StartupTimeout = TimeSpan.FromSeconds(40);

    private Process? _process;
    private Task<bool>? _attempt;
    // Ultima linea que escribio la API. Es lo que se muestra cuando el arranque
    // falla, en lugar de un generico "no respondio".
    private string? _lastError;

    /// <summary>Lo que ocurrió en el último intento, para mostrarlo en el panel.</summary>
    public string Status { get; private set; } = "sin comprobar";

    /// <summary>
    /// Deja la API en marcha si es posible. Devuelve <c>true</c> cuando responde,
    /// sin importar si la arrancó este proceso o ya estaba corriendo.
    /// </summary>
    /// <remarks>
    /// Un único intento compartido entre todos los que llamen. El arranque de la
    /// ventana y la primera carga del panel ocurren casi a la vez y sin esto
    /// competían: el panel pedía el examen antes de que la API escuchara y mostraba
    /// un error de conexión que se corregía solo cinco segundos después.
    /// </remarks>
    public Task<bool> EnsureRunningAsync(CancellationToken cancellationToken = default) =>
        _attempt ??= AttemptAsync(cancellationToken);

    private async Task<bool> AttemptAsync(CancellationToken cancellationToken)
    {
        // Si ya responde no se arranca nada. Cubre dos casos reales: el .bat la
        // levantó antes de abrir el panel, y el desarrollador tiene su propio
        // runserver en el puerto. Arrancar una segunda copia fallaría al enlazar.
        if (await api.CheckHealthAsync(cancellationToken))
        {
            Status = "la API ya estaba en marcha";
            return true;
        }

        var layout = ResolveInstallation();
        if (layout is null)
        {
            // Ejecución desde el árbol de compilación: no hay runtime embebido y la
            // API la levanta quien desarrolla. No es un error.
            Status = "no hay instalación local de la API en este equipo";
            await log.WriteAsync("api-host", "runtime embebido no encontrado; no se arranca la API");
            return false;
        }

        try
        {
            _process = Start(layout.Value.Python, layout.Value.BackendDirectory);
            await log.WriteAsync("api-host", $"daphne iniciado pid={_process.Id} en 0.0.0.0:8000");
        }
        catch (Exception exception)
        {
            Status = $"no se pudo iniciar la API: {exception.Message}";
            await log.WriteAsync("api-host", "fallo al iniciar daphne", exception);
            return false;
        }

        if (await WaitUntilHealthyAsync(cancellationToken))
        {
            Status = "API iniciada por el panel";
            return true;
        }

        // El proceso quedó vivo pero sin responder: se deja correr y se informa. El
        // indicador del panel queda en rojo, que es más útil que cerrarlo en silencio.
        var detail = string.IsNullOrWhiteSpace(_lastError) ? "" : $" · {_lastError}";
        Status = _process.HasExited
            ? $"la API se cerró al arrancar (código {_process.ExitCode}){detail}"
            : $"la API no respondió a tiempo{detail}";
        await log.WriteAsync("api-host", $"arranque incompleto: {Status}");
        return false;
    }

    /// <summary>
    /// Localiza el runtime embebido y la API relativos al ejecutable. La disposición
    /// la fija el instalador: el panel vive en <c>app\</c> y sus hermanas son
    /// <c>runtime\</c> y <c>backend\</c>.
    /// </summary>
    private static (string Python, string BackendDirectory)? ResolveInstallation()
    {
        var root = Directory.GetParent(AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar))?.FullName;
        if (root is null) return null;

        var python = Path.Combine(root, "runtime", "python.exe");
        var backend = Path.Combine(root, "backend");
        if (!File.Exists(python) || !File.Exists(Path.Combine(backend, "manage.py"))) return null;
        return (python, backend);
    }

    private Process Start(string python, string backendDirectory)
    {
        var start = new ProcessStartInfo(python)
        {
            WorkingDirectory = backendDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            // Se captura la salida de error porque es donde daphne cuenta por qué no
            // arrancó. Sin esto, un fallo al importar los settings —el caso real: la
            // API no podía crear su carpeta de registros dentro de Program Files y
            // moría antes de abrir el socket— sólo se veía como "no respondió a
            // tiempo", que no dice nada de la causa.
            RedirectStandardError = true,
            RedirectStandardOutput = true,
        };
        // Argumentos uno a uno en lugar de una cadena: así no hay que escapar
        // comillas. Escapar a mano fue justo lo que rompió el .bat del instalador,
        // donde -FilePath '' terminaba siendo una cadena vacía.
        foreach (var argument in new[] { "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "exam_master.asgi:application" })
            start.ArgumentList.Add(argument);

        var process = Process.Start(start) ?? throw new InvalidOperationException("Windows no devolvió el proceso de la API.");

        // Lectura asíncrona y no ReadToEnd(): los flujos redirigidos tienen un búfer
        // limitado y, si nadie los vacía, daphne se bloquea al llenarlo. Con la API
        // en marcha esa escritura es continua, así que bloquearía siempre.
        process.ErrorDataReceived += (_, e) => LogLine("stderr", e.Data);
        process.OutputDataReceived += (_, e) => LogLine("stdout", e.Data);
        process.BeginErrorReadLine();
        process.BeginOutputReadLine();
        return process;
    }

    private void LogLine(string stream, string? line)
    {
        if (string.IsNullOrWhiteSpace(line)) return;
        _lastError = line;
        _ = log.WriteAsync("api-host", $"{stream}: {line}");
    }

    private async Task<bool> WaitUntilHealthyAsync(CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(StartupTimeout);
        try
        {
            while (!timeout.IsCancellationRequested)
            {
                if (_process?.HasExited == true) return false;
                if (await api.CheckHealthAsync(timeout.Token)) return true;
                await Task.Delay(TimeSpan.FromMilliseconds(500), timeout.Token);
            }
        }
        catch (OperationCanceledException) { }
        return false;
    }

    /// <summary>
    /// Apaga sólo la API que arrancó este proceso. Si ya estaba corriendo cuando se
    /// abrió el panel, se deja intacta: no es suya y cerrarla dejaría sin servicio a
    /// otra sesión.
    /// </summary>
    public async ValueTask DisposeAsync()
    {
        if (_process is null) return;
        try
        {
            if (!_process.HasExited)
            {
                // entireProcessTree: daphne crea procesos hijos y matar sólo al padre
                // dejaría el puerto 8000 ocupado, impidiendo el siguiente arranque.
                _process.Kill(entireProcessTree: true);
                await _process.WaitForExitAsync();
            }
        }
        catch (Exception exception)
        {
            await log.WriteAsync("api-host", "fallo al detener la API", exception);
        }
        finally
        {
            _process.Dispose();
            _process = null;
        }
    }
}
