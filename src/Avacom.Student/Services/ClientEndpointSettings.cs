using Avacom.OPS.Core.Configuration;

namespace Avacom.Student.Services;

public sealed class ClientEndpointSettings
{
    private const string Key = "api_base_url";
    // Solo es la sugerencia que aparece en la pantalla de entrada; el alumno la
    // corrige y queda guardada. Un valor fijo aquí nunca va a acertar en todas
    // las aulas, y por eso la pantalla comprueba antes de dejar entrar.
    private const string DefaultUrl = "http://192.168.0.29:8000/";
    public string BaseUrl
    {
        get => Preferences.Default.Get(Key, DefaultUrl);
        set => Preferences.Default.Set(Key, new ApiEndpoint(value).BaseUrl);
    }
    public ApiEndpoint Current => new(BaseUrl);
}
