using System.Diagnostics;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Text;

namespace Avacom.OPS.Backend.Service;

/// <summary>
/// Mantiene la API del aula en marcha.
///
/// El servicio no sirve HTTP por su cuenta: lanza el mismo daphne que ya usaba
/// el panel y lo vigila. Si daphne muere —el equipo se quedó sin memoria, la
/// base estaba bloqueada— vuelve a levantarlo con una espera creciente, en vez
/// de reintentar en bucle y llenar el registro de eventos.
/// </summary>
public sealed class BackendWorker(ILogger<BackendWorker> log) : BackgroundService
{
    /// <summary>
    /// Escuchar en 0.0.0.0 es lo que permite que las tabletas alcancen la API
    /// desde la LAN. Es un requisito de la arquitectura, no un ajuste.
    /// </summary>
    private const string Interfaz = "0.0.0.0";
    private const int Puerto = 8000;

    /// <summary>
    /// Cuánto se espera antes de reintentar. Crece para no castigar a un equipo
    /// que ya va mal, y se corta en un minuto para que una avería pasajera no
    /// deje el aula sin API el resto de la mañana.
    /// </summary>
    private static readonly TimeSpan[] Esperas =
    [
        TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(15),
        TimeSpan.FromSeconds(30), TimeSpan.FromMinutes(1),
    ];

    private Process? _api;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var disposicion = Resolver();
        if (disposicion is null)
        {
            // Sin runtime embebido no hay nada que arrancar. Se dice y se sale
            // limpio: un servicio que se reinicia eternamente sin poder trabajar
            // es peor que uno detenido con un motivo en el registro.
            log.LogError(
                "No se encontró la instalación de la API junto al servicio. Se esperaba "
                + "runtime\\python.exe y backend\\manage.py en la carpeta del producto.");
            return;
        }

        var (python, backend, registros) = disposicion.Value;
        Directory.CreateDirectory(registros);
        log.LogInformation("Runtime {python}", python);
        log.LogInformation("Backend {backend}", backend);

        var intento = 0;
        while (!stoppingToken.IsCancellationRequested)
        {
            if (PuertoOcupado())
            {
                // Otro proceso tiene el puerto: puede ser el propio panel, que
                // arranca su copia si la API no responde. No se le quita el
                // puerto a nadie; se espera y se vuelve a mirar.
                log.LogWarning(
                    "El puerto {puerto} está ocupado por otro proceso. El servicio espera "
                    + "en vez de forzar el enlace.", Puerto);
                await Esperar(intento++, stoppingToken);
                continue;
            }

            try
            {
                _api = Arrancar(python, backend, registros);
                log.LogInformation("daphne iniciado pid={pid} en {interfaz}:{puerto}",
                    _api.Id, Interfaz, Puerto);

                if (await Respondio(stoppingToken))
                {
                    log.LogInformation("La API responde en http://127.0.0.1:{puerto}/health/", Puerto);
                    intento = 0;
                }
                else
                {
                    log.LogWarning("daphne arrancó pero /health/ no respondió a tiempo.");
                }

                await _api.WaitForExitAsync(stoppingToken);
                if (!stoppingToken.IsCancellationRequested)
                {
                    log.LogWarning("daphne terminó con código {codigo}. Se reintenta.", _api.ExitCode);
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception excepcion)
            {
                log.LogError(excepcion, "No se pudo iniciar la API.");
            }

            if (stoppingToken.IsCancellationRequested) break;
            await Esperar(intento++, stoppingToken);
        }

        Detener();
    }

