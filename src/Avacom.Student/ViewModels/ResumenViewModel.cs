using System.Collections.ObjectModel;
using Avacom.OPS.Core.Models;
using Avacom.OPS.Core.Services;
using Avacom.Student.Services;

namespace Avacom.Student.ViewModels;

/// <summary>
/// El resumen del alumno: sus cursos, si el material está en el equipo, y la
/// estructura de lo que puede abrir.
///
/// Es la versión para tableta de lo que el docente ve en el panel, con dos
/// diferencias deliberadas:
///
///   · No hay NADA que borre ni desinstale. Ni un botón, ni una llamada. Solo
///     se piden cuatro rutas de lectura; las destructivas no se tocan desde
///     este proyecto.
///   · Cuando el material no está, el mensaje es otro. Al docente le sirve
///     saber que se desinstaló un paquete; al alumno le sirve saber que su
///     avance sigue guardado y que no tiene que hacer nada.
/// </summary>
public sealed class ResumenViewModel : ViewModelBase
{
    private readonly ExamSession _session;
    private readonly ILmsApiClient _api;
    private readonly ILocalLog _log;

    private bool _isBusy;
    private string _status = "";
    private string _resumen = "";
    private bool _sinConexion;
    private CursoDelEstudiante? _cursoElegido;
    private CursoContenido? _contenidoDelCurso;
    private Course? _arbol;
    private long _actualizadoEn;

    public ResumenViewModel(ExamSession session, ILmsApiClient api, ILocalLog log)
    {
        _session = session;
        _api = api;
        _log = log;
        RefreshCommand = new Command(async () => await RefreshAsync(), () => !IsBusy);
        SelectCommand = new Command<CursoDelEstudiante>(
            async curso => await SeleccionarAsync(curso));
        DisconnectCommand = new Command(async () => await Shell.Current.GoToAsync("//RegistrationPage"));
    }

    public ObservableCollection<CursoDelEstudiante> Cursos { get; } = [];

    /// <summary>Los elementos que la biblioteca del aula ofrece del curso elegido.</summary>
    public ObservableCollection<ContenidoElemento> Contenido { get; } = [];

    /// <summary>La estructura del curso: secciones y lecciones, como en el panel.</summary>
    public ObservableCollection<CourseSection> Secciones { get; } = [];

    public string StudentName => _session.StudentName;
    public string ConnectionLabel => $"{_session.ServerAddress}  ·  equipo {_session.HostId}";

    public bool IsBusy
    {
        get => _isBusy;
        private set { Set(ref _isBusy, value); RefreshCommand.ChangeCanExecute(); }
    }

    public string Status { get => _status; private set => Set(ref _status, value); }
    public string Resumen { get => _resumen; private set => Set(ref _resumen, value); }

    /// <summary>El nodo dejó de responder. Se dice, y se conserva lo último visto.</summary>
    public bool SinConexion
    {
        get => _sinConexion;
        private set => Set(ref _sinConexion, value);
    }

    public bool HayCursos => Cursos.Count > 0;
    public bool SinCursos => Cursos.Count == 0 && !SinConexion;

    public CursoDelEstudiante? CursoElegido
    {
        get => _cursoElegido;
        private set
        {
            Set(ref _cursoElegido, value);
            Notify(nameof(HayCursoElegido));
            Notify(nameof(CursoNoDisponible));
        }
    }

    public bool HayCursoElegido => CursoElegido is not null;

    /// <summary>
    /// El curso elegido no tiene su material en el equipo. Es lo que enciende el
    /// aviso de «contenido no disponible».
    /// </summary>
    public bool CursoNoDisponible => CursoElegido is not null && !CursoElegido.Available;

    /// <summary>
    /// El veredicto del curso tal como lo publica el backend. Se pide SIN
    /// `?sanear=1`: una tableta informa, no arregla registros.
    /// </summary>
    public CursoContenido? ContenidoDelCurso
    {
        get => _contenidoDelCurso;
        private set
        {
            Set(ref _contenidoDelCurso, value);
            Notify(nameof(HayContenido));
            Notify(nameof(EstructuraVisible));
        }
    }

    public bool HayContenido => Contenido.Count > 0;

    /// <summary>
    /// La estructura se esconde cuando no hay material que abrir, igual que en el
    /// panel: enseñar lecciones cuyo contenido no está promete algo que la
    /// tableta no puede cumplir.
    /// </summary>
    public bool EstructuraVisible =>
        Secciones.Count > 0 && ContenidoDelCurso?.StructureVisible != false;

