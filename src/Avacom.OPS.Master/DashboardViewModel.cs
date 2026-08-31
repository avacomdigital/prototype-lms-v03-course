using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using Avacom.OPS.Core.Configuration;
using Avacom.OPS.Core.Models;
using Avacom.OPS.Core.Services;

namespace Avacom.OPS.Master;

public sealed class DashboardViewModel : INotifyPropertyChanged, IAsyncDisposable
{
    private static readonly TimeSpan HealthInterval = TimeSpan.FromSeconds(5);
    private readonly ILmsApiClient _api;
    private readonly ILmsRealtimeClient _realtime;
    private readonly MasterEndpointSettings _endpoint;
    private readonly ILocalLog _log;
    private readonly Services.LocalApiHost _apiHost;
    private readonly Services.ApiDiagnostics _diagnostics;
    private readonly Services.IPackageFileSource _packageFiles;
    private CancellationTokenSource? _healthCts;
    private CancellationTokenSource? _realtimeCts;
    private string? _realtimeKey;
    private IReadOnlyList<LocalNetworkAddress> _addresses = [];
    private Course? _selectedCourse;
    private QuizResultDetail? _selectedDetail;
    private string _currentView = "overview";
    private bool _isBusy;
    private bool _loaded;
    private bool _isApiOnline;
    private bool _isApiOffline;
    private string _apiStatusText = "Comprobando la API…";
    private string _connectionStatus = "Preparando el aula…";
    private string _serverUrl;
    private string _studentUrl = "";
    private string _addressHint = "";
    private int _connectedStudents;
    private int _wizardStep = 1;
    private string _assignmentPerson = "";
    private string _newTitle = "";
    private string _newDescription = "";
    private CurriculumFramework? _newFrameworkItem;
    private string _importFileName = "";
    private InstalledCourseCard? _courseToDelete;
    private CourseUninstallResult? _deleteResult;
    private string _deleteStatus = "Elige el curso que quieres retirar de esta OPS.";
    private Services.PackageFile? _importFile;
    private ZipPackageDetected? _importZipDetected;
    private ZipInstallResult? _importZipResult;
    private string _importTitle = "";
    private string _importStatus = "Abre un paquete .zip (SCORM o CMI5) o un .json de AVACOM.";
    private CurriculumFramework? _importFramework;
    private CoursePackagePreview? _importPreview;
    private CoursePackageImportResult? _importResult;

