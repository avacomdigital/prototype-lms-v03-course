using Avacom.OPS.Core.Configuration;

namespace Avacom.OPS.Core.Tests;

/// <summary>
/// La IP del Master la escribe un docente a mano en el dispositivo, así que la
/// normalización de la URL es la primera línea de defensa contra un examen que no arranca.
/// </summary>
public class ApiEndpointTests
{
    [Theory]
    [InlineData("http://192.168.1.10:8000", "http://192.168.1.10:8000/")]
    [InlineData("http://192.168.1.10:8000/", "http://192.168.1.10:8000/")]
    [InlineData("http://192.168.1.10:8000///", "http://192.168.1.10:8000/")]
    [InlineData("  http://192.168.1.10:8000  ", "http://192.168.1.10:8000/")]
    [InlineData("https://master.lan", "https://master.lan/")]
    public void Normaliza_la_url_a_una_sola_barra_final(string input, string expected)
    {
        Assert.Equal(expected, new ApiEndpoint(input).BaseUrl);
    }

    [Theory]
    [InlineData("http://192.168.1.10:8000", "ws://192.168.1.10:8000/")]
    [InlineData("https://192.168.1.10:8443", "wss://192.168.1.10:8443/")]
    [InlineData("HTTP://192.168.1.10:8000", "ws://192.168.1.10:8000/")]
    public void Traduce_el_esquema_http_al_esquema_websocket(string input, string expected)
    {
        Assert.Equal(expected, new ApiEndpoint(input).WebSocketBaseUri.ToString());
    }

    [Fact]
    public void Construye_la_url_del_estudiante_con_rol_e_identificador()
    {
        var endpoint = new ApiEndpoint("http://192.168.1.10:8000");

        var uri = endpoint.WebSocketForActivity("0123456789abcdef01234567", "student", "attempt-42");

        Assert.Equal("ws://192.168.1.10:8000/ws/activities/0123456789abcdef01234567/?role=student&attempt_id=attempt-42", uri.ToString());
    }

    [Fact]
    public void Construye_la_url_del_profesor_sin_identificador_de_estudiante()
    {
        var endpoint = new ApiEndpoint("http://192.168.1.10:8000");

        var uri = endpoint.WebSocketForActivity("0123456789abcdef01234567", "professor");

        Assert.Equal("ws://192.168.1.10:8000/ws/activities/0123456789abcdef01234567/?role=professor", uri.ToString());
        Assert.DoesNotContain("attempt_id", uri.ToString());
    }

    [Fact]
    public void Conserva_una_ruta_base_cuando_la_api_vive_detras_de_un_prefijo()
    {
        // Escenario de reverse proxy en la sede: http://master.lan/examen/
        var endpoint = new ApiEndpoint("http://master.lan/examen");

        Assert.Equal("http://master.lan/examen/", endpoint.BaseUrl);
        Assert.Equal("ws://master.lan/examen/ws/activities/abc/?role=professor",
            endpoint.WebSocketForActivity("abc", "professor").ToString());
    }

    [Theory]
    [InlineData("")]
    [InlineData("192.168.1.10:8000")]
    [InlineData("no es una url")]
    public void Rechaza_una_direccion_que_no_es_absoluta(string input)
    {
        Assert.ThrowsAny<UriFormatException>(() => new ApiEndpoint(input));
    }

    /// <summary>
    /// La dirección que escribe el profesor se respeta tal cual: el botón prueba
    /// exactamente eso, sin sustituciones silenciosas.
    /// </summary>
    [Theory]
    [InlineData("http://0.0.0.0:8000", "http://0.0.0.0:8000/")]
    [InlineData("http://0.0.0.0:8000/", "http://0.0.0.0:8000/")]
    [InlineData("http://127.0.0.1:8000/", "http://127.0.0.1:8000/")]
    [InlineData("http://192.168.1.10:8000/", "http://192.168.1.10:8000/")]
    [InlineData("http://master.lan:8000/", "http://master.lan:8000/")]
    public void La_direccion_escrita_no_se_reescribe(string input, string expected)
    {
        Assert.Equal(expected, new ApiEndpoint(input).BaseUrl);
    }

    /// <summary>
    /// La dirección de escucha se acepta como entrada —es la que imprime Django— pero
    /// para conectar se usa 127.0.0.1, porque 0.0.0.0 no es un destino válido. Lo
    /// escrito se conserva en BaseUrl para mostrarlo tal cual.
    /// </summary>
    [Theory]
    [InlineData("http://0.0.0.0:8000")]
    [InlineData("http://0.0.0.0:8000/")]
    [InlineData("HTTP://0.0.0.0:8000")]
    [InlineData("http://[::]:8000")]
    public void Una_direccion_de_escucha_se_marca_y_se_conecta_al_equipo_local(string url)
    {
        var endpoint = new ApiEndpoint(url);

        Assert.True(endpoint.IsListenAddress);
        Assert.Equal("http://127.0.0.1:8000/", endpoint.HttpBaseUri.ToString());
        Assert.Equal("ws://127.0.0.1:8000/", endpoint.WebSocketBaseUri.ToString());
    }

    [Fact]
    public void Escribir_la_direccion_de_escucha_no_altera_lo_mostrado()
    {
        var endpoint = new ApiEndpoint("http://0.0.0.0:8000");

        Assert.Equal("http://0.0.0.0:8000/", endpoint.BaseUrl);
    }

    [Fact]
    public void El_websocket_del_estudiante_tambien_queda_alcanzable()
    {
        var endpoint = new ApiEndpoint("http://0.0.0.0:8000");

        Assert.Equal("ws://127.0.0.1:8000/ws/activities/abc/?role=student&attempt_id=attempt-7",
            endpoint.WebSocketForActivity("abc", "student", "attempt-7").ToString());
    }

    [Theory]
    [InlineData("http://127.0.0.1:8000/")]
    [InlineData("http://192.168.1.10:8000/")]
    [InlineData("http://master.lan:8000/")]
    public void Una_direccion_normal_no_se_marca_ni_se_cambia(string url)
    {
        var endpoint = new ApiEndpoint(url);

        Assert.False(endpoint.IsListenAddress);
        Assert.Equal(url, endpoint.BaseUrl);
        Assert.Equal(url, endpoint.HttpBaseUri.ToString());
    }

    [Fact]
    public void El_websocket_usa_la_direccion_escrita_sin_cambios()
    {
        var endpoint = new ApiEndpoint("http://192.168.1.10:8000");

        Assert.Equal("ws://192.168.1.10:8000/ws/activities/abc/?role=professor",
            endpoint.WebSocketForActivity("abc", "professor").ToString());
    }
}
