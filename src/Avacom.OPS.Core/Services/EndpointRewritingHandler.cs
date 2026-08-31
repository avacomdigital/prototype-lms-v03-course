using Avacom.OPS.Core.Configuration;

namespace Avacom.OPS.Core.Services;

/// <summary>
/// Dirige cada petición al Master que el usuario tenga configurado en ese momento.
/// </summary>
/// <remarks>
/// <para>
/// La dirección del Master se escribe a mano en cada dispositivo y puede cambiar entre
/// sedes, así que no se puede fijar en <c>HttpClient.BaseAddress</c>: esa propiedad
/// lanza en cuanto el cliente hizo su primera petición. De ahí que la reescritura viva
/// en un handler.
/// </para>
/// <para>
/// Pero un handler por sí solo no basta: <c>HttpClient.SendAsync</c> valida la URL
/// <b>antes</b> de invocar la cadena de handlers y, si es relativa y no hay
/// BaseAddress, lanza «An invalid request URI was provided. Either the request URI must
/// be an absolute URI or BaseAddress must be set» sin llegar nunca al handler. Por eso
/// el cliente se registra con <see cref="PlaceholderBaseAddress"/>: sólo existe para
/// que esa validación pase, y este handler sustituye el destino real antes de salir a
/// la red.
/// </para>
/// </remarks>
public sealed class EndpointRewritingHandler(Func<ApiEndpoint> endpointProvider) : DelegatingHandler
{
    /// <summary>
    /// Host que nunca se resuelve, usado sólo para satisfacer la validación de
    /// <c>HttpClient</c>. Si alguna petición llegara con este host a la red, significa
    /// que el handler no se ejecutó.
    /// </summary>
    public static readonly Uri PlaceholderBaseAddress = new("http://master.avacom.invalid/");

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        request.RequestUri = Retarget(endpointProvider().HttpBaseUri, request.RequestUri);
        return base.SendAsync(request, cancellationToken);
    }

    /// <summary>
    /// Reapunta la petición al Master conservando ruta y cadena de consulta. Acepta
    /// tanto una URL relativa como una ya combinada contra el marcador.
    /// </summary>
    public static Uri Retarget(Uri baseUri, Uri? requestUri)
    {
        if (requestUri is null) return baseUri;

        var relative = requestUri.IsAbsoluteUri
            ? requestUri.PathAndQuery
            : requestUri.OriginalString;

        return new Uri(baseUri, relative.TrimStart('/'));
    }
}
