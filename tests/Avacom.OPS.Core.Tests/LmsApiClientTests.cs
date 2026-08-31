using System.Net;
using Avacom.OPS.Core.Models;
using Avacom.OPS.Core.Services;

namespace Avacom.OPS.Core.Tests;

public class LmsApiClientTests
{
    [Fact]
    public async Task Reads_nested_course_catalog()
    {
        const string json = """
        [{
          "id":"c1","titulo":"Álgebra Octavo B","descripcion":"Demo","docente_id":"d1",
          "curriculum_framework":{"clave":"SEP_MX","nombre":"SEP México","pais":"MX"},
          "version":1,"estado":"habilitado","idioma":"es","secciones":[],"inscripciones":[],
          "total_lecciones":0,"total_items":0
        }]
        """;
        var handler = new StubHttpHandler(_ => StubHttpHandler.Json(json));
        var api = new LmsApiClient(new HttpClient(handler) { BaseAddress = new Uri("http://localhost/") });

        var courses = await api.GetCoursesAsync(studentCatalog: true);

        Assert.Equal("Álgebra Octavo B", courses[0].Title);
        Assert.Equal("SEP México", courses[0].Framework.Name);
        Assert.Equal("/api/courses/?student=1", handler.Requests[0].RequestUri!.PathAndQuery);
    }

    [Fact]
    public async Task Posts_quiz_answer_with_idempotency_event()
    {
        var handler = new StubHttpHandler(_ => StubHttpHandler.Json("""{"saved":true,"answer_id":"x"}""", HttpStatusCode.Created));
        var api = new LmsApiClient(new HttpClient(handler) { BaseAddress = new Uri("http://localhost/") });

        await api.SaveAnswerAsync(QuizAnswerCommand.Create("a1", "q1", "o1"));
        var body = await handler.Requests[0].Content!.ReadAsStringAsync();

        Assert.Equal("/api/quiz-attempts/answer/", handler.Requests[0].RequestUri!.AbsolutePath);
        Assert.Contains("\"intento_id\":\"a1\"", body);
        Assert.Contains("client_event_id", body);
    }

    [Fact]
    public async Task Reports_api_errors_with_request_context()
    {
        var handler = new StubHttpHandler(_ => StubHttpHandler.Json("""{"detail":"invalid"}""", HttpStatusCode.BadRequest));
        var api = new LmsApiClient(new HttpClient(handler) { BaseAddress = new Uri("http://localhost/") });

        var exception = await Assert.ThrowsAsync<LmsApiException>(() => api.EnrollStudentAsync("c1", "ada"));

        Assert.Equal(400, exception.StatusCode);
        Assert.Contains("api/enrollments", exception.RequestDescription);
    }
}
