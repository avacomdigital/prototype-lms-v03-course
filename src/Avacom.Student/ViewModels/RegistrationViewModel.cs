using Avacom.OPS.Core.Services;
using Avacom.Student.Pages;
using Avacom.Student.Services;

namespace Avacom.Student.ViewModels;

public sealed class RegistrationViewModel : ViewModelBase
{
    private readonly ILmsApiClient _api;
    private readonly ExamSession _session;
    private readonly ClientEndpointSettings _endpoint;
    private string _name = "";
    private string _serverUrl;
    private string _status = "Escribe tus datos para entrar al aula.";
    private string _diagnostic = "";
    private bool _isBusy;
    private bool _isConnected;

    public RegistrationViewModel(ILmsApiClient api, ExamSession session, ClientEndpointSettings endpoint)
    {
        _api = api;
        _session = session;
        _endpoint = endpoint;
        _serverUrl = endpoint.BaseUrl;
        ConnectCommand = new Command(async () => await ConnectAsync(), () => !IsBusy);
        CopyDiagnosticCommand = new Command(async () =>
        {
            if (!string.IsNullOrWhiteSpace(Diagnostic)) await Clipboard.Default.SetTextAsync(Diagnostic);
        });
    }

    public string Name { get => _name; set => Set(ref _name, value); }
    public string ServerUrl { get => _serverUrl; set => Set(ref _serverUrl, value); }
    public string Status { get => _status; private set => Set(ref _status, value); }
    public string Diagnostic { get => _diagnostic; private set { Set(ref _diagnostic, value); Notify(nameof(HasDiagnostic)); } }
    public bool HasDiagnostic => !string.IsNullOrWhiteSpace(Diagnostic);
    public bool IsBusy { get => _isBusy; private set { Set(ref _isBusy, value); ConnectCommand.ChangeCanExecute(); } }
    public bool IsConnected { get => _isConnected; private set => Set(ref _isConnected, value); }
    public Command ConnectCommand { get; }
    public Command CopyDiagnosticCommand { get; }

    private async Task ConnectAsync()
    {
        Diagnostic = "";
        IsConnected = false;
        if (Name.Trim().Length < 2)
        {
            Status = "Escribe tu nombre completo.";
            return;
        }
        if (!Uri.TryCreate(ServerUrl, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https"))
        {
            Status = "Escribe una dirección válida, por ejemplo http://192.168.1.20:8000/.";
            return;
        }

        IsBusy = true;
        Status = "Buscando el aula…";
        try
        {
            _endpoint.BaseUrl = ServerUrl;
            if (!await _api.CheckHealthAsync())
                throw new HttpRequestException($"La API no respondió en {_endpoint.BaseUrl}");
            var courses = await _api.GetCoursesAsync(studentCatalog: true);
            if (courses.Count == 0) throw new LmsApiException(404, "No hay cursos habilitados.");

            _session.StudentName = Name.Trim();
            _session.PersonId = Slug(Name);
            _session.ServerAddress = _endpoint.BaseUrl;
            _session.Courses = courses;
            IsConnected = true;
            Status = $"Conectado a {_endpoint.Current.HttpBaseUri.Host}:{_endpoint.Current.HttpBaseUri.Port}";
            await Shell.Current.GoToAsync(nameof(CoursesPage));
        }
        catch (Exception exception)
        {
            Status = exception switch
            {
                LmsApiException { StatusCode: 404 } => "El aula está conectada, pero todavía no hay cursos publicados.",
                HttpRequestException => "No encontramos el host. Revisa que ambos equipos estén en la misma red.",
                TaskCanceledException => "La conexión tardó demasiado. Revisa la dirección y el Wi-Fi.",
                _ => $"No se pudo conectar: {exception.Message}",
            };
            Diagnostic = $"{DateTimeOffset.Now:O}\nNombre: {Name.Trim()}\nDirección: {ServerUrl}\n{exception}";
        }
        finally { IsBusy = false; }
    }

    private static string Slug(string value)
    {
        var normalized = new string(value.Trim().ToLowerInvariant().Select(ch => char.IsLetterOrDigit(ch) ? ch : '-').ToArray());
        while (normalized.Contains("--", StringComparison.Ordinal)) normalized = normalized.Replace("--", "-", StringComparison.Ordinal);
        return normalized.Trim('-');
    }
}
