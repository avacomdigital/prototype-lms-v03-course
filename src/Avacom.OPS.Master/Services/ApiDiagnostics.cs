using System.Text;
using Avacom.OPS.Core.Services;

namespace Avacom.OPS.Master.Services;

/// <summary>
/// Reúne en un solo texto dónde está corriendo la API y qué dice su registro.
/// </summary>
/// <remarks>
/// Existe porque diagnosticar la API desde la sede era imposible: el panel sólo
/// mostraba «error 500» y averiguar la causa exigía saber de antemano que el
/// registro vive en ProgramData, que el .env está junto al ejecutable y que la
/// base puede haber quedado en otra carpeta. Todo eso se reúne aquí.
/// </remarks>
public sealed class ApiDiagnostics(LocalApiHost apiHost, MasterEndpointSettings endpoint)
{
    /// <summary>Cuántas líneas finales de cada registro se incluyen.</summary>
    private const int TailLines = 25;

    /// <summary>Raíz de la instalación, o null si se ejecuta desde el árbol de compilación.</summary>
    public string? InstallRoot =>
        Directory.GetParent(AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar))?.FullName;

    /// <summary>Carpeta de datos declarada en el .env. Es donde viven la base y el registro de la API.</summary>
    public string? DataDirectory => ReadEnvValue("AVACOM_DATA_DIR");

    /// <summary>Registro de la API. Es el archivo que explica un 500.</summary>
    public string? ApiLogPath =>
        DataDirectory is null ? null : Path.Combine(DataDirectory, "logs", "api.log");

    /// <summary>Registro del panel, que incluye el arranque de la API.</summary>
    public string PanelLogPath => Path.Combine(FileSystem.AppDataDirectory, "logs", "master.log");

    /// <summary>Carpeta que conviene abrir para revisar registros a mano.</summary>
    public string? LogsFolder => DataDirectory is null ? null : Path.Combine(DataDirectory, "logs");

    /// <summary>
    /// Informe completo, listo para pegar en un reporte. La clave de Django se
    /// oculta: este texto se copia al portapapeles y acaba en correos y tickets.
    /// </summary>
    public string BuildReport()
    {
        var report = new StringBuilder();
        void Line(string label, string? value) => report.AppendLine($"{label,-22}: {value ?? "(no disponible)"}");

        report.AppendLine("=== AVACOM OPS Core · diagnóstico ===");
        Line("Fecha", DateTimeOffset.Now.ToString("yyyy-MM-dd HH:mm:ss zzz"));
        Line("Equipo", Environment.MachineName);
        Line("Usuario", Environment.UserName);
        report.AppendLine();

        report.AppendLine("--- Dónde está corriendo ---");
        Line("Panel (ejecutable)", AppContext.BaseDirectory);
        Line("Raíz de instalación", InstallRoot);
        Line("Runtime de Python", Describe(InstallRoot is null ? null : Path.Combine(InstallRoot, "runtime", "python.exe")));
        Line("API (backend)", Describe(InstallRoot is null ? null : Path.Combine(InstallRoot, "backend", "manage.py")));
        Line("Estado del arranque", apiHost.Status);
        report.AppendLine();

        report.AppendLine("--- Configuración ---");
        var envPath = EnvPath();
        Line("Archivo .env", Describe(envPath));
        foreach (var key in new[] { "DB_ENGINE", "AVACOM_DATA_DIR", "API_PORT", "DJANGO_DEBUG", "DJANGO_ALLOWED_HOSTS" })
            Line("  " + key, ReadEnvValue(key) ?? "(ausente)");
        // La clave se confirma presente pero nunca se imprime.
        Line("  DJANGO_SECRET_KEY", ReadEnvValue("DJANGO_SECRET_KEY") is null ? "(ausente)" : "(presente, oculta)");
        report.AppendLine();

        report.AppendLine("--- Datos ---");
        Line("Carpeta de datos", Describe(DataDirectory));
        Line("¿Escribible?", DataDirectory is null ? null : (CanWrite(DataDirectory) ? "sí" : "NO — la API no podrá guardar respuestas"));
        Line("Base de datos", Describe(DataDirectory is null ? null : Path.Combine(DataDirectory, "db.sqlite3")));
        // Una base dentro de la instalación es el fallo que produce 500: en Program
        // Files un usuario estándar no puede escribirla.
        var strayDb = InstallRoot is null ? null : Path.Combine(InstallRoot, "backend", "db.sqlite3");
        if (strayDb is not null && File.Exists(strayDb))
            report.AppendLine($"  AVISO: hay una base dentro de la instalación ({strayDb}). Si el .env no declara AVACOM_DATA_DIR, la API la usará y fallará al escribir.");
        report.AppendLine();

        report.AppendLine("--- Direcciones ---");
        Line("API de este equipo", endpoint.BaseUrl);
        report.AppendLine();

        report.AppendLine($"--- Registro de la API (últimas {TailLines} líneas) ---");
        report.AppendLine(Tail(ApiLogPath));
        report.AppendLine();
        report.AppendLine($"--- Registro del panel (últimas {TailLines} líneas) ---");
        report.AppendLine(Tail(PanelLogPath));

        return report.ToString();
    }

    private string EnvPath() => InstallRoot is null
        ? Path.Combine(AppContext.BaseDirectory, ".env")
        : Path.Combine(InstallRoot, ".env");

    /// <summary>
    /// Lee una clave del .env sin depender de que la API esté en pie: cuando hay
    /// un 500 es justo lo que no se puede consultar por HTTP.
    /// </summary>
    private string? ReadEnvValue(string key)
    {
        try
        {
            var path = EnvPath();
            if (!File.Exists(path)) return null;
            foreach (var raw in File.ReadLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line.StartsWith('#')) continue;
                var separator = line.IndexOf('=');
                if (separator <= 0) continue;
                if (line[..separator].Trim() == key) return line[(separator + 1)..].Trim();
            }
        }
        catch (Exception exception)
        {
            return $"(no legible: {exception.GetType().Name})";
        }
        return null;
    }

    private static string Describe(string? path)
    {
        if (path is null) return "(no disponible)";
        if (Directory.Exists(path)) return $"{path}  [carpeta]";
        if (!File.Exists(path)) return $"{path}  [NO EXISTE]";
        var info = new FileInfo(path);
        return $"{path}  [{info.Length:N0} bytes, {info.LastWriteTime:yyyy-MM-dd HH:mm}]";
    }

    private static bool CanWrite(string directory)
    {
        // Se comprueba escribiendo de verdad. Los permisos efectivos en Windows
        // dependen de herencias y denegaciones que no se deducen de la ruta.
        try
        {
            Directory.CreateDirectory(directory);
            var probe = Path.Combine(directory, $".probe-{Environment.ProcessId}");
            File.WriteAllText(probe, "x");
            File.Delete(probe);
            return true;
        }
        catch { return false; }
    }

    /// <summary>
    /// Últimas líneas de un registro. Se abre con FileShare.ReadWrite porque la
    /// API lo tiene abierto: sin eso, leerlo mientras corre lanza y el
    /// diagnóstico quedaría vacío justo cuando hace falta.
    /// </summary>
    private static string Tail(string? path)
    {
        if (path is null) return "(ruta no disponible)";
        if (!File.Exists(path)) return $"(no existe: {path})";
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            using var reader = new StreamReader(stream);
            var window = new Queue<string>(TailLines);
            while (reader.ReadLine() is { } line)
            {
                if (window.Count == TailLines) window.Dequeue();
                window.Enqueue(line);
            }
            return window.Count == 0 ? "(vacío)" : string.Join(Environment.NewLine, window);
        }
        catch (Exception exception)
        {
            return $"(no se pudo leer: {exception.Message})";
        }
    }
}
