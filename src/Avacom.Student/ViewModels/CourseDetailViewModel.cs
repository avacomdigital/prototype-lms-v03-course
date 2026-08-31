using Avacom.OPS.Core.Models;
using Avacom.Student.Pages;
using Avacom.Student.Services;

namespace Avacom.Student.ViewModels;

public sealed class CourseDetailViewModel : ViewModelBase
{
    private readonly ExamSession _session;
    private string _status = "Explora las lecciones en orden.";

    public CourseDetailViewModel(ExamSession session)
    {
        _session = session;
        OpenItemCommand = new Command<LessonItem>(async item => await OpenItemAsync(item));
        BackCommand = new Command(async () => await Shell.Current.GoToAsync(".."));
    }

    public Course? Course => _session.Course;
    public string StudentName => _session.StudentName;
    public string Status { get => _status; private set => Set(ref _status, value); }
    public Command<LessonItem> OpenItemCommand { get; }
    public Command BackCommand { get; }

    public void Initialize()
    {
        Notify(nameof(Course));
        Notify(nameof(StudentName));
    }

    private async Task OpenItemAsync(LessonItem? item)
    {
        if (item is null) return;
        if (item.Activity?.IsQuiz == true)
        {
            _session.Activity = item.Activity;
            _session.Attempt = null;
            _session.Result = null;
            await Shell.Current.GoToAsync(nameof(ExamPage));
            return;
        }
        Status = item.Type switch
        {
            "contenido" => $"Recurso listo: {item.Title}",
            "referencia_externa" => $"Referencia disponible: {item.ExternalReference}",
            _ => $"Actividad: {item.Title}",
        };
    }
}
