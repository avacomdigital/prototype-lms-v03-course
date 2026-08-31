using Avacom.Student.Services;

namespace Avacom.Student.ViewModels;

public sealed class FinishedViewModel : ViewModelBase
{
    private readonly ExamSession _session;

    public FinishedViewModel(ExamSession session)
    {
        _session = session;
        BackToCourseCommand = new Command(async () => await Shell.Current.GoToAsync("../.."));
    }

    public string StudentName => _session.StudentName;
    public string CourseTitle => _session.Course?.Title ?? "Curso";
    public string ScoreLabel => _session.Result is null ? "—" : $"{_session.Result.Score:0}/100";
    public string PercentageLabel => _session.Result is null ? "0%" : $"{_session.Result.Percentage}%";
    public string Message => _session.Result?.Percentage switch
    {
        >= 80 => "¡Excelente trabajo! Tu resultado ya está visible para el profesor.",
        >= 60 => "Buen avance. Revisa las respuestas y sigue practicando.",
        _ => "El intento quedó registrado. Cada práctica te ayuda a mejorar.",
    };
    public Command BackToCourseCommand { get; }
}