    public bool HayEstructura => Secciones.Count > 0;

    public string ActualizadoLabel => _actualizadoEn == 0
        ? ""
        : $"Actualizado a las {DateTimeOffset.FromUnixTimeMilliseconds(_actualizadoEn).ToLocalTime():HH:mm:ss}";

    public Command RefreshCommand { get; }
    public Command<CursoDelEstudiante> SelectCommand { get; }
    public Command DisconnectCommand { get; }

    public async Task InitializeAsync()
    {
        Notify(nameof(StudentName));
        Notify(nameof(ConnectionLabel));
        await RefreshAsync();
    }

    /// <summary>
    /// Vuelve a preguntar si el material sigue en el equipo.
    ///
    /// Es lo que hace el botón «Actualizar», y es la razón de que exista: el
    /// docente puede retirar material en cualquier momento y el alumno tiene que
    /// poder comprobarlo él mismo en vez de esperar.
    /// </summary>
    private async Task RefreshAsync()
    {
        IsBusy = true;
        Status = "Comprobando el material del aula…";
        try
        {
            var respuesta = await _api.GetStudentCoursesAsync(_session.PersonId, _session.HostId);
            SinConexion = false;

            var elegido = CursoElegido?.CourseId;
            Cursos.Clear();
            foreach (var curso in respuesta.Courses) Cursos.Add(curso);
            Notify(nameof(HayCursos));
            Notify(nameof(SinCursos));

            Resumen = respuesta.Summary;
            _actualizadoEn = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            Notify(nameof(ActualizadoLabel));

            // Se mantiene el curso que el alumno estaba mirando; si desapareció
            // de su matrícula, se cae al primero.
            var reelegir = Cursos.FirstOrDefault(c => c.CourseId == elegido) ?? Cursos.FirstOrDefault();
            await SeleccionarAsync(reelegir);

            Status = respuesta.HasUnavailable
                ? $"{respuesta.Unavailable.Count} curso(s) no tienen su material en el equipo ahora mismo."
                : "Todo tu material está disponible.";
        }
        catch (Exception excepcion)
        {
            // Se conserva lo último visto: en el salón vale más una lista vieja y
            // advertida que una pantalla en blanco.
            SinConexion = true;
            Status = $"No hay respuesta del equipo del aula. Se muestra lo último que se vio. "
                   + $"({excepcion.Message})";
            await _log.WriteAsync("resumen", "refresh_failed", excepcion);
        }
        finally { IsBusy = false; }
    }

    /// <summary>
    /// Carga el contenido y la estructura del curso elegido.
    ///
    /// Dos llamadas de lectura: el veredicto del curso —que dice si su material
    /// sigue en el equipo y qué elementos ofrece la biblioteca— y el árbol del
    /// catálogo, que es el que trae secciones y lecciones.
    /// </summary>
    private async Task SeleccionarAsync(CursoDelEstudiante? curso)
    {
        CursoElegido = curso;
        Contenido.Clear();
        Secciones.Clear();
        ContenidoDelCurso = null;
        _arbol = null;

        if (curso is null)
        {
            Notify(nameof(HayContenido));
            Notify(nameof(HayEstructura));
            Notify(nameof(EstructuraVisible));
            return;
        }

        try
        {
            var veredicto = await _api.GetCursoContenidoAsync(curso.CourseId);
            ContenidoDelCurso = veredicto;
            foreach (var elemento in veredicto.Elements) Contenido.Add(elemento);

            // El árbol solo llega si el curso está disponible: el catálogo del
            // estudiante ya esconde lo que no se puede abrir. Que no llegue no es
            // un error, es la respuesta.
            var catalogo = await _api.GetCoursesAsync(studentCatalog: true);
            _arbol = catalogo.FirstOrDefault(c => c.Id == curso.CourseId);
            foreach (var seccion in _arbol?.Sections ?? []) Secciones.Add(seccion);
        }
        catch (Exception excepcion)
        {
            await _log.WriteAsync("resumen", "curso_failed", excepcion);
        }
        finally
        {
            Notify(nameof(HayContenido));
            Notify(nameof(HayEstructura));
            Notify(nameof(EstructuraVisible));
        }
    }
}
