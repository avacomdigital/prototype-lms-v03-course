using Avacom.OPS.Core.Configuration;

namespace Avacom.Student.Services;

public sealed class ClientEndpointSettings
{
    private const string Key = "api_base_url";
    private const string DefaultUrl = "http://192.168.1.10:8000/";
    public string BaseUrl
    {
        get => Preferences.Default.Get(Key, DefaultUrl);
        set => Preferences.Default.Set(Key, new ApiEndpoint(value).BaseUrl);
    }
    public ApiEndpoint Current => new(BaseUrl);
}
