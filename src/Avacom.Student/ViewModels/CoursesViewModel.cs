using System.Collections.ObjectModel;
using Avacom.OPS.Core.Models;
using Avacom.OPS.Core.Services;
using Avacom.Student.Pages;
using Avacom.Student.Services;

namespace Avacom.Student.ViewModels;

public sealed class CoursesViewModel : ViewModelBase
{
    private readonly ExamSession _session;
    private readonly ILmsApiClient _api;
    private bool _isBusy;
    private string _status = "Cursos sincronizados";

    public CoursesViewModel(ExamSession session, ILmsApiClient api)
    {
        _session = session;
        _api = api;
        OpenCourseCommand = new Command<Course>(async course => await OpenCourseAsync(course));
        RefreshCommand = new Command(async () => await RefreshAsync(), () => !IsBusy);
        DisconnectCommand = new Command(async () => await Shell.Current.GoToAsync("//RegistrationPage"));
    }

    public ObservableCollection<Course> Courses { get; } = [];
    public string StudentName => _session.StudentName;
    public string ConnectionLabel => $"Conectado a {_session.ServerAddress}";
    public string Status { get => _status; private set => Set(ref _status, value); }
    public bool IsBusy { get => _isBusy; private set { Set(ref _isBusy, value); RefreshCommand.ChangeCanExecute(); } }
    public Command<Course> OpenCourseCommand { get; }
    public Command RefreshCommand { get; }
    public Command DisconnectCommand { get; }

    public Task InitializeAsync()
    {
        Courses.Clear();
        foreach (var course in _session.Courses) Courses.Add(course);
        Notify(nameof(StudentName));
        Notify(nameof(ConnectionLabel));
        return Task.CompletedTask;
    }

    private async Task RefreshAsync()
    {
        IsBusy = true;
        try
        {
            _session.Courses = await _api.GetCoursesAsync(studentCatalog: true);
            await InitializeAsync();
            Status = $"{Courses.Count} curso(s) disponibles";
        }
        catch (Exception exception) { Status = $"No se pudo actualizar: {exception.Message}"; }
        finally { IsBusy = false; }
    }

    private async Task OpenCourseAsync(Course? course)
    {
        if (course is null) return;
        _session.Course = course;
        await Shell.Current.GoToAsync(nameof(CourseDetailPage));
    }
}
