using Avacom.OPS.Core.Configuration;

namespace Avacom.OPS.Master;

public sealed class MasterEndpointSettings
{
    private const string Key = "master_api_url";
    public string BaseUrl { get => Preferences.Default.Get(Key, "http://127.0.0.1:8000/"); set => Preferences.Default.Set(Key, new ApiEndpoint(value).BaseUrl); }
    public ApiEndpoint Current => new(BaseUrl);
}
