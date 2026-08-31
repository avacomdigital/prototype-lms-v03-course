using System.Text.Json;
using Avacom.OPS.Core.Models;

namespace Avacom.OPS.Core.Tests;

public class ContractsTests
{
    [Theory]
    [InlineData(1, "A")]
    [InlineData(3, "C")]
    [InlineData(26, "Z")]
    public void Quiz_option_exposes_letter(int position, string expected) =>
        Assert.Equal(expected, new QuizOption("id", "texto", position).Letter);

    [Fact]
    public void Course_finds_quiz_in_last_lesson_item()
    {
        var quiz = new CourseActivity("a", "Quiz", null, "quiz", "quiz", "automatic", 100, "activa", []);
        var item = new LessonItem("i", 2, "actividad", quiz, null, null, null, "Quiz", "Quiz calificable");
        var lesson = new Lesson("l", "Lección", null, null, null, null, null, 1, "publicado", [item]);
        var section = new CourseSection("s", "Sección", 1, [lesson]);
        var course = new Course("c", "Álgebra", null, "d", new CurriculumFramework("SEP_MX", "SEP México", "MX"), 1,
            "habilitado", "es", [section], [], 1, 1);

        Assert.Equal("a", course.Quiz?.Id);
        Assert.Equal("1 secciones · 1 lecciones · 1 ítems", course.Summary);
    }

    [Fact]
    public void Answer_command_serializes_backend_field_names()
    {
        var json = JsonSerializer.Serialize(QuizAnswerCommand.Create("attempt", "question", "option"));

        Assert.Contains("\"intento_id\":\"attempt\"", json);
        Assert.Contains("\"pregunta_id\":\"question\"", json);
        Assert.Contains("\"opcion_id\":\"option\"", json);
    }
}
