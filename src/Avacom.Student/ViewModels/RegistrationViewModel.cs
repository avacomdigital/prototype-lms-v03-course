using Avacom.OPS.Core.Services;
using Avacom.Student.Pages;
using Avacom.Student.Services;

namespace Avacom.Student.ViewModels;

/// <summary>
/// Entrar: el nombre del alumno y la dirección del nodo del aula.
///
/// No hay contraseña. Es un prototipo y el aula no tiene internet, así que la
/// identidad es el nombre que el alumno escribe; el backend no autentica nada
/// todavía. Cuando exista, esta pantalla es la que cambia.
///
/// <para>
/// Lo que sí hace bien esta pantalla es DECIR si hay conexión, en verde o en
/// rojo, antes de dejar entrar. Un alumno delante de una tableta que no conecta
/// no puede diagnosticar nada: o se le dice qué pasa, o se queda mirando.
/// </para>
/// </summary>
public sealed class RegistrationViewModel : ViewModelBase
{
    private readonly ClientEndpointSettings _endpoint;
    private readonly ILmsApiClient _api;
    private readonly ExamSession _session;
    private readonly ILocalLog _log;

    private string _name = "";
    private string _serverUrl;
    private bool _isBusy;
    private bool _isConnected;
    private bool _isFailed;
    private string _status = "Escribe la dirección del equipo del aula y pulsa Comprobar.";
    private string _hostId = "";

    public RegistrationViewModel(
        ClientEndpointSettings endpoint, ILmsApiClient api, ExamSession session, ILocalLog log)
    {
        _endpoint = endpoint;
        _api = api;
        _session = session;
        _log = log;
        _serverUrl = endpoint.BaseUrl;

        CheckCommand = new Command(async () => await CheckAsync(), () => !IsBusy);
        EnterCommand = new Command(async () => await EnterAsync(), () => !IsBusy && CanEnter);
    }

    public string Name
    {
        get => _name;
        set { if (Set(ref _name, value)) EnterCommand.ChangeCanExecute(); }
    }

    /// <summary>
    /// La dirección del nodo. Cambiarla invalida la comprobación anterior: seguir
    /// mostrando «Conectado» de una dirección que ya no es la escrita sería
    /// mentir en la única pantalla donde el alumno puede detectar el problema.
    /// </summary>
    public string ServerUrl
    {
        get => _serverUrl;
        set
        {
            if (!Set(ref _serverUrl, value)) return;
            IsConnected = false;
            IsFailed = false;
            Status = "La dirección cambió. Pulsa Comprobar.";
        }
    }

    public bool IsBusy
    {
        get => _isBusy;
        private set
        {
            Set(ref _isBusy, value);
            CheckCommand.ChangeCanExecute();
            EnterCommand.ChangeCanExecute();
        }
    }

    /// <summary>Verde: la API del nodo respondió.</summary>
    public bool IsConnected
    {
        get => _isConnected;
        private set
        {
            Set(ref _isConnected, value);
            Notify(nameof(CanEnter));
            Notify(nameof(ConnectionLabel));
            EnterCommand.ChangeCanExecute();
        }
    }

    /// <summary>Rojo: se intentó y no contestó.</summary>
    public bool IsFailed
    {
        get => _isFailed;
        private set { Set(ref _isFailed, value); Notify(nameof(ConnectionLabel)); }
    }

    /// <summary>El texto del semáforo. Es el único que el alumno mira.</summary>
    public string ConnectionLabel => IsConnected
        ? "Conectado"
        : IsFailed ? "Sin conexión" : "Sin comprobar";

    public string Status { get => _status; private set => Set(ref _status, value); }

    /// <summary>El equipo del aula, descubierto al conectar. No se le pide al alumno.</summary>
    public string HostId { get => _hostId; private set => Set(ref _hostId, value); }

    public bool CanEnter => IsConnected && !string.IsNullOrWhiteSpace(Name);

    public Command CheckCommand { get; }
    public Command EnterCommand { get; }

    /// <summary>
    /// Comprueba la conexión y averigua de qué equipo se trata.
    ///
    /// El `host_id` no se le pregunta al alumno: se lee de la propia API. Pedirle
    /// el nombre del equipo a un niño de transición no es una opción, y un
    /// docente tampoco debería tener que dictarlo tableta por tableta.
    /// </summary>
    private async Task CheckAsync()
    {
        IsBusy = true;
        IsConnected = false;
        IsFailed = false;
        Status = "Buscando el equipo del aula…";
        try
        {
            if (!Uri.TryCreate(Normalizar(ServerUrl), UriKind.Absolute, out _))
            {
                IsFailed = true;
                Status = "Esa dirección no se entiende. Ejemplo: 192.168.0.29:8000";
                return;
            }

            _endpoint.BaseUrl = Normalizar(ServerUrl);
            _serverUrl = _endpoint.BaseUrl;
            Notify(nameof(ServerUrl));

            if (!await _api.CheckHealthAsync())
            {
                IsFailed = true;
                Status = $"No hay respuesta en {_endpoint.BaseUrl}. Comprueba que el equipo del "
                       + "aula esté encendido y en la misma red.";
                return;
            }

            HostId = await _api.DiscoverHostIdAsync() ?? "";
            IsConnected = true;
            Status = string.IsNullOrWhiteSpace(HostId)
                ? "Conectado. El equipo del aula todavía no tiene contenido instalado."
                : $"Conectado al equipo {HostId}.";
        }
        catch (Exception excepcion)
        {
            IsFailed = true;
            Status = $"No se pudo conectar: {excepcion.Message}";
            await _log.WriteAsync("registro", "check_failed", excepcion);
        }
        finally { IsBusy = false; }
    }

    private async Task EnterAsync()
    {
        if (!CanEnter) return;
        _session.StudentName = Name.Trim();
        _session.PersonId = Slug(Name);
        _session.ServerAddress = _endpoint.BaseUrl;
        _session.HostId = HostId;
        await Shell.Current.GoToAsync(nameof(ResumenPage));
    }

    /// <summary>Acepta «192.168.0.29:8000» sin obligar a escribir el esquema.</summary>
    private static string Normalizar(string direccion)
    {
        direccion = (direccion ?? "").Trim();
        if (direccion.Length == 0) return direccion;
        if (!direccion.StartsWith("http://") && !direccion.StartsWith("https://"))
            direccion = $"http://{direccion}";
        return direccion.EndsWith('/') ? direccion : direccion + "/";
    }

    /// <summary>
    /// El identificador con el que el backend guarda el progreso. Sale del
    /// nombre porque no hay login: si el alumno vuelve a escribir su nombre
    /// igual, recupera su avance.
    /// </summary>
    private static string Slug(string nombre)
    {
        var limpio = new string((nombre ?? "").Trim().ToLowerInvariant()
            .Select(c => char.IsLetterOrDigit(c) ? c : '-').ToArray());
        while (limpio.Contains("--")) limpio = limpio.Replace("--", "-");
        return limpio.Trim('-');
    }
}
