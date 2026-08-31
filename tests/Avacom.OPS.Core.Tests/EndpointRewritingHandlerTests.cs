using Avacom.OPS.Core.Configuration;
using Avacom.OPS.Core.Services;

namespace Avacom.OPS.Core.Tests;

/// <summary>
/// Estas pruebas cubren el hueco que dejó pasar el fallo real: las de
/// Las pruebas anteriores fijaban la BaseAddress a mano, así que nunca
/// ejercitaron la composición que usan las apps. El síntoma en pantalla era
/// «An invalid request URL was provided. Either the request URL must be an absolute
/// URL or BaseAddress must be set», y ninguna petición llegaba a salir.
/// </summary>
public class EndpointRewritingHandlerTests
{
    private static (HttpClient client, StubHttpHandler stub) Build(string masterUrl)
    {
        var stub = new StubHttpHandler(_ => new HttpResponseMessage(System.Net.HttpStatusCode.OK)
        {
            Content = new StringContent("{}", System.Text.Encoding.UTF8, "application/json"),
        });
        var endpoint = new ApiEndpoint(masterUrl);
        var handler = new EndpointRewritingHandler(() => endpoint) { InnerHandler = stub };
        // Igual que en MauiProgram: marcador para que HttpClient acepte rutas relativas.
        var client = new HttpClient(handler) { BaseAddress = EndpointRewritingHandler.PlaceholderBaseAddress };
        return (client, stub);
    }

    [Fact]
    public async Task Una_ruta_relativa_llega_al_master_configurado()
    {
        var (client, stub) = Build("http://192.168.1.10:8000");

        await client.GetAsync("api/courses/");

        Assert.Equal("http://192.168.1.10:8000/api/courses/", stub.Requests[0].RequestUri!.ToString());
    }

    [Fact]
    public async Task El_host_marcador_nunca_sale_a_la_red()
    {
        var (client, stub) = Build("http://192.168.1.10:8000");

        await client.GetAsync("api/enrollments/");

        Assert.DoesNotContain("invalid", stub.Requests[0].RequestUri!.Host);
        Assert.Equal("192.168.1.10", stub.Requests[0].RequestUri!.Host);
    }

    [Fact]
    public async Task Se_conserva_la_cadena_de_consulta()
    {
        var (client, stub) = Build("http://192.168.1.10:8000");

        await client.GetAsync("api/quiz-results/?actividad_id=0123456789abcdef01234567");

        Assert.Equal("http://192.168.1.10:8000/api/quiz-results/?actividad_id=0123456789abcdef01234567",
            stub.Requests[0].RequestUri!.ToString());
    }

    [Fact]
    public async Task Un_post_tambien_se_reapunta()
    {
        var (client, stub) = Build("http://10.0.0.5:8000");

        await client.PostAsync("api/quiz-attempts/answer/", new StringContent("{}"));

        Assert.Equal("http://10.0.0.5:8000/api/quiz-attempts/answer/", stub.Requests[0].RequestUri!.ToString());
        Assert.Equal(HttpMethod.Post, stub.Requests[0].Method);
    }

    [Fact]
    public async Task Cambiar_de_master_entre_peticiones_redirige_la_siguiente()
    {
        // El profesor corrige la dirección y vuelve a pulsar "Probar conexión": la
        // BaseAddress de HttpClient no se puede cambiar después de la primera
        // petición, así que el destino tiene que resolverse en cada envío.
        var stub = new StubHttpHandler(_ => new HttpResponseMessage(System.Net.HttpStatusCode.OK)
        {
            Content = new StringContent("{}"),
        });
        var actual = new ApiEndpoint("http://127.0.0.1:8000");
        var handler = new EndpointRewritingHandler(() => actual) { InnerHandler = stub };
        var client = new HttpClient(handler) { BaseAddress = EndpointRewritingHandler.PlaceholderBaseAddress };

        await client.GetAsync("api/courses/");
        actual = new ApiEndpoint("http://192.168.1.77:9000");
        await client.GetAsync("api/courses/");

        Assert.Equal("http://127.0.0.1:8000/api/courses/", stub.Requests[0].RequestUri!.ToString());
        Assert.Equal("http://192.168.1.77:9000/api/courses/", stub.Requests[1].RequestUri!.ToString());
    }

    [Fact]
    public async Task Respeta_un_master_detras_de_un_prefijo_de_ruta()
    {
        var (client, stub) = Build("http://master.lan/examen");

        await client.GetAsync("api/courses/");

        Assert.Equal("http://master.lan/examen/api/courses/", stub.Requests[0].RequestUri!.ToString());
    }

    [Fact]
    public async Task El_cliente_completo_de_cursos_funciona_sin_BaseAddress_explicita()
    {
        // Composición idéntica a la de MauiProgram, extremo a extremo.
        var stub = new StubHttpHandler(_ => new HttpResponseMessage(System.Net.HttpStatusCode.OK)
        {
            Content = new StringContent(
                """[{"id":"c1","titulo":"Demo","descripcion":"","docente_id":"d","curriculum_framework":{"clave":"SEP_MX","nombre":"SEP México","pais":"MX"},"version":1,"estado":"habilitado","idioma":"es","secciones":[],"inscripciones":[],"total_lecciones":0,"total_items":0}]""",
                System.Text.Encoding.UTF8, "application/json"),
        });
        var endpoint = new ApiEndpoint("http://192.168.1.10:8000");
        var client = new HttpClient(new EndpointRewritingHandler(() => endpoint) { InnerHandler = stub })
        {
            BaseAddress = EndpointRewritingHandler.PlaceholderBaseAddress,
        };
        var api = new LmsApiClient(client);

        var courses = await api.GetCoursesAsync();

        Assert.Equal("Demo", courses[0].Title);
        Assert.Equal("http://192.168.1.10:8000/api/courses/", stub.Requests[0].RequestUri!.ToString());
    }

    [Theory]
    [InlineData("http://192.168.1.10:8000/", "api/students/", "http://192.168.1.10:8000/api/students/")]
    [InlineData("http://192.168.1.10:8000/", "/api/students/", "http://192.168.1.10:8000/api/students/")]
    [InlineData("http://192.168.1.10:8000/", "http://master.avacom.invalid/api/students/", "http://192.168.1.10:8000/api/students/")]
    public void Reapunta_rutas_relativas_y_absolutas_por_igual(string baseUrl, string request, string expected)
    {
        var result = EndpointRewritingHandler.Retarget(new Uri(baseUrl), new Uri(request, UriKind.RelativeOrAbsolute));

        Assert.Equal(expected, result.ToString());
    }
}
