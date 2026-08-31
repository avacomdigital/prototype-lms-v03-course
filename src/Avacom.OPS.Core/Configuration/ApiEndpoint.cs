namespace Avacom.OPS.Core.Configuration;

/// <summary>
/// Dirección del Master. Separa lo que el usuario escribe de lo que se puede usar
/// como destino de una conexión, porque no siempre coinciden.
/// </summary>
public sealed class ApiEndpoint
{
    /// <summary>
    /// Direcciones con las que un servidor escucha en todas las interfaces. Son las
    /// correctas para <c>runserver 0.0.0.0:8000</c> y aparecen impresas en la consola
    /// de Django, así que es natural copiarlas. Como destino, en cambio, la capa de
    /// sockets las rechaza: "unspecified addresses that cannot be used as a target
    /// address".
    /// </summary>
    private static readonly string[] ListenOnlyHosts = ["0.0.0.0", "::", "[::]", "::0", "0:0:0:0:0:0:0:0"];

    public ApiEndpoint(string baseUrl)
    {
        BaseUrl = Normalize(baseUrl);
        var written = new Uri(BaseUrl, UriKind.Absolute);

        IsListenAddress = ListenOnlyHosts.Contains(written.Host, StringComparer.OrdinalIgnoreCase);

        // Escuchar en 0.0.0.0 incluye este equipo, así que desde el propio Master el
        // destino equivalente es 127.0.0.1. Se resuelve sólo para conectar: BaseUrl
        // conserva intacto lo que se escribió, para mostrarlo y para guardarlo.
        var reachable = IsListenAddress
            ? new UriBuilder(written) { Host = "127.0.0.1" }.Uri
            : written;

        HttpBaseUri = reachable;
        WebSocketBaseUri = ToWebSocketScheme(reachable);
    }

    /// <summary>La dirección tal como se escribió, sin sustituciones.</summary>
    public string BaseUrl { get; }

    /// <summary>
    /// Indica que se escribió una dirección de escucha y que, para conectar, se está
    /// usando 127.0.0.1 en su lugar. La interfaz lo informa en lugar de hacerlo callado.
    /// </summary>
    public bool IsListenAddress { get; }

    /// <summary>Destino alcanzable para las peticiones HTTP.</summary>
    public Uri HttpBaseUri { get; }

    /// <summary>Destino alcanzable para el WebSocket.</summary>
    public Uri WebSocketBaseUri { get; }

    public Uri WebSocketForActivity(string activityId, string role, string? attemptId = null)
    {
        var query = $"role={Uri.EscapeDataString(role)}";
        if (!string.IsNullOrWhiteSpace(attemptId))
            query += $"&attempt_id={Uri.EscapeDataString(attemptId)}";
        return new Uri(WebSocketBaseUri, $"ws/activities/{Uri.EscapeDataString(activityId)}/?{query}");
    }

    private static Uri ToWebSocketScheme(Uri uri)
    {
        var builder = new UriBuilder(uri)
        {
            Scheme = uri.Scheme.Equals("https", StringComparison.OrdinalIgnoreCase) ? "wss" : "ws",
        };
        // Sin esto, un http sin puerto explícito saldría como ws://host:80/.
        if (uri.IsDefaultPort) builder.Port = -1;
        return builder.Uri;
    }

    private static string Normalize(string value) => value.Trim().TrimEnd('/') + "/";
}
