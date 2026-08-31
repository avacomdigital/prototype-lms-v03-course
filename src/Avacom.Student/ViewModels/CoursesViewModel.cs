using System.Collections.ObjectModel;
using Avacom.OPS.Core.Models;
using Avacom.OPS.Core.Services;
using Avacom.Student.Pages;
using Avacom.Student.Services;

namespace Avacom.Student.ViewModels;

public sealed class CoursesViewModel : ViewModelBase
{
    /// <summary>
    /// Cada cuánto se vuelve a preguntar mientras la lista está a la vista. El
    /// docente puede instalar o eliminar un curso en cualquier momento y la
    /// tableta suele quedarse en esta pantalla sin que nadie la toque.
    /// </summary>
    private static readonly TimeSpan Intervalo = TimeSpan.FromSeconds(8);

    private readonly ExamSession _session;
    private readonly ILmsApiClient _api;
    private CancellationTokenSource? _vigilancia;
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

    /// <summary>
    /// Corre cada vez que la pantalla aparece.
    ///
    /// Antes solo copiaba la lista cargada al registrarse, así que el estudiante
    /// veía una foto del momento en que entró: si el docente eliminaba un curso
    /// desde el OPS Master, en la tableta seguía apareciendo. Ahora se pinta lo
    /// último conocido para no dejar la pantalla en blanco, se vuelve a preguntar
    /// enseguida, y se sigue preguntando mientras la lista esté a la vista.
    /// </summary>
    public async Task InitializeAsync()
    {
        Notify(nameof(StudentName));
        Notify(nameof(ConnectionLabel));
        Pintar(_session.Courses);
        await RefreshAsync();
        IniciarVigilancia();
    }

    /// <summary>La pantalla se fue: dejar de consultar.</summary>
    public void DetenerVigilancia()
    {
        _vigilancia?.Cancel();
        _vigilancia?.Dispose();
        _vigilancia = null;
    }

    private void IniciarVigilancia()
    {
        DetenerVigilancia();
        var cancelacion = new CancellationTokenSource();
        _vigilancia = cancelacion;

        _ = Task.Run(async () =>
        {
            try
            {
                while (!cancelacion.IsCancellationRequested)
                {
                    await Task.Delay(Intervalo, cancelacion.Token);
                    await MainThread.InvokeOnMainThreadAsync(() => RefreshAsync(silencioso: true));
                }
            }
            catch (OperationCanceledException) { /* la pantalla se fue; es lo esperado */ }
        }, cancelacion.Token);
    }

    /// <summary>
    /// Vuelve a leer el catálogo de esta OPS.
    ///
    /// En modo silencioso —la consulta periódica— no enciende el indicador de
    /// ocupado ni reescribe el mensaje si nada cambió: parpadear cada ocho
    /// segundos sería peor que no avisar.
    /// </summary>
    private async Task RefreshAsync(bool silencioso = false)
    {
        if (!silencioso) IsBusy = true;
        try
        {
            var cursos = await _api.GetCoursesAsync(studentCatalog: true);
            var cambio = !MismosCursos(cursos);
            _session.Courses = cursos;

            if (cambio) Pintar(cursos);
            if (cambio || !silencioso)
            {
                Status = cursos.Count == 0
                    ? "No hay cursos disponibles en esta OPS."
                    : $"{cursos.Count} curso(s) disponibles";
            }
        }
        catch (Exception exception)
        {
            // Se conserva lo último que se vio y se avisa: en el salón vale más una
            // lista vieja y advertida que una pantalla vacía sin explicación.
            if (!silencioso)
                Status = $"Sin respuesta de la OPS; esta lista puede estar desactualizada. {exception.Message}";
        }
        finally { if (!silencioso) IsBusy = false; }
    }

    private bool MismosCursos(IReadOnlyList<Course> cursos) =>
        cursos.Count == Courses.Count
        && cursos.Select(c => c.Id).SequenceEqual(Courses.Select(c => c.Id));

    private void Pintar(IReadOnlyList<Course> cursos)
    {
        Courses.Clear();
        foreach (var curso in cursos) Courses.Add(curso);
    }

    private async Task OpenCourseAsync(Course? course)
    {
        if (course is null) return;
        _session.Course = course;
        await Shell.Current.GoToAsync(nameof(CourseDetailPage));
    }
}
