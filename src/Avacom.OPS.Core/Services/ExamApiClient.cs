using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Avacom.OPS.Core.Models;

namespace Avacom.OPS.Core.Services;

public interface ILmsApiClient
{
    Task<bool> CheckHealthAsync(CancellationToken cancellationToken = default);
    Task<IReadOnlyList<Course>> GetCoursesAsync(bool studentCatalog = false, CancellationToken cancellationToken = default);
    Task<Course> GetCourseAsync(string courseId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<CurriculumFramework>> GetFrameworksAsync(CancellationToken cancellationToken = default);
    Task<Course> CreateCourseDraftAsync(CourseDraftCommand command, CancellationToken cancellationToken = default);

    /// <summary>Lee el paquete sin escribir nada, para que el docente confirme.</summary>
    Task<CoursePackagePreview> InspectCoursePackageAsync(string packageJson, CancellationToken cancellationToken = default);

    /// <summary>Instala el paquete en el backend y lo deja disponible para las tabletas.</summary>
    Task<CoursePackageImportResult> ImportCoursePackageAsync(
        string packageJson, CoursePackageImportOptions options, CancellationToken cancellationToken = default);
    Task<CourseEnrollment> EnrollStudentAsync(string courseId, string personId, CancellationToken cancellationToken = default);
    Task<QuizAttempt> StartQuizAsync(string activityId, string studentName, string personId, string deviceId, CancellationToken cancellationToken = default);
    Task ReportProgressAsync(string attemptId, int question, CancellationToken cancellationToken = default);
    Task SaveAnswerAsync(QuizAnswerCommand command, CancellationToken cancellationToken = default);
    Task<QuizAttempt> FinishQuizAsync(string attemptId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<QuizAttempt>> GetQuizResultsAsync(string activityId, CancellationToken cancellationToken = default);
    Task<QuizResultDetail> GetQuizResultAsync(string attemptId, CancellationToken cancellationToken = default);
}

public sealed class LmsApiClient(HttpClient httpClient) : ILmsApiClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<bool> CheckHealthAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            using var response = await httpClient.GetAsync("health/", HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            return response.IsSuccessStatusCode;
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or UriFormatException or InvalidOperationException)
        {
            return false;
        }
    }

    public async Task<IReadOnlyList<Course>> GetCoursesAsync(bool studentCatalog = false, CancellationToken cancellationToken = default) =>
        await GetAsync<List<Course>>(studentCatalog ? "api/courses/?student=1" : "api/courses/", cancellationToken);

    public Task<Course> GetCourseAsync(string courseId, CancellationToken cancellationToken = default) =>
        GetAsync<Course>($"api/courses/{courseId}/", cancellationToken);

    public async Task<IReadOnlyList<CurriculumFramework>> GetFrameworksAsync(CancellationToken cancellationToken = default) =>
        await GetAsync<List<CurriculumFramework>>("api/curriculum-frameworks/", cancellationToken);

    public Task<CoursePackagePreview> InspectCoursePackageAsync(string packageJson, CancellationToken cancellationToken = default) =>
        PostRawAsync<CoursePackagePreview>("api/course-packages/inspect/", packageJson, cancellationToken);

    /// <summary>
    /// El paquete se manda TAL CUAL, sin volver a serializarlo: cualquier
    /// round-trip por objetos podría alterar el contenido y su huella dejaría de
    /// cuadrar. Los datos que aporta el docente se inyectan como campos con
    /// guion bajo al margen del paquete.
    /// </summary>
    public Task<CoursePackageImportResult> ImportCoursePackageAsync(
        string packageJson, CoursePackageImportOptions options, CancellationToken cancellationToken = default)
    {
        var extras = new Dictionary<string, object?>();
        if (!string.IsNullOrWhiteSpace(options.Title)) extras["_titulo"] = options.Title!.Trim();
        if (!string.IsNullOrWhiteSpace(options.CurriculumFramework)) extras["_curriculum_framework"] = options.CurriculumFramework;
        if (!string.IsNullOrWhiteSpace(options.TeacherId)) extras["_docente_id"] = options.TeacherId;
        if (!string.IsNullOrWhiteSpace(options.Actor)) extras["_actor"] = options.Actor;
        if (options.Activate.HasValue) extras["_activar"] = options.Activate.Value;

        var cuerpo = MergeIntoJsonObject(packageJson, extras);
        return PostRawAsync<CoursePackageImportResult>("api/course-packages/import/", cuerpo, cancellationToken);
    }