    /// <summary>
    /// Averigua dónde está la instalación mirando hacia arriba desde el propio
    /// ejecutable.
    ///
    /// El servicio vive en {app}\service\, el runtime en {app}\runtime\ y la API
    /// en {app}\backend\. Deducirlo de la ruta propia evita guardar rutas
    /// absolutas en el registro o en un archivo de configuración, que es lo que
    /// se rompe cuando alguien mueve la carpeta.
    /// </summary>
    private static (string Python, string Backend, string Registros)? Resolver()
    {
        var propio = Path.GetDirectoryName(Environment.ProcessPath
            ?? AppContext.BaseDirectory)!;
        for (var carpeta = new DirectoryInfo(propio); carpeta is not null; carpeta = carpeta.Parent)
        {
            var python = Path.Combine(carpeta.FullName, "runtime", "python.exe");
            var backend = Path.Combine(carpeta.FullName, "backend");
            if (File.Exists(python) && File.Exists(Path.Combine(backend, "manage.py")))
            {
                // Los registros van a ProgramData: en Program Files un servicio
                // que corre como LocalSystem sí podría escribir, pero mezclar
                // datos con archivos de programa complica respaldar y desinstalar.
                var datos = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                    "AVACOM", "OPS Master", "logs");
                return (python, backend, datos);
            }
        }
        return null;
    }

    private Process Arrancar(string python, string backend, string registros)
    {
        var inicio = new ProcessStartInfo
        {
            FileName = python,
            WorkingDirectory = backend,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            StandardErrorEncoding = Encoding.UTF8,
            StandardOutputEncoding = Encoding.UTF8,
        };
        foreach (var argumento in new[]
        {
            "-m", "daphne", "-b", Interfaz, "-p", Puerto.ToString(),
            "--access-log", Path.Combine(registros, "acceso.log"),
            "exam_master.asgi:application",
        })
        {
            inicio.ArgumentList.Add(argumento);
        }

        var proceso = new Process { StartInfo = inicio, EnableRaisingEvents = true };

        // Los buffers de salida son pequeños: si nadie los vacía, daphne se
        // bloquea al llenarlos. Se leen y se llevan al registro del servicio.
        proceso.OutputDataReceived += (_, e) =>
        {
            if (!string.IsNullOrWhiteSpace(e.Data)) log.LogInformation("api: {linea}", e.Data);
        };
        proceso.ErrorDataReceived += (_, e) =>
        {
            if (!string.IsNullOrWhiteSpace(e.Data)) log.LogInformation("api: {linea}", e.Data);
        };

        proceso.Start();
        proceso.BeginOutputReadLine();
        proceso.BeginErrorReadLine();
        return proceso;
    }

    /// <summary>
    /// Comprueba que la API quedó realmente operativa, no solo que el proceso
    /// arrancó. Un daphne que muere al importar Django también «arranca».
    /// </summary>
    private async Task<bool> Respondio(CancellationToken cancellationToken)
    {
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
        for (var intento = 0; intento < 20 && !cancellationToken.IsCancellationRequested; intento++)
        {
            await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);
            if (_api?.HasExited == true) return false;
            try
            {
                using var respuesta = await http.GetAsync(
                    $"http://127.0.0.1:{Puerto}/health/", cancellationToken);
                if (respuesta.IsSuccessStatusCode) return true;
            }
            catch (Exception) { /* todavía no levanta; se vuelve a intentar */ }
        }
        return false;
    }

    private static bool PuertoOcupado()
    {
        try
        {
            return IPGlobalProperties.GetIPGlobalProperties()
                .GetActiveTcpListeners()
                .Any(punto => punto.Port == Puerto);
        }
        catch (Exception)
        {
            // Si no se puede saber, se intenta arrancar: enlazar fallará con un
            // mensaje claro, que es mejor que negarse por si acaso.
            return false;
        }
    }

    private async Task Esperar(int intento, CancellationToken cancellationToken)
    {
        var espera = Esperas[Math.Min(intento, Esperas.Length - 1)];
        try { await Task.Delay(espera, cancellationToken); }
        catch (OperationCanceledException) { }
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        Detener();
        await base.StopAsync(cancellationToken);
    }

    /// <summary>
    /// Cierra daphne y sus hijos. `entireProcessTree` importa: daphne crea
    /// procesos hijos y matar solo al padre deja el puerto ocupado, con lo que
    /// el siguiente arranque del servicio falla sin motivo aparente.
    /// </summary>
    private void Detener()
    {
        var proceso = _api;
        _api = null;
        if (proceso is null) return;
        try
        {
            if (!proceso.HasExited)
            {
                proceso.Kill(entireProcessTree: true);
                proceso.WaitForExit(10_000);
                log.LogInformation("daphne detenido.");
            }
        }
        catch (Exception excepcion)
        {
            log.LogWarning(excepcion, "No se pudo detener daphne limpiamente.");
        }
        finally { proceso.Dispose(); }
    }
}
