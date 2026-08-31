using Avacom.OPS.Core.Models;

namespace Avacom.Student.Services;

public sealed class ExamSession
{
    public string StudentName { get; set; } = "";
    public string PersonId { get; set; } = "";
    public string ServerAddress { get; set; } = "";
    public IReadOnlyList<Course> Courses { get; set; } = [];
    public Course? Course { get; set; }
    public CourseActivity? Activity { get; set; }
    public QuizAttempt? Attempt { get; set; }
    public QuizAttempt? Result { get; set; }
    public bool IsExamInProgress { get; set; }
}