    /// <summary>
    /// Añade claves al objeto JSON de nivel superior conservando todo lo demás
    /// byte a byte. Se usa Utf8JsonWriter en lugar de deserializar a un modelo
    /// porque el paquete tiene campos que el cliente no conoce ni debe conocer.
    /// </summary>
    private static string MergeIntoJsonObject(string json, IDictionary<string, object?> extras)
    {
        using var document = JsonDocument.Parse(json);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
        {
            throw new LmsApiException(0, "El archivo no contiene un objeto JSON.", "lectura del paquete");
        }

        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            foreach (var property in document.RootElement.EnumerateObject())
            {
                if (extras.ContainsKey(property.Name)) continue;
                property.WriteTo(writer);
            }
            foreach (var (clave, valor) in extras)
            {
                switch (valor)
                {
                    case bool flag: writer.WriteBoolean(clave, flag); break;
                    case null: writer.WriteNull(clave); break;
                    default: writer.WriteString(clave, valor.ToString()); break;
                }
            }
            writer.WriteEndObject();
        }
        return Encoding.UTF8.GetString(buffer.ToArray());
    }

    private async Task<T> PostRawAsync<T>(string path, string json, CancellationToken cancellationToken)
    {
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var response = await httpClient.PostAsync(path, content, cancellationToken);
        return await ReadAsync<T>(response, Abbreviate(json), cancellationToken);
    }

    /// <summary>Un paquete puede pesar cientos de KB: el diagnóstico solo necesita el principio.</summary>
    private static string Abbreviate(string json) =>
        json.Length <= 400 ? json : json[..400] + $"… ({json.Length} caracteres)";

    /// <summary>
    /// Crea el curso y recorre las secciones y lecciones que el docente definió en la OPS.
    /// El <c>orden</c> se asigna por posición en la lista, que es lo que el docente ve en
    /// pantalla, y no por un contador fijo.
    /// </summary>
    public async Task<Course> CreateCourseDraftAsync(CourseDraftCommand command, CancellationToken cancellationToken = default)
    {
        var course = await PostAsync<WriteResponse>("api/courses/", new
        {
            titulo = command.Title,
            descripcion = command.Description,
            docente_id = "docente-ops",
            curriculum_framework = command.CurriculumFramework,
            estado = "borrador",
            idioma = "es",
            creado_por = "docente-ops",
        }, cancellationToken);

        for (var s = 0; s < command.Sections.Count; s++)
        {
            var sectionDraft = command.Sections[s];
            var section = await PostAsync<WriteResponse>("api/sections/", new
            {
                curso = course.Id,
                titulo = sectionDraft.Title,
                orden = s + 1,
                creado_por = "docente-ops",
            }, cancellationToken);

            for (var l = 0; l < sectionDraft.Lessons.Count; l++)
            {
                await CreateLessonAsync(section.Id, sectionDraft.Lessons[l], l + 1, cancellationToken);
            }
        }

        return await GetCourseAsync(course.Id, cancellationToken);
    }

    private Task<WriteResponse> CreateLessonAsync(string sectionId, LessonDraft lesson, int order, CancellationToken cancellationToken) =>
        PostAsync<WriteResponse>("api/lessons/", new
        {
            seccion = sectionId,
            titulo = lesson.Title,
            descripcion = string.IsNullOrWhiteSpace(lesson.Description)
                ? "Contenido por desarrollar en el editor del curso."
                : lesson.Description,
            // CharField(64) en el modelo: se recorta aquí para que un pegado largo del
            // docente no vuelva como un 400 desde el serializer.
            competency_framework = Truncate(lesson.CompetencyFramework, 64),
            learning_outcome = string.IsNullOrWhiteSpace(lesson.LearningOutcome)
                ? "Aprendizaje esperado por definir."
                : lesson.LearningOutcome,
            skills = "Modelar · Resolver · Comunicar",
            attitudes_values = "Curiosidad y colaboración.",
            orden = order,
            estado = "draft",
            creado_por = "docente-ops",
        }, cancellationToken);

    private static string? Truncate(string? value, int max) =>
        string.IsNullOrWhiteSpace(value) ? null
        : value.Length <= max ? value.Trim()
        : value.Trim()[..max];

    public Task<CourseEnrollment> EnrollStudentAsync(string courseId, string personId, CancellationToken cancellationToken = default) =>
        PostAsync<CourseEnrollment>("api/enrollments/", new { curso = courseId, persona_id = personId, estado = "activa", creado_por = "docente-ops" }, cancellationToken);

    public Task<QuizAttempt> StartQuizAsync(string activityId, string studentName, string personId, string deviceId, CancellationToken cancellationToken = default) =>
        PostAsync<QuizAttempt>("api/quiz-attempts/start/", new
        {
            actividad_id = activityId,
            nombre_estudiante = studentName,
            persona_id = personId,
            device_id = deviceId,
        }, cancellationToken);

    public async Task ReportProgressAsync(string attemptId, int question, CancellationToken cancellationToken = default) =>
        _ = await PostAsync<QuizAttempt>("api/quiz-attempts/progress/", new { intento_id = attemptId, pregunta_actual = question }, cancellationToken);

    public async Task SaveAnswerAsync(QuizAnswerCommand command, CancellationToken cancellationToken = default) =>
        _ = await PostAsync<JsonElement>("api/quiz-attempts/answer/", command, cancellationToken);

    public Task<QuizAttempt> FinishQuizAsync(string attemptId, CancellationToken cancellationToken = default) =>
        PostAsync<QuizAttempt>("api/quiz-attempts/finish/", new { intento_id = attemptId }, cancellationToken);

    public async Task<IReadOnlyList<QuizAttempt>> GetQuizResultsAsync(string activityId, CancellationToken cancellationToken = default) =>
        await GetAsync<List<QuizAttempt>>($"api/quiz-results/?actividad_id={Uri.EscapeDataString(activityId)}", cancellationToken);

    public Task<QuizResultDetail> GetQuizResultAsync(string attemptId, CancellationToken cancellationToken = default) =>
        GetAsync<QuizResultDetail>($"api/quiz-results/{attemptId}/", cancellationToken);

    private async Task<T> GetAsync<T>(string path, CancellationToken cancellationToken)
    {
        using var response = await httpClient.GetAsync(path, cancellationToken);
        return await ReadAsync<T>(response, null, cancellationToken);
    }

    private async Task<T> PostAsync<T>(string path, object body, CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(body, body.GetType(), JsonOptions);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var response = await httpClient.PostAsync(path, content, cancellationToken);
        return await ReadAsync<T>(response, json, cancellationToken);
    }

    private static async Task<T> ReadAsync<T>(HttpResponseMessage response, string? sentBody, CancellationToken cancellationToken)
    {
        if (!response.IsSuccessStatusCode)
        {
            var detail = await response.Content.ReadAsStringAsync(cancellationToken);
            throw new LmsApiException((int)response.StatusCode, detail, Describe(response, sentBody));
        }
        return await response.Content.ReadFromJsonAsync<T>(JsonOptions, cancellationToken)
            ?? throw new LmsApiException((int)response.StatusCode, "La API devolvió una respuesta vacía.", Describe(response, sentBody));
    }

    private static string Describe(HttpResponseMessage response, string? sentBody)
    {
        var request = response.RequestMessage;
        var line = request is null ? "(petición no disponible)" : $"{request.Method} {request.RequestUri}";
        return sentBody is null ? line : $"{line}\nEnviado: {sentBody}";
    }

    private sealed record WriteResponse([property: JsonPropertyName("id")] string Id);
}

public sealed class LmsApiException(int statusCode, string responseBody, string requestDescription = "")
    : Exception($"La API respondió {statusCode}: {responseBody}")
{
    public int StatusCode { get; } = statusCode;
    public string ResponseBody { get; } = responseBody;
    public string RequestDescription { get; } = requestDescription;
    public string ToDiagnostic() => string.IsNullOrEmpty(RequestDescription)
        ? Message
        : $"{RequestDescription}\nRespuesta {StatusCode}: {ResponseBody}";
}