    public DashboardViewModel(
        ILmsApiClient api,
        ILmsRealtimeClient realtime,
        MasterEndpointSettings endpoint,
        ILocalLog log,
        Services.LocalApiHost apiHost,
        Services.ApiDiagnostics diagnostics,
        Services.IPackageFileSource packageFiles)
    {
        _api = api;
        _realtime = realtime;
        _endpoint = endpoint;
        _log = log;
        _apiHost = apiHost;
        _diagnostics = diagnostics;
        _packageFiles = packageFiles;
        _serverUrl = endpoint.BaseUrl;

        ShowOverviewCommand = new Command(() => CurrentView = "overview");
        ShowCreateCommand = new Command(() => CurrentView = "create");
        ShowStudentsCommand = new Command(() => CurrentView = "students");
        ShowResultsCommand = new Command(() => CurrentView = "results");
        RefreshCommand = new Command(async () => await LoadAsync(force: true), () => !IsBusy);
        SelectCourseCommand = new Command<Course>(async course => await SelectCourseAsync(course));
        SelectResultCommand = new Command<QuizAttempt>(async item => await SelectResultAsync(item));
        CloseDetailCommand = new Command(() => SelectedDetail = null);
        AddSectionCommand = new Command(() => AddSection());
        ShowImportCommand = new Command(() => CurrentView = "import");
        ShowDeleteCommand = new Command(async () =>
        {
            CurrentView = "delete";
            // Llegar a la pantalla la deja limpia: el resultado de un borrado
            // anterior es un aviso puntual, no un estado donde quedarse.
            DeleteResult = null;
            CourseToDelete = null;
            await LoadInstalledAsync();
        });
        // Elegir una tarjeta NO elimina: abre la confirmación. El paso destructivo
        // siempre pide un segundo clic.
        SelectForDeletionCommand = new Command<InstalledCourseCard>(tarjeta =>
        {
            DeleteResult = null;
            CourseToDelete = tarjeta;
        });
        CancelDeletionCommand = new Command(() => CourseToDelete = null);
        ConfirmDeletionCommand = new Command(
            async () => await DeleteCourseAsync(),
            () => !IsBusy && CourseToDelete is not null);
        PickPackageCommand = new Command(async () => await PickPackageAsync(), () => !IsBusy);
        ImportPackageCommand = new Command(
            async () => await ImportPackageAsync(),
            () => !IsBusy && (ImportPreview?.CanImport == true || ImportZipDetected is not null));
        ClearImportCommand = new Command(ClearImport);
        NextWizardCommand = new Command(NextWizard);
        PreviousWizardCommand = new Command(() => WizardStep = Math.Max(1, WizardStep - 1));
        CreateCourseCommand = new Command(async () => await CreateCourseAsync(), () => !IsBusy);
        AssignStudentCommand = new Command(async () => await AssignStudentAsync(), () => !IsBusy && SelectedCourse is not null);
        CopyStudentUrlCommand = new Command(async () => await CopyStudentUrlAsync(), () => HasStudentUrl);
        CopyDiagnosticsCommand = new Command(async () => await CopyDiagnosticsAsync());
        OpenLogsFolderCommand = new Command(OpenLogsFolder);
        CloseCommand = new Command(() => Application.Current?.Quit());
        RefreshAddresses();
        // El borrador nunca está vacío: se abre con una sección y una lección, que el
        // docente renombra o amplía con los botones de +.
        AddSection("Fundamentos", "Primera lección");
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public ObservableCollection<Course> Courses { get; } = [];
    public ObservableCollection<QuizAttempt> Results { get; } = [];

    /// <summary>Marcos curriculares que ofrece la API para el desplegable del paso 1.</summary>
    public ObservableCollection<CurriculumFramework> Frameworks { get; } = [];

    /// <summary>
    /// Las secciones del borrador. Cuántas hay y cuántas lecciones lleva cada una lo
    /// decide el docente con los botones de +, no el código.
    /// </summary>
    public ObservableCollection<SectionDraftForm> DraftSections { get; } = [];
    public Command ShowOverviewCommand { get; }
    public Command ShowCreateCommand { get; }
    public Command ShowStudentsCommand { get; }
    public Command ShowResultsCommand { get; }
    public Command RefreshCommand { get; }
    public Command<Course> SelectCourseCommand { get; }
    public Command<QuizAttempt> SelectResultCommand { get; }
    public Command CloseDetailCommand { get; }
    public Command AddSectionCommand { get; }
    public Command ShowImportCommand { get; }
    public Command PickPackageCommand { get; }
    public Command ImportPackageCommand { get; }
    public Command ClearImportCommand { get; }
    public Command ShowDeleteCommand { get; }
    public Command<InstalledCourseCard> SelectForDeletionCommand { get; }
    public Command CancelDeletionCommand { get; }
    public Command ConfirmDeletionCommand { get; }
    public Command NextWizardCommand { get; }
    public Command PreviousWizardCommand { get; }
    public Command CreateCourseCommand { get; }
    public Command AssignStudentCommand { get; }
    public Command CopyStudentUrlCommand { get; }
    public Command CopyDiagnosticsCommand { get; }
    public Command OpenLogsFolderCommand { get; }
    public Command CloseCommand { get; }

    public string CurrentView
    {
        get => _currentView;
        set
        {
            if (!Set(ref _currentView, value)) return;
            Notify(nameof(IsOverview));
            Notify(nameof(IsCreate));
            Notify(nameof(IsImport));
            Notify(nameof(IsDelete));
            Notify(nameof(IsStudents));
            Notify(nameof(IsResults));
            Notify(nameof(PageTitle));
            Notify(nameof(PageSubtitle));
        }
    }

    public bool IsOverview => CurrentView == "overview";
    public bool IsCreate => CurrentView == "create";
    public bool IsImport => CurrentView == "import";
    public bool IsDelete => CurrentView == "delete";
    public bool IsStudents => CurrentView == "students";
    public bool IsResults => CurrentView == "results";
    public string PageTitle => CurrentView switch
    {
        "create" => "Crear un curso",
        "import" => "Importar un curso",
        "delete" => "Eliminar un curso",
        "students" => "Asignar estudiantes",
        "results" => "Actividad en vivo",
        _ => "Panel del curso",
    };
    public string PageSubtitle => CurrentView switch
    {
        "create" => "Construye la estructura esencial en tres pasos claros.",
        "import" => "Abre un .zip SCORM o CMI5 y déjalo disponible en esta OPS.",
        "delete" => "Retira el contenido de esta OPS. El progreso de los estudiantes se conserva.",
        "students" => "Vincula estudiantes al curso seleccionado.",
        "results" => "Sigue la pregunta actual y el consolidado de notas.",
        _ => "Una vista sintetizada de lo que verá el estudiante.",
    };

    public Course? SelectedCourse
    {
        get => _selectedCourse;
        private set
        {
            if (!Set(ref _selectedCourse, value)) return;
            NotifyCourse();
            AssignStudentCommand.ChangeCanExecute();
        }
    }

    public QuizResultDetail? SelectedDetail { get => _selectedDetail; private set { Set(ref _selectedDetail, value); Notify(nameof(HasSelectedDetail)); } }
    public bool HasSelectedDetail => SelectedDetail is not null;
    public string CourseTitle => SelectedCourse?.Title ?? "Sin curso seleccionado";
    public string CourseDescription => SelectedCourse?.Description ?? "Crea o selecciona un curso para comenzar.";
    public string CourseStatus => SelectedCourse?.StatusLabel ?? "Sin publicar";
    public string CourseSummary => SelectedCourse?.Summary ?? "0 secciones · 0 lecciones · 0 ítems";
    public string FrameworkLabel => SelectedCourse?.Framework.Name ?? "Marco curricular";
    public int SectionCount => SelectedCourse?.Sections.Count ?? 0;
    public int LessonCount => SelectedCourse?.TotalLessons ?? 0;
    public int StudentCount => SelectedCourse?.Enrollments.Count ?? 0;
    public string QuizTitle => SelectedCourse?.Quiz?.Title ?? "Sin actividad calificable";
    public string QuizMeta => SelectedCourse?.Quiz?.QuestionCountLabel ?? "Agrega un quiz al último ítem";
    public bool HasQuiz => SelectedCourse?.Quiz is not null;
    public int FinishedCount => Results.Count(item => item.IsFinished);
    public string CompletionLabel => $"{FinishedCount}/{Math.Max(Results.Count, StudentCount)} entregas";
    public string AverageLabel
    {
        get
        {
            var completed = Results.Where(item => item.IsFinished).ToList();
            return completed.Count == 0 ? "—" : $"{completed.Average(item => item.Percentage):0}%";
        }
    }

    public int ConnectedStudents { get => _connectedStudents; private set => Set(ref _connectedStudents, value); }
    public bool IsBusy { get => _isBusy; private set { Set(ref _isBusy, value); RefrescarComandosOcupados(); } }

    /// <summary>
    /// Todo comando cuyo CanExecute lee IsBusy tiene que reevaluarse cuando IsBusy
    /// cambia; si falta uno, su botón queda apagado para siempre. Pasaba con los dos
    /// de la pantalla Importar: se ponen en marcha con IsBusy ya en true, así que la
    /// única oportunidad de volver a habilitarse es esta. Al agregar un comando
    /// nuevo con `() => !IsBusy`, agrégalo también acá.
    /// </summary>
    private void RefrescarComandosOcupados()
    {
        RefreshCommand.ChangeCanExecute();
        PickPackageCommand.ChangeCanExecute();
        ImportPackageCommand.ChangeCanExecute();
        ConfirmDeletionCommand.ChangeCanExecute();
        CreateCourseCommand.ChangeCanExecute();
        AssignStudentCommand.ChangeCanExecute();
    }
    public string ConnectionStatus { get => _connectionStatus; private set => Set(ref _connectionStatus, value); }
    public bool IsApiOnline { get => _isApiOnline; private set => Set(ref _isApiOnline, value); }
    public bool IsApiOffline { get => _isApiOffline; private set => Set(ref _isApiOffline, value); }
    public string ApiStatusText { get => _apiStatusText; private set => Set(ref _apiStatusText, value); }
    public string ServerUrl { get => _serverUrl; set => Set(ref _serverUrl, value); }
    public string StudentUrl { get => _studentUrl; private set { Set(ref _studentUrl, value); Notify(nameof(HasStudentUrl)); CopyStudentUrlCommand.ChangeCanExecute(); } }
    public bool HasStudentUrl => !string.IsNullOrWhiteSpace(StudentUrl);
    public string AddressHint { get => _addressHint; private set => Set(ref _addressHint, value); }

    public int WizardStep
    {
        get => _wizardStep;
        private set
        {
            if (!Set(ref _wizardStep, value)) return;
            Notify(nameof(IsWizardBasics));
            Notify(nameof(IsWizardStructure));
            Notify(nameof(IsWizardReview));
            Notify(nameof(WizardProgress));
        }
    }
    public bool IsWizardBasics => WizardStep == 1;
    public bool IsWizardStructure => WizardStep == 2;
    public bool IsWizardReview => WizardStep == 3;
    public double WizardProgress => WizardStep / 3d;
    public string NewTitle { get => _newTitle; set => Set(ref _newTitle, value); }
    public string NewDescription { get => _newDescription; set => Set(ref _newDescription, value); }

    /// <summary>
    /// Marco curricular elegido. Al cambiarlo se renombra el campo de competencia de
    /// todas las lecciones del borrador: el docente colombiano ve DBA y el mexicano PDA.
    /// </summary>
    public CurriculumFramework? NewFrameworkItem
    {
        get => _newFrameworkItem;
        set
        {
            if (!Set(ref _newFrameworkItem, value)) return;
            Notify(nameof(CompetencyLabel));
            Notify(nameof(CompetencyHint));
            Notify(nameof(FrameworkHelpText));
            ApplyCompetencyLabels();
        }
    }

    /// <summary>Cómo se llama el elemento de competencia en el marco elegido.</summary>
    public string CompetencyLabel => NewFrameworkItem?.CompetencyLabel ?? "Elemento de competencia";
    public string CompetencyHint => NewFrameworkItem?.CompetencyHint ?? "Código del marco de referencia";

    public string FrameworkHelpText => NewFrameworkItem is null
        ? "Elige el marco para que las lecciones pidan el elemento correcto."
        : $"En {NewFrameworkItem.Name} cada lección se ancla a un elemento llamado «{NewFrameworkItem.CompetencyLabel}».";

    // ── IMPORTAR UN PAQUETE DE CURSO ────────────────────────────────────────
    // Tres pasos deliberados: elegir el archivo, revisar qué trae, confirmar.
    // La instalación la hace Django en una transacción; la OPS solo presenta la
    // decisión y su resultado.

    public string ImportFileName { get => _importFileName; private set { Set(ref _importFileName, value); Notify(nameof(HasImportFile)); } }
    public bool HasImportFile => !string.IsNullOrEmpty(ImportFileName);

    public CoursePackagePreview? ImportPreview
    {
        get => _importPreview;
        private set
        {
            Set(ref _importPreview, value);
            Notify(nameof(HasImportPreview));
            Notify(nameof(ImportNeedsDetails));
            Notify(nameof(ImportSummary));
            Notify(nameof(ImportContentSummary));
            Notify(nameof(ImportIntent));
            ImportPackageCommand.ChangeCanExecute();
        }
    }

    /// <summary>
    /// Lo que el backend leyó de un .zip SCORM o CMI5. El ESTÁNDAR concreto lo
    /// detecta él, leyendo imsmanifest.xml o cmi5.xml: la extensión del archivo no
    /// alcanza para saberlo.
    /// </summary>
    public ZipPackageDetected? ImportZipDetected
    {
        get => _importZipDetected;
        private set
        {
            Set(ref _importZipDetected, value);
            Notify(nameof(HasImportPreview));
            Notify(nameof(HasZipDetected));
            Notify(nameof(ImportNeedsDetails));
            Notify(nameof(ImportSummary));
            Notify(nameof(ImportContentSummary));
            Notify(nameof(ImportIntent));
            ImportPackageCommand.ChangeCanExecute();
        }
    }

    public bool HasZipDetected => ImportZipDetected is not null;

    /// <summary>La fila de m05_curso_host que quedó tras instalar el .zip.</summary>
    public ZipInstallResult? ImportZipResult
    {
        get => _importZipResult;
        private set
        {
            Set(ref _importZipResult, value);
            Notify(nameof(HasImportResult));
            Notify(nameof(ImportHostRow));
            Notify(nameof(HasImportHostRow));
        }
    }

    /// <summary>Presencia física registrada: es lo que responde «¿está en esta OPS?».</summary>
    public CourseHostRow? ImportHostRow => ImportZipResult?.Host;
    public bool HasImportHostRow => ImportHostRow is not null;

    /// <summary>Identidad de esta OPS, con la que se registra la presencia.</summary>
    public string HostId
    {
        get => _endpoint.HostId;
        set { _endpoint.HostId = value; Notify(); }
    }

    /// <summary>Los cursos presentes en esta OPS. Una tarjeta por curso.</summary>
    public ObservableCollection<InstalledCourseCard> InstalledCourses { get; } = [];

    public bool HasInstalledCourses => InstalledCourses.Count > 0;
    public bool HasNoInstalledCourses => InstalledCourses.Count == 0;

    /// <summary>
    /// La tarjeta que el docente eligió. Mientras no sea null, la pantalla muestra
    /// la confirmación en lugar de la lista: no se puede eliminar por accidente.
    /// </summary>
    public InstalledCourseCard? CourseToDelete
    {
        get => _courseToDelete;
        private set
        {
            Set(ref _courseToDelete, value);
            Notify(nameof(IsConfirmingDeletion));
            Notify(nameof(IsPickingDeletion));
            ConfirmDeletionCommand.ChangeCanExecute();
        }
    }

    public bool IsConfirmingDeletion => CourseToDelete is not null;

    /// <summary>
    /// La lista y la confirmación se excluyen: una pregunta a la vez. Pero el
    /// RESULTADO no la oculta — antes sí, y como nada limpiaba DeleteResult la
    /// pantalla quedaba atrapada en la tarjeta del último borrado: el curso
    /// desaparecía de la vista aunque siguiera instalado.
    /// </summary>
    public bool IsPickingDeletion => CourseToDelete is null;

    /// <summary>Lo que quedó tras retirar el contenido, con la prueba de lo conservado.</summary>
    public CourseUninstallResult? DeleteResult
    {
        get => _deleteResult;
        private set
        {
            Set(ref _deleteResult, value);
            Notify(nameof(HasDeleteResult));
        }
    }

    public bool HasDeleteResult => DeleteResult is not null;

    public string DeleteStatus { get => _deleteStatus; private set => Set(ref _deleteStatus, value); }

    public bool HasImportPreview => ImportPreview is not null || ImportZipDetected is not null;

    /// <summary>El paquete trae su identificador pero no el título ni el marco: eso lo aporta el docente.</summary>
    public bool ImportNeedsDetails =>
        ImportPreview?.NeedsCourseDetails == true || ImportZipDetected?.NeedsCourseDetails == true;

    // Los tres resúmenes se resuelven contra el paquete que haya, sea .zip o .json,
    // para que el XAML no tenga que ramificar.
    public string ImportSummary =>
        ImportZipDetected?.Counts.Summary ?? ImportPreview?.Summary ?? "";

    public string ImportContentSummary =>
        ImportZipDetected?.Counts.ContentSummary ?? ImportPreview?.ContentSummary ?? "";

    public string ImportIntent =>
        ImportZipDetected?.Intent ?? ImportPreview?.Intent ?? "";

    public string ImportTitle { get => _importTitle; set => Set(ref _importTitle, value); }

    public CurriculumFramework? ImportFramework
    {
        get => _importFramework;
        set => Set(ref _importFramework, value);
    }

    public CoursePackageImportResult? ImportResult
    {
        get => _importResult;
        private set { Set(ref _importResult, value); Notify(nameof(HasImportResult)); }
    }

    public bool HasImportResult => ImportResult is not null || ImportZipResult is not null;

    /// <summary>Titular del resultado, venga de un .zip o del formato nativo.</summary>
    public string ImportHeadline =>
        ImportZipResult?.Headline ?? ImportResult?.Headline ?? "";

    public string ImportDetail =>
        ImportZipResult?.Install.Detail ?? ImportResult?.Detail ?? "";

    public string ImportStatus { get => _importStatus; private set => Set(ref _importStatus, value); }

    public string StructureSummary
    {
        get
        {
            var sections = DraftSections.Count;
            var lessons = DraftSections.Sum(s => s.Lessons.Count);
            var s = sections == 1 ? "1 sección" : $"{sections} secciones";
            var l = lessons == 1 ? "1 lección" : $"{lessons} lecciones";
            return $"{s} · {l} · Estado inicial: borrador";
        }
    }
    public string AssignmentPerson { get => _assignmentPerson; set => Set(ref _assignmentPerson, value); }

    public async Task LoadAsync(bool force = false)
    {
        if (_loaded && !force) return;
        if (!Uri.TryCreate(ServerUrl, UriKind.Absolute, out _))
        {
            ConnectionStatus = "Escribe una dirección completa, por ejemplo http://127.0.0.1:8000/.";
            return;
        }
        IsBusy = true;
        try
        {
            _endpoint.BaseUrl = ServerUrl;
            RefreshAddresses();
            EnsureHealthMonitor();
            ConnectionStatus = "Iniciando la API local…";
            await _apiHost.EnsureRunningAsync();
            await LoadFrameworksAsync();
            var selectedId = SelectedCourse?.Id;
            var items = await _api.GetCoursesAsync();
            Courses.Clear();
            foreach (var item in items) Courses.Add(item);
            SelectedCourse = Courses.FirstOrDefault(course => course.Id == selectedId)
                ?? Courses.FirstOrDefault(course => course.Title == "Álgebra Octavo B")
                ?? Courses.FirstOrDefault();
            await RefreshResultsAsync();
            _loaded = true;
            ConnectionStatus = _endpoint.Current.IsListenAddress
                ? "Conectado localmente por 127.0.0.1; la API escucha en toda la LAN."
                : "Datos del curso sincronizados.";
        }
        catch (Exception exception)
        {
            ConnectionStatus = DescribeFailure(ServerUrl, exception);
            await _log.WriteAsync("api", "dashboard_load_failed", exception);
        }
        finally { IsBusy = false; }
    }

    /// <summary>
    /// Trae los marcos curriculares. Si la lista aún está vacía se preselecciona el
    /// primero, para que el paso 2 ya sepa cómo rotular el campo de competencia.
    /// </summary>
    private async Task LoadFrameworksAsync()
    {
        try
        {
            var frameworks = await _api.GetFrameworksAsync();
            var previous = NewFrameworkItem?.Key;
            Frameworks.Clear();
            foreach (var framework in frameworks) Frameworks.Add(framework);
            NewFrameworkItem = Frameworks.FirstOrDefault(f => f.Key == previous)
                ?? Frameworks.FirstOrDefault();
        }
        catch (Exception exception)
        {
            // No es motivo para abortar la carga del panel: el docente puede seguir
            // viendo cursos y resultados aunque el desplegable quede vacío.
            await _log.WriteAsync("api", "frameworks_load_failed", exception);
        }
    }

    private async Task SelectCourseAsync(Course? course)
    {
        if (course is null) return;
        SelectedCourse = course;
        SelectedDetail = null;
        await RefreshResultsAsync();
    }

    private void NextWizard()
    {
        if (WizardStep == 2)
        {
            var invalid = DraftSections.FirstOrDefault(s => !s.IsValid);
            if (invalid is not null)
            {
                ConnectionStatus = string.IsNullOrWhiteSpace(invalid.Title)
                    ? $"La sección {invalid.Position:00} necesita un nombre."
                    : $"Cada lección de «{invalid.Title.Trim()}» necesita un título.";
                return;
            }
        }
        if (WizardStep == 1 && (string.IsNullOrWhiteSpace(NewTitle) || string.IsNullOrWhiteSpace(NewDescription)))
        {
            ConnectionStatus = "Completa el nombre y la descripción del curso.";
            return;
        }
        WizardStep = Math.Min(3, WizardStep + 1);
    }

    private async Task CreateCourseAsync()
    {
        if (string.IsNullOrWhiteSpace(NewTitle))
        {
            ConnectionStatus = "El curso necesita un nombre.";
            WizardStep = 1;
            return;
        }
        var invalid = DraftSections.FirstOrDefault(s => !s.IsValid);
        if (invalid is not null)
        {
            ConnectionStatus = string.IsNullOrWhiteSpace(invalid.Title)
                ? $"La sección {invalid.Position:00} necesita un nombre."
                : $"Cada lección de «{invalid.Title.Trim()}» necesita un título.";
            WizardStep = 2;
            return;
        }
        if (NewFrameworkItem is null)
        {
            ConnectionStatus = "Elige el marco curricular antes de crear el curso.";
            WizardStep = 1;
            return;
        }

        IsBusy = true;
        try
        {
            var sections = DraftSections
                .Select(s => new SectionDraft(
                    s.Title.Trim(),
                    s.Lessons.Select(l => new LessonDraft(
                        l.Title.Trim(),
                        l.Description.Trim(),
                        l.Competency.Trim(),
                        l.LearningOutcome.Trim())).ToList()))
                .ToList();

            var created = await _api.CreateCourseDraftAsync(new CourseDraftCommand(
                NewTitle.Trim(), NewDescription.Trim(), NewFrameworkItem.Key, sections));
            Courses.Insert(0, created);
            SelectedCourse = created;
            ConnectionStatus = $"Curso «{created.Title}» creado como borrador.";
            ResetWizard();
            CurrentView = "overview";
        }
        catch (Exception exception)
        {
            ConnectionStatus = $"No se pudo crear el curso: {exception.Message}";
            await _log.WriteAsync("courses", "create_failed", exception);
        }
        finally { IsBusy = false; }
    }

    private async Task AssignStudentAsync()
    {
        if (SelectedCourse is null || string.IsNullOrWhiteSpace(AssignmentPerson))
        {
            ConnectionStatus = "Escribe el nombre o identificador del estudiante.";
            return;
        }
        IsBusy = true;
        try
        {
            await _api.EnrollStudentAsync(SelectedCourse.Id, AssignmentPerson.Trim());
            AssignmentPerson = "";
            SelectedCourse = await _api.GetCourseAsync(SelectedCourse.Id);
            ReplaceSelectedCourse();
            ConnectionStatus = "Estudiante asignado correctamente.";
        }
        catch (Exception exception)
        {
            ConnectionStatus = exception is LmsApiException { StatusCode: 400 }
                ? "Ese estudiante ya está asignado o el identificador no es válido."
                : $"No se pudo asignar: {exception.Message}";
            await _log.WriteAsync("enrollments", "assign_failed", exception);
        }
        finally { IsBusy = false; }
    }

    private void ReplaceSelectedCourse()
    {
        if (SelectedCourse is null) return;
        var index = Courses.ToList().FindIndex(course => course.Id == SelectedCourse.Id);
        if (index >= 0) Courses[index] = SelectedCourse;
    }

    private async Task RefreshResultsAsync()
    {
        Results.Clear();
        var quiz = SelectedCourse?.Quiz;
        if (quiz is null)
        {
            StopRealtime();
            NotifyResults();
            return;
        }
        var items = await _api.GetQuizResultsAsync(quiz.Id);
        foreach (var item in items.OrderBy(item => item.IsFinished).ThenBy(item => item.StudentName)) Results.Add(item);
        NotifyResults();
        EnsureRealtime(quiz.Id);
    }

    private async Task SelectResultAsync(QuizAttempt? item)
    {
        if (item is null) return;
        try { SelectedDetail = await _api.GetQuizResultAsync(item.Id); }
        catch (Exception exception) { await _log.WriteAsync("api", "result_detail_failed", exception); }
    }

    private void EnsureRealtime(string activityId)
    {
        var key = $"{_endpoint.BaseUrl}|{activityId}";
        if (_realtimeKey == key && _realtimeCts is { IsCancellationRequested: false }) return;
        StopRealtime();
        _realtimeCts = new CancellationTokenSource();
        _realtimeKey = key;
        _realtime.EventReceived -= OnRealtime;
        _realtime.ConnectionChanged -= OnConnectionChanged;
        _realtime.EventReceived += OnRealtime;
        _realtime.ConnectionChanged += OnConnectionChanged;
        _ = _realtime.RunAsync(_endpoint.Current.WebSocketForActivity(activityId, "professor"), _realtimeCts.Token);
    }

    private void StopRealtime()
    {
        _realtimeCts?.Cancel();
        _realtimeCts?.Dispose();
        _realtimeCts = null;
        _realtimeKey = null;
    }

    private void OnRealtime(object? sender, LmsRealtimeEvent message) => MainThread.BeginInvokeOnMainThread(() =>
    {
        if (message.Type == "presence_changed") ConnectedStudents = message.ConnectedStudents;
        if (message.Type is "student_progress" or "attempt_finished" && message.Attempt is not null)
        {
            var index = Results.ToList().FindIndex(item => item.Id == message.Attempt.Id);
            if (index < 0) Results.Insert(0, message.Attempt); else Results[index] = message.Attempt;
            NotifyResults();
        }
    });

    private void OnConnectionChanged(object? sender, bool connected) => MainThread.BeginInvokeOnMainThread(() =>
        ConnectionStatus = connected ? "LIVE · avance por WebSocket" : "Reconectando el canal en vivo…");

    private void EnsureHealthMonitor()
    {
        if (_healthCts is { IsCancellationRequested: false }) return;
        _healthCts = new CancellationTokenSource();
        _ = MonitorHealthAsync(_healthCts.Token);
    }

    private async Task MonitorHealthAsync(CancellationToken cancellationToken)
    {
        try
        {
            using var timer = new PeriodicTimer(HealthInterval);
            do { await ProbeHealthAsync(cancellationToken); }
            while (await timer.WaitForNextTickAsync(cancellationToken));
        }
        catch (OperationCanceledException) { }
    }

    private async Task ProbeHealthAsync(CancellationToken cancellationToken)
    {
        var healthy = await _api.CheckHealthAsync(cancellationToken);
        if (cancellationToken.IsCancellationRequested) return;
        MainThread.BeginInvokeOnMainThread(() =>
        {
            IsApiOnline = healthy;
            IsApiOffline = !healthy;
            ApiStatusText = healthy ? $"API disponible · 0.0.0.0:{ResolvePort()}" : $"API sin respuesta · {_apiHost.Status}";
        });
    }

    private void RefreshAddresses()
    {
        try { _addresses = LocalNetworkAddresses.Discover(); }
        catch (Exception exception) { _addresses = []; _ = _log.WriteAsync("network", "discover_failed", exception); }
        var preferred = _addresses.FirstOrDefault();
        if (preferred is null)
        {
            StudentUrl = "";
            AddressHint = "Conecta este equipo a la red del aula para obtener una dirección.";
            return;
        }
        StudentUrl = $"http://{preferred.Address}:{ResolvePort()}/";
        var alternatives = _addresses.Skip(1).Select(item => item.Address).ToList();
        AddressHint = alternatives.Count == 0
            ? $"Interfaz {preferred.InterfaceName}"
            : $"Interfaz {preferred.InterfaceName} · alternativas: {string.Join(", ", alternatives)}";
    }

    private int ResolvePort()
    {
        try { return _endpoint.Current.HttpBaseUri.Port; }
        catch { return 8000; }
    }

    private async Task CopyStudentUrlAsync()
    {
        if (!HasStudentUrl) return;
        await Clipboard.Default.SetTextAsync(StudentUrl);
        ConnectionStatus = "Dirección para estudiantes copiada.";
    }

    private async Task CopyDiagnosticsAsync()
    {
        try { await Clipboard.Default.SetTextAsync(_diagnostics.BuildReport()); ConnectionStatus = "Diagnóstico copiado."; }
        catch (Exception exception) { ConnectionStatus = $"No se pudo copiar: {exception.Message}"; }
    }

    private void OpenLogsFolder()
    {
        var folder = _diagnostics.LogsFolder;
        if (folder is null) { ConnectionStatus = "El .env no declara AVACOM_DATA_DIR."; return; }
        try
        {
            Directory.CreateDirectory(folder);
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", $"\"{folder}\"") { UseShellExecute = true });
        }
        catch (Exception exception) { ConnectionStatus = $"No se pudo abrir la carpeta: {exception.Message}"; }
    }

    private static string DescribeFailure(string url, Exception exception) => exception switch
    {
        LmsApiException { StatusCode: 500 } => "La API responde, pero la base de datos falló (500). Copia el diagnóstico para soporte.",
        LmsApiException api => $"La API respondió {api.StatusCode}. Revisa los datos enviados.",
        HttpRequestException => $"No hay respuesta en {url}. Revisa red, puerto y firewall.",
        TaskCanceledException => $"Tiempo de espera agotado contra {url}.",
        _ => $"API no disponible: {exception.Message}",
    };

    /// <summary>
    /// Paso 1 · el docente abre el archivo. Se inspecciona de inmediato contra la
    /// API, que no escribe nada, para poder mostrarle qué trae antes de confirmar.
    /// </summary>
    private async Task PickPackageAsync()
    {
        try
        {
            var archivo = await _packageFiles.PickAsync();
            if (archivo is null) return;

            LimpiarPrevias();
            _importFile = archivo;
            ImportFileName = $"{archivo.Name}  ·  {archivo.SizeLabel}";
            ImportStatus = "Leyendo el paquete…";
            IsBusy = true;

            if (archivo.Kind == Services.PackageKind.Zip)
            {
                // El backend abre el .zip, busca su descriptor y decide si es
                // SCORM 1.2, SCORM 2004 o CMI5. Nada se escribe todavía.
                var detectado = await _api.InspectZipPackageAsync(archivo.Content, archivo.Name);
                ImportZipDetected = detectado;
                ImportTitle = detectado.SuggestedTitle;
                ImportStatus =
                    $"Detectado {detectado.FormatLabel} · {detectado.DescriptorLabel}. {detectado.Intent}";
            }
            else
            {
                var preview = await _api.InspectCoursePackageAsync(archivo.AsJson());
                ImportPreview = preview;
                ImportTitle = preview.SuggestedTitle;
                ImportStatus = preview.Intent;
            }

            ImportFramework ??= Frameworks.FirstOrDefault();
        }
        catch (LmsApiException exception)
        {
            LimpiarPrevias();
            ImportStatus = $"El archivo no se pudo leer: {ExtractDetail(exception.ResponseBody)}";
            await _log.WriteAsync("import", "inspect_failed", exception);
        }
        catch (Exception exception)
        {
            LimpiarPrevias();
            ImportStatus = $"No se pudo abrir el archivo: {exception.Message}";
            await _log.WriteAsync("import", "pick_failed", exception);
        }
        finally { IsBusy = false; }
    }

    /// <summary>
    /// Paso 2 · confirmar. Django instala en una transacción y registra la
    /// presencia en m05_curso_host; si algo falla, la base queda como estaba y
    /// aquí se muestra el motivo.
    /// </summary>
    private async Task ImportPackageAsync()
    {
        if (_importFile is null) return;
        if (ImportPreview is null && ImportZipDetected is null) return;

        if (ImportNeedsDetails && string.IsNullOrWhiteSpace(ImportTitle))
        {
            ImportStatus = "Ponle un nombre al curso antes de importarlo.";
            return;
        }

        IsBusy = true;
        ImportStatus = "Importando…";
        try
        {
            string cursoId;
            if (_importFile.Kind == Services.PackageKind.Zip)
            {
                var opciones = new ZipInstallOptions(
                    HostId: HostId,
                    Title: ImportNeedsDetails ? ImportTitle : null,
                    CurriculumFramework: ImportNeedsDetails ? ImportFramework?.Key : null,
                    Actor: "docente-ops");

                var resultado = await _api.InstallZipPackageAsync(
                    _importFile.Content, _importFile.Name, opciones);
                ImportZipResult = resultado;
                cursoId = resultado.Install.CourseId;
                SoltarPaquete();
                ImportStatus = resultado.IsAvailableToStudents
                    ? $"{resultado.Headline} Ya está disponible en las tabletas de {HostId}."
                    : $"{resultado.Headline} Instalado en {HostId}, sin habilitar todavía.";
            }
            else
            {
                var opciones = new CoursePackageImportOptions(
                    Title: ImportNeedsDetails ? ImportTitle : null,
                    CurriculumFramework: ImportNeedsDetails ? ImportFramework?.Key : null,
                    TeacherId: "docente-ops",
                    Actor: "docente-ops");

                var resultado = await _api.ImportCoursePackageAsync(_importFile.AsJson(), opciones);
                ImportResult = resultado;
                cursoId = resultado.CourseId;
                SoltarPaquete();
                ImportStatus = resultado.IsAvailableToStudents
                    ? $"{resultado.Headline} Ya está disponible en las tabletas."
                    : $"{resultado.Headline} Todavía no está publicada.";
            }

            // El catálogo del panel se recarga para que el curso aparezca en Resumen.
            await LoadAsync(force: true);
            SelectedCourse = Courses.FirstOrDefault(c => c.Id == cursoId) ?? SelectedCourse;
        }
        catch (LmsApiException exception)
        {
            ImportStatus = $"No se importó: {ExtractDetail(exception.ResponseBody)}";
            await _log.WriteAsync("import", "import_failed", exception);
        }
        catch (Exception exception)
        {
            ImportStatus = $"No se importó: {exception.Message}";
            await _log.WriteAsync("import", "import_failed", exception);
        }
        finally { IsBusy = false; }
    }

    /// <summary>Trae las tarjetas de lo que hay presente en esta OPS.</summary>
    private async Task LoadInstalledAsync()
    {
        IsBusy = true;
        try
        {
            var cursos = await _api.GetInstalledCoursesAsync(HostId);
            InstalledCourses.Clear();
            foreach (var curso in cursos) InstalledCourses.Add(curso);

            Notify(nameof(HasInstalledCourses));
            Notify(nameof(HasNoInstalledCourses));
            DeleteStatus = cursos.Count == 0
                ? $"No hay cursos instalados en {HostId}. Importa uno primero."
                : $"{cursos.Count} {(cursos.Count == 1 ? "curso instalado" : "cursos instalados")} en {HostId}.";
        }
        catch (LmsApiException exception)
        {
            DeleteStatus = $"No se pudo leer lo instalado: {ExtractDetail(exception.ResponseBody)}";
            await _log.WriteAsync("delete", "list_failed", exception);
        }
        catch (Exception exception)
        {
            DeleteStatus = $"No se pudo leer lo instalado: {exception.Message}";
            await _log.WriteAsync("delete", "list_failed", exception);
        }
        finally { IsBusy = false; }
    }

    /// <summary>
    /// Retira el contenido. El backend apaga las dos banderas y sella retirado_en;
    /// los estudiantes, el progreso y las calificaciones quedan donde estaban, y
    /// responde el antes y el después para poder afirmarlo y no solo prometerlo.
    /// </summary>
    private async Task DeleteCourseAsync()
    {
        var tarjeta = CourseToDelete;
        if (tarjeta is null) return;

        IsBusy = true;
        DeleteStatus = $"Retirando «{tarjeta.Name}» de {HostId}…";
        try
        {
            var resultado = await _api.UninstallCourseAsync(tarjeta.CourseId, HostId, "docente-ops");
            DeleteResult = resultado;
            CourseToDelete = null;

            DeleteStatus = resultado.Preserved.Intact
                ? $"«{tarjeta.Name}» salió de esta OPS. {resultado.PreservedLabel}"
                : $"«{tarjeta.Name}» salió de esta OPS, pero los conteos cambiaron: revísalo.";

            // La tarjeta desaparece de la lista y el catálogo del panel se recarga,
            // porque el curso ya no debe ofrecerse a las tabletas.
            await LoadInstalledAsync();
            await LoadAsync(force: true);
        }
        catch (LmsApiException exception)
        {
            DeleteStatus = $"No se retiró: {ExtractDetail(exception.ResponseBody)}";
            await _log.WriteAsync("delete", "uninstall_failed", exception);
        }
        catch (Exception exception)
        {
            DeleteStatus = $"No se retiró: {exception.Message}";
            await _log.WriteAsync("delete", "uninstall_failed", exception);
        }
        finally { IsBusy = false; }
    }

    /// <summary>
    /// Tras importar se suelta el archivo y se apaga el botón de confirmar. Si el
    /// paquete quedara cargado, un clic distraído volvería a instalar un curso que
    /// quizá se acaba de eliminar. El resultado sí queda a la vista.
    /// </summary>
    private void SoltarPaquete()
    {
        _importFile = null;
        ImportZipDetected = null;
        ImportPreview = null;
        ImportFileName = "";
    }

    private void LimpiarPrevias()
    {
        ImportPreview = null;
        ImportZipDetected = null;
        ImportResult = null;
        ImportZipResult = null;
    }

    private void ClearImport()
    {
        ImportFileName = "";
        _importFile = null;
        LimpiarPrevias();
        ImportTitle = "";
        ImportStatus = "Abre un paquete .zip (SCORM o CMI5) o un .json de AVACOM.";
    }

    /// <summary>
    /// La API devuelve {"detail": "..."} en los errores. En la OPS no hay teclado
    /// ni consola, así que el motivo tiene que llegar legible a la pantalla.
    /// </summary>
    private static string ExtractDetail(string responseBody)
    {
        if (string.IsNullOrWhiteSpace(responseBody)) return "la API no explicó el motivo.";
        try
        {
            using var document = System.Text.Json.JsonDocument.Parse(responseBody);
            if (document.RootElement.TryGetProperty("detail", out var detail))
            {
                return detail.GetString() ?? responseBody;
            }
        }
        catch (System.Text.Json.JsonException) { }
        return responseBody.Length > 240 ? responseBody[..240] + "…" : responseBody;
    }

    /// <summary>Añade una sección al borrador y le deja una lección, para que nunca quede vacía.</summary>
    public SectionDraftForm AddSection(string title = "", string firstLessonTitle = "")
    {
        var section = new SectionDraftForm(RemoveSection)
        {
            Title = title,
            CompetencyLabel = CompetencyLabel,
            CompetencyHint = CompetencyHint,
        };
        section.PropertyChanged += OnDraftChanged;
        section.Lessons.CollectionChanged += (_, _) => Notify(nameof(StructureSummary));
        DraftSections.Add(section);
        section.AddLesson(firstLessonTitle);
        RenumberSections();
        return section;
    }

    private void RemoveSection(SectionDraftForm section)
    {
        // Un curso sin secciones no se puede recorrer: la última no se quita.
        if (DraftSections.Count <= 1) return;
        section.PropertyChanged -= OnDraftChanged;
        DraftSections.Remove(section);
        RenumberSections();
    }

    private void RenumberSections()
    {
        for (var i = 0; i < DraftSections.Count; i++)
        {
            DraftSections[i].Position = i + 1;
            DraftSections[i].CanRemove = DraftSections.Count > 1;
        }
        Notify(nameof(StructureSummary));
    }

    private void OnDraftChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(SectionDraftForm.LessonCountLabel)) Notify(nameof(StructureSummary));
    }

    private void ApplyCompetencyLabels()
    {
        foreach (var section in DraftSections)
        {
            section.CompetencyLabel = CompetencyLabel;
            section.CompetencyHint = CompetencyHint;
        }
    }

    private void ResetWizard()
    {
        WizardStep = 1;
        NewTitle = "";
        NewDescription = "";
        foreach (var section in DraftSections) section.PropertyChanged -= OnDraftChanged;
        DraftSections.Clear();
        AddSection();
    }

    private void NotifyCourse()
    {
        foreach (var name in new[]
        {
            nameof(CourseTitle), nameof(CourseDescription), nameof(CourseStatus), nameof(CourseSummary), nameof(FrameworkLabel),
            nameof(SectionCount), nameof(LessonCount), nameof(StudentCount), nameof(QuizTitle), nameof(QuizMeta), nameof(HasQuiz),
            nameof(CompletionLabel),
        }) Notify(name);
    }

    private void NotifyResults()
    {
        Notify(nameof(FinishedCount));
        Notify(nameof(CompletionLabel));
        Notify(nameof(AverageLabel));
    }

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        Notify(name);
        return true;
    }

    private void Notify([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    public async ValueTask DisposeAsync()
    {
        _healthCts?.Cancel();
        _healthCts?.Dispose();
        StopRealtime();
        await _realtime.DisposeAsync();
    }
}
