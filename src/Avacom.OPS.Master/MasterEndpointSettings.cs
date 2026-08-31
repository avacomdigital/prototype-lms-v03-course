using Avacom.OPS.Core.Configuration;

namespace Avacom.OPS.Master;

public sealed class MasterEndpointSettings
{
    private const string Key = "master_api_url";
    private const string HostKey = "master_host_id";

    public string BaseUrl { get => Preferences.Default.Get(Key, "http://127.0.0.1:8000/"); set => Preferences.Default.Set(Key, new ApiEndpoint(value).BaseUrl); }
    public ApiEndpoint Current => new(BaseUrl);

    /// <summary>
    /// Identidad de ESTA OPS. Es la clave con la que m05_curso_host registra qué
    /// contenido está físicamente instalado aquí, así que tiene que ser estable
    /// entre reinicios: se persiste en Preferences.
    ///
    /// Por omisión el nombre del equipo, que es lo que un técnico reconoce al
    /// llegar a una sede. Se puede cambiar por algo más hablado —OPS-BOGOTA-A3—
    /// sin que eso afecte al contenido ya instalado: el registro viejo sigue
    /// existiendo bajo el nombre anterior, que es lo correcto para no perder el
    /// rastro de qué se instaló dónde.
    /// </summary>
    public string HostId
    {
        get => Preferences.Default.Get(HostKey, DefaultHostId());
        set
        {
            var limpio = (value ?? "").Trim();
            Preferences.Default.Set(HostKey, string.IsNullOrEmpty(limpio) ? DefaultHostId() : limpio);
        }
    }

    private static string DefaultHostId()
    {
        var nombre = Environment.MachineName;
        return string.IsNullOrWhiteSpace(nombre) ? "OPS-LOCAL" : nombre.Trim();
    }
}
